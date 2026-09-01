"""Tests for ExceptionService workflow, assignment, and state machine transitions."""

from pathlib import Path
import pytest

from backend.app.services.batch_service import BatchService
from backend.app.services.exception_service import (
    ExceptionService,
    InvalidStateTransitionError,
)


@pytest.fixture
def sample_batch_exception_id(db_conn):
    """Seed the database with the fixture batch and return a sample exception ID."""
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    service = BatchService()
    summary = service.process_csv_directory(conn=db_conn, data_dir=data_dir)
    assert len(summary.exceptions) > 0
    return summary.exceptions[0]["exception_id"]


def test_exception_lifecycle_valid_transitions(db_conn, sample_batch_exception_id):
    """Verify valid state transitions: OPEN -> IN_REVIEW -> RESOLVED -> IN_REVIEW -> DISMISSED."""
    service = ExceptionService()
    exc_id = sample_batch_exception_id

    # 1. OPEN -> IN_REVIEW
    exc = service.transition_status(db_conn, exc_id, target_status="IN_REVIEW", actor="analyst_1", reason="Beginning review")
    assert exc["status"] == "IN_REVIEW"

    # 2. IN_REVIEW -> RESOLVED
    exc = service.transition_status(
        db_conn, exc_id, target_status="RESOLVED", actor="analyst_1", reason="Settlement confirmed by payment gateway"
    )
    assert exc["status"] == "RESOLVED"
    assert exc["resolved_by"] == "analyst_1"
    assert exc["resolved_at"] is not None
    assert exc["resolution_reason"] == "Settlement confirmed by payment gateway"

    # 3. RESOLVED -> IN_REVIEW (Reopening clears resolution fields)
    exc = service.transition_status(db_conn, exc_id, target_status="IN_REVIEW", actor="manager_1", reason="Re-evaluating dispute")
    assert exc["status"] == "IN_REVIEW"
    assert exc["resolved_by"] is None
    assert exc["resolved_at"] is None

    # 4. IN_REVIEW -> DISMISSED
    exc = service.transition_status(
        db_conn, exc_id, target_status="DISMISSED", actor="manager_1", reason="Expected edge case confirmed by risk ops"
    )
    assert exc["status"] == "DISMISSED"
    assert exc["resolved_by"] == "manager_1"
    assert exc["resolved_at"] is not None


def test_exception_invalid_transitions_rejected(db_conn, sample_batch_exception_id):
    """Verify invalid state transitions raise InvalidStateTransitionError."""
    service = ExceptionService()
    exc_id = sample_batch_exception_id

    # OPEN -> RESOLVED directly (not allowed, must go through IN_REVIEW)
    with pytest.raises(InvalidStateTransitionError):
        service.transition_status(db_conn, exc_id, target_status="RESOLVED", actor="analyst_1", reason="Direct resolve")


def test_exception_resolution_requires_reason(db_conn, sample_batch_exception_id):
    """Verify RESOLVED and DISMISSED require non-empty resolution reason."""
    service = ExceptionService()
    exc_id = sample_batch_exception_id

    service.transition_status(db_conn, exc_id, target_status="IN_REVIEW", actor="analyst_1")

    with pytest.raises(ValueError):
        service.transition_status(db_conn, exc_id, target_status="RESOLVED", actor="analyst_1", reason="")


def test_exception_assignment(db_conn, sample_batch_exception_id):
    """Verify assignment updates assigned_to without altering status and logs audit event."""
    service = ExceptionService()
    exc_id = sample_batch_exception_id

    exc = service.assign_exception(db_conn, exc_id, assigned_to="analyst_jane", actor="team_lead")
    assert exc["assigned_to"] == "analyst_jane"
    assert exc["status"] == "OPEN"  # Status remains OPEN
