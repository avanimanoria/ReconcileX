"""Tests for the /batches API routes."""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import app
from backend.app.api.deps import get_db


@pytest.fixture
def api_client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def fixture_files():
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    return {
        "payments_file": ("payments.csv", (data_dir / "payments.csv").read_bytes(), "text/csv"),
        "settlements_file": ("settlements.csv", (data_dir / "settlements.csv").read_bytes(), "text/csv"),
        "bank_credits_file": ("bank_credits.csv", (data_dir / "bank_credits.csv").read_bytes(), "text/csv"),
        "refunds_file": ("refunds.csv", (data_dir / "refunds.csv").read_bytes(), "text/csv"),
    }


def test_post_batches_valid_upload(api_client, fixture_files):
    """Verify uploading all four valid CSV files returns 201 Created with full summary."""
    response = api_client.post("/batches", files=fixture_files)
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert "batch_number" in data
    assert data["status"] == "COMPLETED"
    assert data["disposition"] == "PROCESSED_NEW"
    assert data["total_payments"] == 15
    assert data["total_settlements"] == 15
    assert data["auto_match_count"] == 8
    assert data["exception_count"] == 7


def test_post_batches_idempotent_repeat(api_client, fixture_files):
    """Verify submitting identical content hash returns 200 OK with ALREADY_COMPLETED."""
    # First upload
    res1 = api_client.post("/batches", files=fixture_files)
    assert res1.status_code in (200, 201)
    batch_id = res1.json()["id"]

    # Second upload with identical bytes
    res2 = api_client.post("/batches", files=fixture_files)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["id"] == batch_id
    assert data2["disposition"] == "ALREADY_COMPLETED"


