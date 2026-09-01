"""Exception lifecycle and workflow management service for ReconcileX."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import psycopg

from backend.app.db.repositories.audit_repo import AuditRepository
from backend.app.db.repositories.recon_repo import ReconRepository


class InvalidStateTransitionError(Exception):
    """Raised when an invalid exception status transition is requested."""


class ExceptionNotFoundError(Exception):
    """Raised when an exception ID is not found in database."""


VALID_TRANSITIONS = {
    "OPEN": {"IN_REVIEW", "DISMISSED"},
    "IN_REVIEW": {"RESOLVED", "DISMISSED"},
    "RESOLVED": {"IN_REVIEW"},
    "DISMISSED": {"IN_REVIEW"},
}


class ExceptionService:
    """Manages exception lifecycle transitions, assignments, and resolution audits."""

    def __init__(
        self,
        recon_repo: Optional[ReconRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
    ) -> None:
        self.recon_repo = recon_repo or ReconRepository()
        self.audit_repo = audit_repo or AuditRepository()

    def get_exception(self, conn: psycopg.Connection, exception_id: str) -> Dict[str, Any]:
        """Fetch exception details."""
        exc = self.recon_repo.get_exception_by_id(conn, exception_id)
        if not exc:
            raise ExceptionNotFoundError(f"Exception '{exception_id}' not found.")
        return exc

    def list_exceptions(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List exceptions for a batch."""
        return self.recon_repo.list_exceptions_by_batch(conn, batch_id, status=status, priority=priority)

    def assign_exception(
        self,
        conn: psycopg.Connection,
        exception_id: str,
        assigned_to: str,
        actor: str = "SYSTEM",
    ) -> Dict[str, Any]:
        """Assign an exception to an analyst (metadata update without status transition)."""
        with conn.transaction():
            exc = self.recon_repo.get_exception_for_update(conn, exception_id)
            if not exc:
                raise ExceptionNotFoundError(f"Exception '{exception_id}' not found.")

            before_state = {
                "status": exc["status"],
                "assigned_to": exc["assigned_to"],
            }
            after_state = {
                "status": exc["status"],
                "assigned_to": assigned_to,
            }

            self.recon_repo.update_exception(
                conn,
                exception_id=exception_id,
                status=exc["status"],
                assigned_to=assigned_to,
                resolution_reason=exc["resolution_reason"],
                resolved_by=exc["resolved_by"],
                resolved_at=exc["resolved_at"],
            )

            self.audit_repo.insert_audit_event(
                conn,
                batch_id=str(exc["batch_id"]),
                exception_id=exception_id,
                event_type="EXCEPTION_ASSIGNED",
                entity_type="EXCEPTION",
                entity_id=exception_id,
                actor=actor,
                action="ASSIGN_EXCEPTION",
                reason=f"Assigned exception to {assigned_to}.",
                before_state=before_state,
                after_state=after_state,
            )

            return self.recon_repo.get_exception_by_id(conn, exception_id)

    def transition_status(
        self,
        conn: psycopg.Connection,
        exception_id: str,
        target_status: str,
        actor: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically transition exception state according to the approved state machine."""
        target_status = target_status.upper()
        if not actor or not actor.strip():
            raise ValueError("An actor identifier is required for all state transitions.")

        with conn.transaction():
            exc = self.recon_repo.get_exception_for_update(conn, exception_id)
            if not exc:
                raise ExceptionNotFoundError(f"Exception '{exception_id}' not found.")

            current_status = exc["status"]
            allowed_next = VALID_TRANSITIONS.get(current_status, set())

            if target_status not in allowed_next:
                raise InvalidStateTransitionError(
                    f"Cannot transition exception from '{current_status}' to '{target_status}'. "
                    f"Allowed transitions from '{current_status}': {sorted(list(allowed_next))}"
                )

            # Validation: RESOLVED and DISMISSED require resolution_reason
            if target_status in ("RESOLVED", "DISMISSED"):
                if not reason or not reason.strip():
                    raise ValueError(f"Transitioning to '{target_status}' requires a non-empty resolution reason.")

            resolved_by = None
            resolved_at = None
            resolution_reason = None

            if target_status in ("RESOLVED", "DISMISSED"):
                resolved_by = actor
                resolved_at = datetime.now(timezone.utc)
                resolution_reason = reason
            elif target_status == "IN_REVIEW" and current_status in ("RESOLVED", "DISMISSED"):
                # Reopening clears resolution metadata
                resolved_by = None
                resolved_at = None
                resolution_reason = None
            else:
                resolution_reason = exc["resolution_reason"]

            before_state = {
                "status": current_status,
                "assigned_to": exc["assigned_to"],
                "resolution_reason": exc["resolution_reason"],
                "resolved_by": exc["resolved_by"],
                "resolved_at": exc["resolved_at"].isoformat() if exc["resolved_at"] else None,
            }

            after_state = {
                "status": target_status,
                "assigned_to": exc["assigned_to"],
                "resolution_reason": resolution_reason,
                "resolved_by": resolved_by,
                "resolved_at": resolved_at.isoformat() if resolved_at else None,
            }

            self.recon_repo.update_exception(
                conn,
                exception_id=exception_id,
                status=target_status,
                assigned_to=exc["assigned_to"],
                resolution_reason=resolution_reason,
                resolved_by=resolved_by,
                resolved_at=resolved_at,
            )

            self.audit_repo.insert_audit_event(
                conn,
                batch_id=str(exc["batch_id"]),
                exception_id=exception_id,
                event_type=f"EXCEPTION_STATUS_{target_status}",
                entity_type="EXCEPTION",
                entity_id=exception_id,
                actor=actor,
                action=f"TRANSITION_TO_{target_status}",
                reason=reason or f"Transitioned status from {current_status} to {target_status}.",
                before_state=before_state,
                after_state=after_state,
            )

            return self.recon_repo.get_exception_by_id(conn, exception_id)
