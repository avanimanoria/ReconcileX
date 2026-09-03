"""Provider-independent deterministic fallback explainer for ReconcileX."""

from typing import Any, Dict, List, Optional
from backend.app.ai.prompt import PROMPT_VERSION
from backend.app.ai.schemas import (
    AIExplanationResponse,
    CalculationSummary,
    EvidenceItem,
    ModelMetadata,
    ValidationMetadata,
)


def generate_deterministic_fallback(
    exception_id: str,
    evidence_payload: Dict[str, Any],
    fallback_reason: str,
) -> AIExplanationResponse:
    """Produce a guaranteed, grounded advisory explanation directly from deterministic evidence.

    This fallback is invoked when no API key is configured, model fails/times out,
    or model response violates grounding or schema constraints.
    """
    exc_meta = evidence_payload.get("exception", {})
    category = exc_meta.get("category", "UNMATCHED")
    priority = exc_meta.get("priority", "MEDIUM")
    engine_reason = exc_meta.get("engine_reason") or "Deterministic rule mismatch identified by reconciliation engine."

    calc_data = evidence_payload.get("calculations", {})
    calc_summary = CalculationSummary(
        captured_amount=calc_data.get("captured_amount"),
        refund_amount=calc_data.get("refund_amount"),
        fee_amount=calc_data.get("fee_amount"),
        gst_amount=calc_data.get("gst_amount"),
        expected_net=calc_data.get("expected_net"),
        settlement_net_amount=calc_data.get("settlement_net_amount"),
        bank_credit_amount=calc_data.get("bank_credit_amount"),
        variance_amount=calc_data.get("variance_amount"),
        currency=calc_data.get("currency", "INR"),
    )

    evidence_items: List[EvidenceItem] = []
    source_records = evidence_payload.get("source_records", {})

    if source_records.get("payment"):
        p = source_records["payment"]
        evidence_items.append(
            EvidenceItem(
                source_type="payment",
                source_id=p.get("payment_id", "UNKNOWN"),
                claim=f"Payment recorded with status '{p.get('status')}' and captured amount INR {p.get('captured_amount')}.",
            )
        )

    if source_records.get("settlement"):
        s = source_records["settlement"]
        evidence_items.append(
            EvidenceItem(
                source_type="settlement",
                source_id=s.get("settlement_id", "UNKNOWN"),
                claim=f"Settlement net amount INR {s.get('net_amount')} (fee INR {s.get('fee_amount')}, GST INR {s.get('gst_on_fee')}).",
            )
        )

    if source_records.get("bank_credit"):
        b = source_records["bank_credit"]
        evidence_items.append(
            EvidenceItem(
                source_type="bank_credit",
                source_id=b.get("bank_txn_id", "UNKNOWN"),
                claim=f"Bank credit received for INR {b.get('credit_amount')} with narration '{b.get('narration')}'.",
            )
        )

    if source_records.get("refund"):
        r = source_records["refund"]
        evidence_items.append(
            EvidenceItem(
                source_type="refund",
                source_id=r.get("refund_id", "UNKNOWN"),
                claim=f"Refund recorded with status '{r.get('refund_status')}' and amount INR {r.get('refund_amount')}.",
            )
        )

    # Contextual category-based summary and suggested next steps
    unknowns: List[str] = []
    if category == "AMOUNT_VARIANCE":
        variance = calc_summary.variance_amount or "an unquantified amount"
        summary = (
            f"Deterministic calculation detected a financial variance of INR {variance}. "
            f"Expected net of INR {calc_summary.expected_net or 'N/A'} does not match "
            f"bank credit of INR {calc_summary.bank_credit_amount or 'N/A'}. {engine_reason}"
        )
        suggested_step = (
            "Verify bank statement narration and inquire with acquiring bank regarding possible unrecorded processing fees or deductions."
        )
        unknowns.append("The root cause of the amount variance is absent from the input dataset records.")
    elif category == "STATUS_CONFLICT":
        summary = (
            f"Payment status prevents automated settlement reconciliation. {engine_reason}"
        )
        suggested_step = (
            "Check payment gateway logs to confirm whether the payment was subsequently captured or officially cancelled."
        )
        unknowns.append("Gateway transaction lifecycle logs outside the batch are not available.")
    elif category == "SETTLEMENT_DELAY":
        summary = (
            f"Settlement timing exceeds the policy window. {engine_reason}"
        )
        suggested_step = (
            "Review processor settlement schedule and verify whether bank holiday or settlement batching caused the delivery delay."
        )
        unknowns.append("Processor operational calendar and batch dispatch schedule are unobserved in this batch.")
    elif category == "MISSING_REFERENCE":
        summary = (
            f"Reference link failure: {engine_reason}"
        )
        suggested_step = (
            "Check for manual bank entries or unstructured bank narrations that might correspond to this settlement."
        )
        unknowns.append("No bank credit record in this batch matched the expected settlement reference.")
    else:
        summary = f"Reconciliation exception categorized as '{category}' ({priority} priority). {engine_reason}"
        suggested_step = "Review linked source entities and verify records manually before taking resolution action."
        unknowns.append("Standard automated rule evaluation flagged this record without automated resolution.")

    return AIExplanationResponse(
        exception_id=exception_id,
        status="VALID",
        advisory_only=True,
        model=ModelMetadata(
            provider="deterministic_fallback",
            model_id="rule-explainer",
            model_version="1.0.0",
            prompt_version=PROMPT_VERSION,
        ),
        summary=summary,
        evidence=evidence_items,
        calculation_summary=calc_summary,
        suggested_next_step=suggested_step,
        unknowns=unknowns,
        confidence=0.95,
        validation=ValidationMetadata(
            schema_valid=True,
            evidence_ids_valid=True,
            grounding_valid=True,
            fallback_used=True,
            fallback_reason=fallback_reason,
        ),
    )
