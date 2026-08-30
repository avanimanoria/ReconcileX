"""Evaluation module comparing reconciliation engine results with truth ledger."""

from typing import List, Optional

from .models import (
    AuditEntry,
    EvaluationComparison,
    EvaluationReport,
    MatchStatus,
    ReconcileResult,
    ReconciliationBatchResult,
    TruthRecord,
)

KNOWN_BASELINE_LIMITATIONS = [
    "Does not validate settlement timing / delay (e.g. TG-005).",
    "Does not validate bank-credit amount / amount variance (e.g. TG-007).",
    "Does not validate fee, GST, or refund-adjusted net amount equations (e.g. TG-003, TG-011 pass purely on references).",
]


def evaluate_results(
    batch_result: ReconciliationBatchResult,
    truth_records: List[TruthRecord],
) -> EvaluationReport:
    """Compare engine batch results and audit logs against ground-truth ledger."""
    results_by_settlement = {
        r.settlement_id: r for r in batch_result.results if r.settlement_id
    }
    results_by_payment = {
        r.payment_id: r for r in batch_result.results if r.payment_id
    }

    duplicate_audit_events = {
        entry.details.get("payment_id") or entry.entity_id: entry
        for entry in batch_result.audit_logs
        if entry.event_type == "DUPLICATE_EVENT"
    }

    comparisons: List[EvaluationComparison] = []
    exact_matches = 0

    for truth in truth_records:
        # Find corresponding result by settlement or payment
        res: Optional[ReconcileResult] = None
        if truth.settlement_record and truth.settlement_record != "NONE":
            res = results_by_settlement.get(truth.settlement_record)
        if not res and truth.payment_record and truth.payment_record != "NONE":
            clean_pay_id = truth.payment_record.replace(" twice", "").strip()
            res = results_by_payment.get(clean_pay_id)

        actual_display = res.display_result if res else "NOT_FOUND"

        # Check special case: AUTO_MATCH + DUPLICATE_AUDIT
        if "DUPLICATE_AUDIT" in truth.expected_system_result:
            has_dup_audit = any(
                entry.event_type == "DUPLICATE_EVENT" for entry in batch_result.audit_logs
            )
            if res and res.match_status == MatchStatus.AUTO_MATCH and has_dup_audit:
                actual_display = "AUTO_MATCH + DUPLICATE_AUDIT"

        is_match = (actual_display == truth.expected_system_result)

        notes = ""
        if not is_match:
            if truth.truth_group_id == "TG-005":
                notes = "Known baseline limitation: settlement delay not validated in baseline."
            elif truth.truth_group_id == "TG-007":
                notes = "Known baseline limitation: amount variance not validated in baseline."
            else:
                notes = f"Engine produced '{actual_display}' vs expected '{truth.expected_system_result}'."

        if is_match:
            exact_matches += 1

        comparisons.append(
            EvaluationComparison(
                truth_group_id=truth.truth_group_id,
                scenario=truth.scenario,
                payment_id=res.payment_id if res else truth.payment_record,
                settlement_id=res.settlement_id if res else truth.settlement_record,
                bank_txn_id=res.bank_txn_id if res else truth.bank_record,
                expected_result=truth.expected_system_result,
                actual_result=actual_display,
                is_match=is_match,
                notes=notes,
            )
        )

    total = len(truth_records)
    mismatches = total - exact_matches
    accuracy = (exact_matches / total * 100.0) if total > 0 else 0.0

    return EvaluationReport(
        total_scenarios=total,
        exact_matches=exact_matches,
        mismatches=mismatches,
        accuracy=accuracy,
        comparisons=comparisons,
        known_baseline_limitations=KNOWN_BASELINE_LIMITATIONS,
    )
