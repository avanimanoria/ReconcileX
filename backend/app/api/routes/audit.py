"""Immutable audit events read-only query API routes."""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
import psycopg

from backend.app.api.deps import get_audit_repo, get_db
from backend.app.api.schemas import AuditEventResponse, PaginatedResponse
from backend.app.db.repositories.audit_repo import AuditRepository

router = APIRouter(prefix="/audit-events", tags=["Audit Events"])


@router.get("", response_model=PaginatedResponse[AuditEventResponse], status_code=status.HTTP_200_OK)
def list_audit_events(
    batch_id: Optional[UUID] = Query(None, description="Filter audit events by batch ID"),
    exception_id: Optional[UUID] = Query(None, description="Filter audit events by exception ID"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (BATCH, EXCEPTION, PAYMENT, etc.)"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset items"),
    db: psycopg.Connection = Depends(get_db),
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> PaginatedResponse[AuditEventResponse]:
    """Retrieve append-only audit events in chronological order with optional filters."""
    items, total = audit_repo.query_audit_events(
        conn=db,
        batch_id=str(batch_id) if batch_id else None,
        exception_id=str(exception_id) if exception_id else None,
        entity_type=entity_type.upper() if entity_type else None,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse[AuditEventResponse](
        items=[AuditEventResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
