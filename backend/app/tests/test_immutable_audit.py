"""Tests for append-only audit log immutability and PostgreSQL trigger enforcement."""

from pathlib import Path
import pytest
import psycopg

from backend.app.db.repositories.audit_repo import AuditRepository
from backend.app.services.batch_service import BatchService
from backend.app.services.exception_service import ExceptionService


def test_audit_events_db_trigger_blocks_update(db_conn):
    """Verify direct SQL UPDATE on audit_events is strictly blocked by PostgreSQL trigger."""
    audit_repo = AuditRepository()
    event_id = audit_repo.insert_audit_event(
        db_conn,
        event_type="TEST_EVENT",
        entity_type="TEST",
        entity_id="test-001",
        action="TEST_ACTION",
        reason="Initial test audit event",
    )
    db_conn.commit()

    # Attempt direct SQL UPDATE on audit_events
    with pytest.raises(psycopg.errors.RaiseException) as excinfo:
        with db_conn.cursor() as cur:
            cur.execute("UPDATE audit_events SET reason = 'Tampered reason' WHERE id = %s;", (event_id,))
        db_conn.commit()

    assert "audit_events is append-only" in str(excinfo.value)
    db_conn.rollback()


def test_audit_events_db_trigger_blocks_delete(db_conn):
    """Verify direct SQL DELETE on audit_events is strictly blocked by PostgreSQL trigger."""
    audit_repo = AuditRepository()
    event_id = audit_repo.insert_audit_event(
        db_conn,
        event_type="TEST_EVENT_DELETE",
        entity_type="TEST",
        entity_id="test-002",
        action="TEST_ACTION",
        reason="Initial test audit event for delete test",
    )
    db_conn.commit()

    # Attempt direct SQL DELETE on audit_events
    with pytest.raises(psycopg.errors.RaiseException) as excinfo:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM audit_events WHERE id = %s;", (event_id,))
        db_conn.commit()

    assert "audit_events is append-only" in str(excinfo.value)
    db_conn.rollback()


def test_exception_transition_records_state_diff_in_audit_events(db_conn):
    """Verify status transitions record before_state and after_state in audit trail."""
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    batch_service = BatchService()
    summary = batch_service.process_csv_directory(conn=db_conn, data_dir=data_dir)

    exc_service = ExceptionService()
    exc_id = summary.exceptions[0]["exception_id"]

    exc_service.transition_status(
        db_conn, exception_id=exc_id, target_status="IN_REVIEW", actor="analyst_bob", reason="Starting investigation"
    )

    audit_repo = AuditRepository()
    events = audit_repo.list_audit_events_for_exception(db_conn, exception_id=exc_id)

    # Check for EXCEPTION_STATUS_IN_REVIEW event
    status_event = next((e for e in events if e["event_type"] == "EXCEPTION_STATUS_IN_REVIEW"), None)
    assert status_event is not None
    assert status_event["actor"] == "analyst_bob"
    assert status_event["before_state"]["status"] == "OPEN"
    assert status_event["after_state"]["status"] == "IN_REVIEW"
    assert status_event["reason"] == "Starting investigation"
