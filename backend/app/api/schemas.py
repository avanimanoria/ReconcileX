"""Pydantic request and response schemas for ReconcileX FastAPI layer."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic envelope for paginated collections."""
    items: List[T]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    """Health check status response."""
    status: str
    engine_version: str
    database: str


class BatchResponse(BaseModel):
    """Reconciliation batch metadata response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_number: str
    content_hash: str
    status: str
    engine_version: str
    total_payments: int
    total_settlements: int
    total_bank_credits: int
    total_refunds: int
    auto_match_count: int
    exception_count: int
    disposition: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: Optional[datetime] = None
    processing_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ReconcileResultResponse(BaseModel):
    """Individual reconciliation result response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    rule_version: str
    payment_id: Optional[str] = None
    settlement_id: Optional[str] = None
    bank_txn_id: Optional[str] = None
    refund_id: Optional[str] = None
    match_status: str
    exception_type: Optional[str] = None
    reason: str
    financial_evidence: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ExceptionResponse(BaseModel):
    """Reconciliation exception item response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    reconciliation_result_id: UUID
    category: str
    priority: str
    status: str
    assigned_to: Optional[str] = None
    resolution_reason: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    payment_id: Optional[str] = None
    settlement_id: Optional[str] = None


class ExceptionDetailResponse(ExceptionResponse):
    """Detailed exception response with linked financial evidence and raw match details."""
    bank_txn_id: Optional[str] = None
    engine_reason: Optional[str] = None
    financial_evidence: Dict[str, Any] = Field(default_factory=dict)


class ExceptionPatchRequest(BaseModel):
    """Human-directed exception mutation request."""
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(..., min_length=1, description="Mandatory identifier of human actor performing action")
    status: Optional[str] = Field(None, description="Target lifecycle status (IN_REVIEW, RESOLVED, DISMISSED)")
    assigned_to: Optional[str] = Field(None, description="Analyst identifier to assign exception to")
    resolution_reason: Optional[str] = Field(None, description="Mandatory reason when status is RESOLVED or DISMISSED")

    @field_validator("actor")
    @classmethod
    def validate_actor(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("actor field must not be empty.")
        return v.strip()

    @model_validator(mode="after")
    def validate_patch_fields(self) -> "ExceptionPatchRequest":
        # Reject no-op requests where neither status nor assigned_to is supplied
        if self.status is None and self.assigned_to is None:
            raise ValueError("At least one of 'status' or 'assigned_to' must be provided for exception update.")

        if self.status:
            target = self.status.upper()
            if target in ("RESOLVED", "DISMISSED"):
                if not self.resolution_reason or not self.resolution_reason.strip():
                    raise ValueError(f"resolution_reason is mandatory when transitioning status to '{target}'.")

        return self


class AuditEventResponse(BaseModel):
    """Immutable audit event response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_sequence: int
    batch_id: Optional[UUID] = None
    exception_id: Optional[UUID] = None
    event_type: str
    entity_type: str
    entity_id: str
    actor: str
    action: str
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# Re-export AI explainer schemas for clean unified access
from backend.app.ai.schemas import (
    AIExplanationRequest,
    AIExplanationResponse,
    CalculationSummary,
    EvidenceItem,
    ModelMetadata,
    ValidationMetadata,
)

