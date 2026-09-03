"""Grounded Exception Explainer Service coordinating evidence retrieval, validation, and audit."""

from decimal import Decimal
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set
import urllib.error
import psycopg



from backend.app.ai.adapter import BaseLLMAdapter, get_configured_llm_adapter
from backend.app.ai.fallback import generate_deterministic_fallback
from backend.app.ai.prompt import build_user_prompt
from backend.app.ai.schemas import (
    AIExplanationResponse,
    CalculationSummary,
    EvidenceItem,
    ModelMetadata,
    ValidationMetadata,
)
from backend.app.ai.validator import validate_grounding
from backend.app.db.repositories.audit_repo import AuditRepository
from backend.app.db.repositories.recon_repo import ReconRepository
from backend.app.services.exception_service import ExceptionNotFoundError

logger = logging.getLogger(__name__)


class GroundedExceptionExplainerService:
    """Service providing grounded, read-only AI advisory explanations for exceptions."""

    def __init__(
        self,
        recon_repo: Optional[ReconRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        llm_adapter: Optional[BaseLLMAdapter] = None,
    ) -> None:
        self.recon_repo = recon_repo or ReconRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.llm_adapter = llm_adapter

    def get_adapter(self) -> Optional[BaseLLMAdapter]:
        """Return configured adapter or look up dynamically from environment."""
        if self.llm_adapter is not None:
            return self.llm_adapter
        return get_configured_llm_adapter()

    def assemble_evidence_payload(
        self,
        conn: psycopg.Connection,
        exception: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Retrieve related records server-side and construct deterministic evidence."""
        batch_id = str(exception["batch_id"])
        payment_id = exception.get("payment_id")
        settlement_id = exception.get("settlement_id")
        bank_txn_id = exception.get("bank_txn_id")
        refund_id = exception.get("refund_id")
        fin_evidence = exception.get("financial_evidence") or {}

        source_records: Dict[str, Any] = {}
        allowed_source_ids: Set[str] = set()

        with conn.cursor() as cur:
            # 1. Payment
            if payment_id:
                cur.execute(
                    "SELECT payment_id, order_id, captured_amount, status, captured_at FROM payments WHERE batch_id = %s AND payment_id = %s LIMIT 1;",
                    (batch_id, payment_id),
                )
                row = cur.fetchone()
                if row:
                    source_records["payment"] = {
                        "payment_id": row["payment_id"],
                        "order_id": row["order_id"],
                        "captured_amount": str(row["captured_amount"]),
                        "status": row["status"],
                        "captured_at": row["captured_at"].isoformat() if row.get("captured_at") else None,
                    }
                    allowed_source_ids.add(row["payment_id"])

            # 2. Settlement
            if settlement_id:
                cur.execute(
                    "SELECT settlement_id, payment_id, gross_amount, fee_amount, gst_on_fee, net_amount, settlement_status, settled_at FROM settlements WHERE batch_id = %s AND settlement_id = %s LIMIT 1;",
                    (batch_id, settlement_id),
                )
                row = cur.fetchone()
                if row:
                    source_records["settlement"] = {
                        "settlement_id": row["settlement_id"],
                        "payment_id": row["payment_id"],
                        "gross_amount": str(row["gross_amount"]),
                        "fee_amount": str(row["fee_amount"]),
                        "gst_on_fee": str(row["gst_on_fee"]),
                        "net_amount": str(row["net_amount"]),
                        "status": row["settlement_status"],
                        "settled_at": row["settled_at"].isoformat() if row.get("settled_at") else None,
                    }
                    allowed_source_ids.add(row["settlement_id"])

            # 3. Bank credit
            if bank_txn_id or settlement_id:
                if bank_txn_id:
                    cur.execute(
                        "SELECT bank_txn_id, credit_amount, credited_at, narration FROM bank_credits WHERE batch_id = %s AND bank_txn_id = %s LIMIT 1;",
                        (batch_id, bank_txn_id),
                    )
                else:
                    cur.execute(
                        "SELECT bank_txn_id, credit_amount, credited_at, narration FROM bank_credits WHERE batch_id = %s AND narration LIKE %s LIMIT 1;",
                        (batch_id, f"%{settlement_id}%"),
                    )
                row = cur.fetchone()
                if row:
                    source_records["bank_credit"] = {
                        "bank_txn_id": row["bank_txn_id"],
                        "credit_amount": str(row["credit_amount"]),
                        "credited_at": row["credited_at"].isoformat() if row.get("credited_at") else None,
                        "narration": row["narration"],
                    }
                    allowed_source_ids.add(row["bank_txn_id"])

            # 4. Refund
            if refund_id or payment_id:
                if refund_id:
                    cur.execute(
                        "SELECT refund_id, payment_id, refund_amount, refund_status, refunded_at FROM refunds WHERE batch_id = %s AND refund_id = %s LIMIT 1;",
                        (batch_id, refund_id),
                    )
                else:
                    cur.execute(
                        "SELECT refund_id, payment_id, refund_amount, refund_status, refunded_at FROM refunds WHERE batch_id = %s AND payment_id = %s LIMIT 1;",
                        (batch_id, payment_id),
                    )
                row = cur.fetchone()
                if row:
                    source_records["refund"] = {
                        "refund_id": row["refund_id"],
                        "payment_id": row["payment_id"],
                        "refund_amount": str(row["refund_amount"]),
                        "refund_status": row["refund_status"],
                        "refunded_at": row["refunded_at"].isoformat() if row.get("refunded_at") else None,
                    }
                    allowed_source_ids.add(row["refund_id"])

        # Determine calculation summary fields directly from deterministic financial evidence
        captured_amt = fin_evidence.get("captured_amount")
        refund_amt = fin_evidence.get("total_processed_refunds")
        fee_amt = fin_evidence.get("fee_amount")
        gst_amt = fin_evidence.get("gst_on_fee")
        expected_net = fin_evidence.get("expected_net")
        settlement_net = fin_evidence.get("settlement_net_amount")
        bank_credit_amt = fin_evidence.get("bank_credit_amount")

        # Fall back to source records if not in financial_evidence dict
        if captured_amt is None and "payment" in source_records:
            captured_amt = source_records["payment"]["captured_amount"]
        if fee_amt is None and "settlement" in source_records:
            fee_amt = source_records["settlement"]["fee_amount"]
        if gst_amt is None and "settlement" in source_records:
            gst_amt = source_records["settlement"]["gst_on_fee"]
        if settlement_net is None and "settlement" in source_records:
            settlement_net = source_records["settlement"]["net_amount"]
        if bank_credit_amt is None and "bank_credit" in source_records:
            bank_credit_amt = source_records["bank_credit"]["credit_amount"]
        if refund_amt is None and "refund" in source_records:
            refund_amt = source_records["refund"]["refund_amount"]

        variance_amount: Optional[str] = None
        if expected_net is not None and bank_credit_amt is not None:
            try:
                diff = abs(Decimal(str(expected_net)) - Decimal(str(bank_credit_amt)))
                variance_amount = f"{diff:.2f}"
            except Exception:
                pass
        elif expected_net is not None and settlement_net is not None:
            try:
                diff = abs(Decimal(str(expected_net)) - Decimal(str(settlement_net)))
                variance_amount = f"{diff:.2f}"
            except Exception:
                pass

        def _fmt(val: Any) -> Optional[str]:
            if val is None:
                return None
            try:
                return f"{Decimal(str(val)):.2f}"
            except Exception:
                return str(val)

        calculations = {
            "captured_amount": _fmt(captured_amt),
            "refund_amount": _fmt(refund_amt) if refund_amt is not None else "0.00",
            "fee_amount": _fmt(fee_amt),
            "gst_amount": _fmt(gst_amt),
            "expected_net": _fmt(expected_net),
            "settlement_net_amount": _fmt(settlement_net),
            "bank_credit_amount": _fmt(bank_credit_amt),
            "variance_amount": variance_amount,
            "currency": "INR",
        }

        return {
            "exception": {
                "id": str(exception["id"]),
                "batch_id": batch_id,
                "category": exception["category"],
                "priority": exception["priority"],
                "status": exception["status"],
                "engine_reason": exception.get("engine_reason"),
            },
            "source_records": source_records,
            "allowed_source_ids": sorted(list(allowed_source_ids)),
            "calculations": calculations,
        }

    def explain_exception(
        self,
        conn: psycopg.Connection,
        exception_id: str,
        actor: Optional[str] = None,
    ) -> AIExplanationResponse:
        """Generate a grounded, read-only advisory explanation for a given exception."""
        # 1. Fetch exception details (Read-only)
        exc = self.recon_repo.get_exception_by_id(conn, exception_id)
        if not exc:
            raise ExceptionNotFoundError(f"Exception '{exception_id}' not found.")

        # 2. Assemble deterministic evidence payload
        evidence_payload = self.assemble_evidence_payload(conn, exc)
        allowed_source_ids = set(evidence_payload["allowed_source_ids"])
        server_calcs = evidence_payload["calculations"]

        # 3. Check model adapter availability
        adapter = self.get_adapter()
        response: Optional[AIExplanationResponse] = None

        if adapter is None:
            response = generate_deterministic_fallback(
                exception_id=exception_id,
                evidence_payload=evidence_payload,
                fallback_reason="NO_LLM_KEY_CONFIGURED",
            )
        else:
            user_prompt = build_user_prompt(exception_id, evidence_payload)
            try:
                raw_text = adapter.generate(user_prompt)
                # Strip markdown code blocks if the model enclosed response in ```json ... ```
                cleaned_text = raw_text.strip()
                if cleaned_text.startswith("```"):
                    lines = cleaned_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned_text = "\n".join(lines).strip()

                raw_json = json.loads(cleaned_text)

                # Grounding and safety validation
                is_valid, failure_reason = validate_grounding(
                    raw_response=raw_json,
                    allowed_source_ids=allowed_source_ids,
                    server_calculations=server_calcs,
                )

                if not is_valid:
                    response = generate_deterministic_fallback(
                        exception_id=exception_id,
                        evidence_payload=evidence_payload,
                        fallback_reason=f"VALIDATION_FAILURE: {failure_reason}",
                    )
                else:
                    # Model validated successfully
                    model_meta = adapter.get_metadata()
                    calc_dict = raw_json.get("calculation_summary", {})
                    response = AIExplanationResponse(
                        exception_id=exception_id,
                        status="VALID",
                        advisory_only=True,
                        model=model_meta,
                        summary=raw_json["summary"],
                        evidence=[EvidenceItem(**item) for item in raw_json.get("evidence", [])],
                        calculation_summary=CalculationSummary(**calc_dict),
                        suggested_next_step=raw_json.get("suggested_next_step", ""),
                        unknowns=raw_json.get("unknowns", []),
                        confidence=float(raw_json.get("confidence", 0.0)),
                        validation=ValidationMetadata(
                            schema_valid=True,
                            evidence_ids_valid=True,
                            grounding_valid=True,
                            fallback_used=False,
                            fallback_reason=None,
                        ),
                    )
            except json.JSONDecodeError:
                response = generate_deterministic_fallback(
                    exception_id=exception_id,
                    evidence_payload=evidence_payload,
                    fallback_reason="MALFORMED_JSON_RETURNED",
                )
            except (TimeoutError, urllib.error.URLError) as e:
                response = generate_deterministic_fallback(
                    exception_id=exception_id,
                    evidence_payload=evidence_payload,
                    fallback_reason=f"MODEL_TIMEOUT: {str(e)}",
                )
            except Exception as e:
                logger.warning("Unexpected error during LLM explanation generation: %s", str(e))
                response = generate_deterministic_fallback(
                    exception_id=exception_id,
                    evidence_payload=evidence_payload,
                    fallback_reason=f"MODEL_INVOCATION_ERROR: {type(e).__name__}",
                )

        # 4. Create immutable append-only audit event
        output_hash = hashlib.sha256(response.summary.encode("utf-8")).hexdigest()
        audit_metadata = {
            "model": response.model.model_dump(),
            "validation": response.validation.model_dump(),
            "cited_evidence_ids": [e.source_id for e in response.evidence],
            "output_hash": output_hash,
            "confidence": response.confidence,
        }

        self.audit_repo.insert_audit_event(
            conn=conn,
            batch_id=str(exc["batch_id"]),
            exception_id=exception_id,
            event_type="AI_EXPLANATION_GENERATED",
            entity_type="EXCEPTION",
            entity_id=exception_id,
            actor=actor or "ANALYST_COPILOT",
            action="GENERATE_AI_EXPLANATION",
            reason="Generated grounded advisory explanation for reconciliation exception.",
            metadata=audit_metadata,
        )

        return response