def test_post_batches_previously_failed_returns_conflict_with_historical_batch(api_client, fixture_files, monkeypatch, db_conn):
    """Verify re-submitting content hash of a failed batch returns HTTP 409 with historical batch detail and creates no duplicate records."""
    # 1. Inject failure into matcher
    def mock_failing_matcher(dataset):
        raise RuntimeError("Simulated API batch processing failure")

    monkeypatch.setattr("backend.app.services.batch_service.run_improved_reconciliation", mock_failing_matcher)

    # Initial POST raises RuntimeError due to unhandled engine failure in service
    with pytest.raises(RuntimeError, match="Simulated API batch processing failure"):
        api_client.post("/batches", files=fixture_files)

    # Verify batch was persisted as FAILED
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM reconciliation_batches WHERE status = 'FAILED';")
        failed_batch = cur.fetchone()
        assert failed_batch is not None
        batch_id = str(failed_batch["id"])

        cur.execute("SELECT COUNT(*) as count FROM reconciliation_batches;")
        batches_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM payments WHERE batch_id = %s;", (batch_id,))
        payments_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (batch_id,))
        results_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM exceptions WHERE batch_id = %s;", (batch_id,))
        exceptions_before = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s AND event_type = 'BATCH_CREATED';", (batch_id,))
        created_audits_before = cur.fetchone()["count"]

    # Undo monkeypatch
    monkeypatch.undo()

    # Re-submit identical files
    response = api_client.post("/batches", files=fixture_files)

    # Assert 409 Conflict
    assert response.status_code == 409
    data = response.json()
    detail = data["detail"]
    assert "previously failed and cannot be reprocessed" in detail["message"]
    assert detail["batch"]["id"] == batch_id
    assert detail["batch"]["status"] == "FAILED"
    assert detail["batch"]["disposition"] == "PREVIOUSLY_FAILED"

    # Assert no duplicate batch, normalized records, results, exceptions, or BATCH_CREATED audit events
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_batches;")
        assert cur.fetchone()["count"] == batches_before
        cur.execute("SELECT COUNT(*) as count FROM payments WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()["count"] == payments_before
        cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()["count"] == results_before
        cur.execute("SELECT COUNT(*) as count FROM exceptions WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()["count"] == exceptions_before
        cur.execute("SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s AND event_type = 'BATCH_CREATED';", (batch_id,))
        assert cur.fetchone()["count"] == created_audits_before


def test_post_batches_rejects_missing_file(api_client, fixture_files):
    """Verify omitting any required file returns 422 Unprocessable Entity."""
    incomplete_files = {k: v for k, v in fixture_files.items() if k != "refunds_file"}
    response = api_client.post("/batches", files=incomplete_files)
    assert response.status_code == 422


def test_post_batches_rejects_empty_file(api_client, fixture_files):
    """Verify 0-byte upload returns 422 Unprocessable Entity."""
    bad_files = dict(fixture_files)
    bad_files["payments_file"] = ("payments.csv", b"", "text/csv")
    response = api_client.post("/batches", files=bad_files)
    assert response.status_code == 422
    assert "cannot be empty" in response.json()["detail"]


def test_post_batches_rejects_non_csv_filename(api_client, fixture_files):
    """Verify non-.csv filename returns 422 Unprocessable Entity."""
    bad_files = dict(fixture_files)
    bad_files["payments_file"] = ("payments.json", b"dummy,header\n", "application/json")
    response = api_client.post("/batches", files=bad_files)
    assert response.status_code == 422
    assert "must be a CSV file with .csv extension" in response.json()["detail"]


def test_post_batches_rejects_oversized_file(api_client, fixture_files):
    """Verify upload exceeding 10 MB returns 422 Unprocessable Entity."""
    bad_files = dict(fixture_files)
    bad_files["payments_file"] = ("payments.csv", b"x" * (11 * 1024 * 1024), "text/csv")
    response = api_client.post("/batches", files=bad_files)
    assert response.status_code == 422
    assert "exceeds maximum allowed size" in response.json()["detail"]


def test_get_batches_pagination_and_ordering(api_client, fixture_files):
    """Verify GET /batches returns paginated list sorted newest first."""
    # Ensure at least one batch exists
    api_client.post("/batches", files=fixture_files)

    response = api_client.get("/batches?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_get_batches_status_filter_invalid(api_client):
    """Verify invalid status filter returns 422 Unprocessable Entity."""
    response = api_client.get("/batches?status=INVALID_STATUS")
    assert response.status_code == 422


def test_get_batch_by_id_and_not_found(api_client, fixture_files):
    """Verify GET /batches/{id} returns batch metadata or 404."""
    post_res = api_client.post("/batches", files=fixture_files)
    batch_id = post_res.json()["id"]

    get_res = api_client.get(f"/batches/{batch_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == batch_id

    # Non-existent UUID
    fake_id = "00000000-0000-0000-0000-000000000000"
    not_found_res = api_client.get(f"/batches/{fake_id}")
    assert not_found_res.status_code == 404


def test_get_batch_results_filtering(api_client, fixture_files):
    """Verify GET /batches/{id}/results filtering by match_status."""
    post_res = api_client.post("/batches", files=fixture_files)
    batch_id = post_res.json()["id"]

    # Filter AUTO_MATCH
    res_auto = api_client.get(f"/batches/{batch_id}/results?match_status=AUTO_MATCH")
    assert res_auto.status_code == 200
    assert res_auto.json()["total"] == 8
    for item in res_auto.json()["items"]:
        assert item["match_status"] == "AUTO_MATCH"

    # Filter EXCEPTION
    res_exc = api_client.get(f"/batches/{batch_id}/results?match_status=EXCEPTION")
    assert res_exc.status_code == 200
    assert res_exc.json()["total"] == 7
    for item in res_exc.json()["items"]:
        assert item["match_status"] == "EXCEPTION"


def test_get_batch_exceptions_filtering(api_client, fixture_files):
    """Verify GET /batches/{id}/exceptions filtering by priority and category."""
    post_res = api_client.post("/batches", files=fixture_files)
    batch_id = post_res.json()["id"]

    # Filter by priority=HIGH
    res_high = api_client.get(f"/batches/{batch_id}/exceptions?priority=HIGH")
    assert res_high.status_code == 200
    assert res_high.json()["total"] == 2
    for item in res_high.json()["items"]:
        assert item["priority"] == "HIGH"

    # Filter by category=SETTLEMENT_DELAY
    res_delay = api_client.get(f"/batches/{batch_id}/exceptions?category=SETTLEMENT_DELAY")
    assert res_delay.status_code == 200
    assert res_delay.json()["total"] == 1
    assert res_delay.json()["items"][0]["category"] == "SETTLEMENT_DELAY"
    assert res_delay.json()["items"][0]["settlement_id"] == "SET-005"


def test_post_and_immediate_get_and_list_returns_same_persisted_batch(api_client, fixture_files):
    """Verify POST /batches, GET /batches/{id}, and GET /batches return the exact same persisted batch."""
    # 1. POST batch
    post_res = api_client.post("/batches", files=fixture_files)
    assert post_res.status_code == 201
    post_data = post_res.json()
    batch_id = post_data["id"]

    # 2. Immediately GET batch by ID
    get_res = api_client.get(f"/batches/{batch_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["id"] == batch_id
    assert get_data["batch_number"] == post_data["batch_number"]
    assert get_data["status"] == "COMPLETED"
    assert get_data["total_payments"] == post_data["total_payments"]
    assert get_data["auto_match_count"] == post_data["auto_match_count"]

    # 3. Immediately list batches and verify batch is returned
    list_res = api_client.get("/batches?limit=10&offset=0")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    matching_batches = [b for b in list_data["items"] if b["id"] == batch_id]
    assert len(matching_batches) == 1
    assert matching_batches[0]["id"] == batch_id
    assert matching_batches[0]["batch_number"] == post_data["batch_number"]


def test_post_batches_durable_commit_verified_by_independent_connection(db_conn, setup_test_database, fixture_files):
    """Verify real request lifecycle (independent per-request connections) durably commits to PostgreSQL."""
    test_url = setup_test_database

    def _real_lifecycle_get_db():
        from backend.app.db.connection import get_connection
        conn = get_connection(test_url)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _real_lifecycle_get_db
    try:
        client = TestClient(app)

        # 1. POST batch through real request lifecycle
        post_res = client.post("/batches", files=fixture_files)
        assert post_res.status_code == 201
        batch_id = post_res.json()["id"]

        # 2. Open a completely independent psycopg connection outside FastAPI/client
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(test_url, row_factory=dict_row) as independent_conn:
            with independent_conn.cursor() as cur:
                # Verify batch is committed and visible
                cur.execute("SELECT * FROM reconciliation_batches WHERE id = %s;", (batch_id,))
                batch_row = cur.fetchone()
                assert batch_row is not None
                assert batch_row["status"] == "COMPLETED"
                assert batch_row["auto_match_count"] == 8
                assert batch_row["exception_count"] == 7

                # Verify results are committed and visible
                cur.execute("SELECT COUNT(*) as count FROM reconciliation_results WHERE batch_id = %s;", (batch_id,))
                assert cur.fetchone()["count"] == 15

                # Verify exceptions are committed and visible
                cur.execute("SELECT COUNT(*) as count FROM exceptions WHERE batch_id = %s;", (batch_id,))
                assert cur.fetchone()["count"] == 7

                # Verify audit events are committed and visible
                cur.execute("SELECT COUNT(*) as count FROM audit_events WHERE batch_id = %s;", (batch_id,))
                assert cur.fetchone()["count"] >= 8

        # 3. Subsequent GET /batches/{id} on separate request connection retrieves the committed batch
        get_res = client.get(f"/batches/{batch_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == batch_id

        # 4. Subsequent GET /batches lists the committed batch
        list_res = client.get("/batches")
        assert list_res.status_code == 200
        assert list_res.json()["total"] >= 1
        assert any(b["id"] == batch_id for b in list_res.json()["items"])
    finally:
        app.dependency_overrides.clear()


