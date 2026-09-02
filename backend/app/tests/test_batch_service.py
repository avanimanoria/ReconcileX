"""Tests for BatchService end-to-end persistence and idempotency."""

from pathlib import Path
import pytest

from backend.app.services.batch_service import (
    BatchAlreadyInProgressError,
    BatchDisposition,
    BatchService,
    compute_canonical_content_hash,
)


def test_process_fixture_batch_end_to_end(db_conn):
    """Verify persisting handcrafted fixture data end-to-end into PostgreSQL."""
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    service = BatchService()

    summary = service.process_csv_directory(conn=db_conn, data_dir=data_dir)

    assert summary.status == "COMPLETED"
    assert summary.disposition == BatchDisposition.PROCESSED_NEW
    assert summary.total_payments == 15
    assert summary.total_settlements == 15
    assert summary.auto_match_count == 8
    assert summary.exception_count == 7

    # Verify reconciliation results stored in database
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (summary.batch_id,))
        res_count = cur.fetchone()["count"]
        assert res_count == 15

        # Verify rule_version
        cur.execute("SELECT DISTINCT rule_version FROM reconciliation_results WHERE batch_id = %s;", (summary.batch_id,))
        rule_versions = [r["rule_version"] for r in cur.fetchall()]
        assert rule_versions == ["v1.1-deterministic"]

    # Verify deterministic exception priority mapping for SET-005, SET-007, and SET-015
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.category, e.priority, r.settlement_id
            FROM exceptions e
            JOIN reconciliation_results r ON e.reconciliation_result_id = r.id
            WHERE e.batch_id = %s;
            """,
            (summary.batch_id,),
        )
        exceptions_map = {row["settlement_id"]: row for row in cur.fetchall()}

    assert "SET-005" in exceptions_map
    assert exceptions_map["SET-005"]["category"] == "SETTLEMENT_DELAY"
    assert exceptions_map["SET-005"]["priority"] == "MEDIUM"

    assert "SET-007" in exceptions_map
    assert exceptions_map["SET-007"]["category"] == "AMOUNT_VARIANCE"
    assert exceptions_map["SET-007"]["priority"] == "HIGH"

    assert "SET-015" in exceptions_map
    assert exceptions_map["SET-015"]["category"] == "INVALID_ROW"
    assert exceptions_map["SET-015"]["priority"] == "CRITICAL"


def test_batch_idempotency_returns_already_completed(db_conn):
    """Verify re-uploading identical file bytes returns ALREADY_COMPLETED without duplicating records."""
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    service = BatchService()

    # First run
    first_summary = service.process_csv_directory(conn=db_conn, data_dir=data_dir)

    # Count audit events before second run
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s;", (first_summary.batch_id,))
        audit_count_before = cur.fetchone()["count"]

    # Second run with same input content
    second_summary = service.process_csv_directory(conn=db_conn, data_dir=data_dir)

    assert second_summary.disposition == BatchDisposition.ALREADY_COMPLETED
    assert second_summary.batch_id == first_summary.batch_id
    assert second_summary.auto_match_count == first_summary.auto_match_count
    assert second_summary.exception_count == first_summary.exception_count

    # Verify no new audit events (like duplicate BATCH_CREATED) were inserted into the completed batch
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s;", (first_summary.batch_id,))
        audit_count_after = cur.fetchone()["count"]
        assert audit_count_after == audit_count_before


def test_duplicate_content_hash_while_processing_is_rejected(db_conn, tmp_path):
    """Verify submitting identical content hash while a batch is in PROCESSING raises BatchAlreadyInProgressError."""
    # Create isolated dummy CSV files
    (tmp_path / "payments.csv").write_text(
        "payment_event_id,payment_id,order_id,captured_amount,status,captured_at\nevt_proc_1,PAY-PROC-1,ORD-1,100.00,captured,2026-09-01T10:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "settlements.csv").write_text(
        "settlement_id,payment_id,gross_amount,fee_amount,gst_on_fee,net_amount,settlement_status,settled_at\nSET-PROC-1,PAY-PROC-1,100.00,2.00,0.36,97.64,settled,2026-09-02T10:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "bank_credits.csv").write_text(
        "bank_txn_id,narration,credit_amount,credited_at\nBANK-PROC-1,NEFT SET-PROC-1,97.64,2026-09-02T14:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "refunds.csv").write_text(
        "refund_id,payment_id,refund_amount,refund_status,refunded_at\n",
        encoding="utf-8",
    )

    service = BatchService()
    p_bytes = (tmp_path / "payments.csv").read_bytes()
    s_bytes = (tmp_path / "settlements.csv").read_bytes()
    b_bytes = (tmp_path / "bank_credits.csv").read_bytes()
    r_bytes = (tmp_path / "refunds.csv").read_bytes()

    content_hash = compute_canonical_content_hash(p_bytes, s_bytes, b_bytes, r_bytes)

    # Create a batch record in PROCESSING status directly
    batch_id = service.batch_repo.create_batch(
        conn=db_conn,
        batch_number="BATCH-PROC-TEST",
        content_hash=content_hash,
        engine_version="v1.1-deterministic",
    )
    service.batch_repo.update_batch_status(conn=db_conn, batch_id=batch_id, status="PROCESSING")
    service.audit_repo.insert_audit_event(
        conn=db_conn,
        batch_id=batch_id,
        event_type="BATCH_CREATED",
        entity_type="BATCH",
        entity_id=batch_id,
        action="CREATE_BATCH",
        reason="Test batch in processing",
    )
    db_conn.commit()

    # Record initial counts
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_batches;")
        batch_count_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM payments WHERE batch_id = %s;", (batch_id,))
        payments_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (batch_id,))
        results_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM exceptions WHERE batch_id = %s;", (batch_id,))
        exceptions_before = cur.fetchone()["count"]
        cur.execute(
            "SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s AND event_type = 'BATCH_CREATED';",
            (batch_id,),
        )
        batch_created_audits_before = cur.fetchone()["count"]

    # Attempt to process the same content
    with pytest.raises(BatchAlreadyInProgressError):
        service.process_csv_directory(conn=db_conn, data_dir=tmp_path)

    # Assert no additional batch or duplicate records
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_batches;")
        assert cur.fetchone()["count"] == batch_count_before
        cur.execute("SELECT COUNT(*) as count FROM payments WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()["count"] == payments_before
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()["count"] == results_before
        cur.execute("SELECT COUNT(*) as count FROM exceptions WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()["count"] == exceptions_before
        cur.execute(
            "SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s AND event_type = 'BATCH_CREATED';",
            (batch_id,),
        )
        assert cur.fetchone()["count"] == batch_created_audits_before


def test_failed_batch_is_preserved_and_repeat_is_not_reprocessed(db_conn, tmp_path, monkeypatch):
    """Verify failed batches are preserved, failure audit is stored, and repeat submissions return PREVIOUSLY_FAILED."""
    # Create isolated dummy CSV files
    (tmp_path / "payments.csv").write_text(
        "payment_event_id,payment_id,order_id,captured_amount,status,captured_at\nevt_fail_1,PAY-FAIL-1,ORD-1,100.00,captured,2026-09-01T10:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "settlements.csv").write_text(
        "settlement_id,payment_id,gross_amount,fee_amount,gst_on_fee,net_amount,settlement_status,settled_at\nSET-FAIL-1,PAY-FAIL-1,100.00,2.00,0.36,97.64,settled,2026-09-02T10:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "bank_credits.csv").write_text(
        "bank_txn_id,narration,credit_amount,credited_at\nBANK-FAIL-1,NEFT SET-FAIL-1,97.64,2026-09-02T14:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "refunds.csv").write_text(
        "refund_id,payment_id,refund_amount,refund_status,refunded_at\n",
        encoding="utf-8",
    )

    service = BatchService()

    # Invalidate matcher execution with monkeypatch
    def mock_failing_matcher(dataset):
        raise RuntimeError("Simulated unrecoverable matcher engine failure")

    monkeypatch.setattr("backend.app.services.batch_service.run_improved_reconciliation", mock_failing_matcher)

    # Initial submission should raise the exception and record FAILED status
    with pytest.raises(RuntimeError, match="Simulated unrecoverable matcher engine failure"):
        service.process_csv_directory(conn=db_conn, data_dir=tmp_path, batch_number="BATCH-FAIL-001")

    # Assert batch is persisted as FAILED with error_message and BATCH_FAILED audit event
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM reconciliation_batches WHERE batch_number = 'BATCH-FAIL-001';")
        failed_batch = cur.fetchone()
        assert failed_batch is not None
        assert failed_batch["status"] == "FAILED"
        assert "Simulated unrecoverable matcher engine failure" in (failed_batch["error_message"] or "")
        batch_id = str(failed_batch["id"])

        cur.execute("SELECT * FROM audit_events WHERE batch_id = %s AND event_type = 'BATCH_FAILED';", (batch_id,))
        fail_audit = cur.fetchone()
        assert fail_audit is not None
        assert "Simulated unrecoverable matcher engine failure" in fail_audit["reason"]

        cur.execute("SELECT COUNT(*) as count FROM reconciliation_batches;")
        total_batches_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (batch_id,))
        results_before = cur.fetchone()["count"]
        cur.execute(
            "SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s AND event_type = 'BATCH_CREATED';",
            (batch_id,),
        )
        created_audits_before = cur.fetchone()["count"]

    # Undo monkeypatch for second submission
    monkeypatch.undo()

    # Re-submitting the exact same canonical bytes
    repeat_summary = service.process_csv_directory(conn=db_conn, data_dir=tmp_path)

    # Assert disposition is PREVIOUSLY_FAILED and batch is not reprocessed
    assert repeat_summary.disposition == BatchDisposition.PREVIOUSLY_FAILED
    assert repeat_summary.batch_id == batch_id
    assert repeat_summary.status == "FAILED"

    # Assert no new batch, duplicate results, or BATCH_CREATED audit events were created
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_batches;")
        assert cur.fetchone()["count"] == total_batches_before
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()["count"] == results_before
        cur.execute(
            "SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s AND event_type = 'BATCH_CREATED';",
            (batch_id,),
        )
        assert cur.fetchone()["count"] == created_audits_before


def test_batch_atomicity_failure_leaves_no_partial_completed_batch(setup_test_database, monkeypatch, tmp_path):
    """Verify that failure during results/exceptions/audit persistence leaves no partial COMPLETED batch."""
    test_url = setup_test_database
    (tmp_path / "payments.csv").write_text(
        "payment_event_id,payment_id,order_id,captured_amount,status,captured_at\n"
        "EVT-001,PAY-001,ORD-001,1000,captured,2026-08-25T10:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "settlements.csv").write_text(
        "settlement_id,payment_id,gross_amount,fee_amount,gst_on_fee,net_amount,settlement_status,settled_at\n"
        "SET-001,PAY-001,1000,20,3.6,976.4,settled,2026-08-26T09:00:00\n",
        encoding="utf-8",
    )
    (tmp_path / "bank_credits.csv").write_text(
        "bank_txn_id,credited_amount,credited_at,narration\n"
        "BNK-001,976.4,2026-08-26T11:00:00,REF:SET-001\n",
        encoding="utf-8",
    )
    (tmp_path / "refunds.csv").write_text(
        "refund_id,payment_id,refund_amount,refund_status,refunded_at\n",
        encoding="utf-8",
    )

    from backend.app.db.connection import get_connection
    service = BatchService()

    # Inject failure into insert_results_and_exceptions
    def mock_failing_recon_repo(*args, **kwargs):
        raise RuntimeError("Simulated unrecoverable DB error during results persistence")

    monkeypatch.setattr(service.recon_repo, "insert_results_and_exceptions", mock_failing_recon_repo)

    with get_connection(test_url) as conn:
        with pytest.raises(RuntimeError, match="Simulated unrecoverable DB error during results persistence"):
            service.process_csv_directory(conn=conn, data_dir=tmp_path, batch_number="BATCH-ATOMIC-001")

    # Connect independently and verify database state
    with get_connection(test_url) as fresh_conn:
        with fresh_conn.cursor() as cur:
            # 1. Assert no COMPLETED batch exists
            cur.execute("SELECT * FROM reconciliation_batches WHERE batch_number = 'BATCH-ATOMIC-001';")
            batch = cur.fetchone()
            assert batch is not None
            assert batch["status"] != "COMPLETED"

            # 2. Assert no partial reconciliation results were committed
            cur.execute("SELECT COUNT(*) as c FROM reconciliation_results WHERE batch_id = %s;", (str(batch["id"]),))
            assert cur.fetchone()["c"] == 0

            # 3. Assert no partial exceptions were committed
            cur.execute("SELECT COUNT(*) as c FROM exceptions WHERE batch_id = %s;", (str(batch["id"]),))
            assert cur.fetchone()["c"] == 0

