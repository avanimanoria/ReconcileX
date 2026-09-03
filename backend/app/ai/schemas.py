"""Pydantic schemas for the Grounded Exception Explainer AI module."""

from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AIExplanationRequest(BaseModel):
    """Safe, optional request body for requesting an AI explanation."""
    model_config = ConfigDict(extra="forbid")

    actor: Optional[str] = Field(
        None,
        description="Optional identifier of the operator requesting explanation for audit trail",
    )


class EvidenceItem(BaseModel):
    """An individual piece of grounded evidence tied to a retrieved source record."""
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(..., description="Entity type, e.g. payment, settlement, bank_credit, refund")
    source_id: str = Field(..., description="Canonical ID of the source record")
    claim: str = Field(..., description="Factual, grounded statement citing this source record")


class CalculationSummary(BaseModel):
    """Deterministic financial calculations associated with the exception."""
    model_config = ConfigDict(extra="forbid")

    captured_amount: Optional[str] = None
    refund_amount: Optional[str] = None
    fee_amount: Optional[str] = None
    gst_amount: Optional[str] = None
    expected_net: Optional[str] = None
    settlement_net_amount: Optional[str] = None
    bank_credit_amount: Optional[str] = None
    variance_amount: Optional[str] = None
    currency: str = "INR"


class ModelMetadata(BaseModel):
    """Metadata describing the AI model/provider invocation."""
    model_config = ConfigDict(extra="forbid")

    provider: str
    model_id: str
    model_version: str
    prompt_version: str = "ai-explanation-v1"


class ValidationMetadata(BaseModel):
    """Validation results verifying strict grounding and schema compliance."""
    model_config = ConfigDict(extra="forbid")

    schema_valid: bool = True
    evidence_ids_valid: bool = True
    grounding_valid: bool = True
    fallback_used: bool = False
    fallback_reason: Optional[str] = None


class AIExplanationResponse(BaseModel):
    """Strongly-typed advisory response returned to analyst."""
    model_config = ConfigDict(extra="forbid")

    exception_id: str
    status: str = "VALID"
    advisory_only: bool = True
    model: ModelMetadata
    summary: str
    evidence: List[EvidenceItem]
    calculation_summary: CalculationSummary
    suggested_next_step: str
    unknowns: List[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    validation: ValidationMetadata

    @field_validator("advisory_only")
    @classmethod
    def ensure_advisory_only(cls, v: bool) -> bool:
        if not v:
            raise ValueError("advisory_only must always be True.")
        return True
