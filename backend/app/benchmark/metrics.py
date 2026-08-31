"""Evaluation metrics calculation for ReconcileX Benchmark."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.models import (
    Dataset,
    MatchStatus,
    ReconcileResult,
    ReconciliationBatchResult,
    TruthRecord,
)


@dataclass
class ScenarioEvaluationDetail:
    truth_group_id: str
    scenario: str
    payment_id: Optional[str]
    settlement_id: Optional[str]
    expected_result: str
    actual_result: str
    is_exact_match: bool
    is_unsafe_auto_match: bool


@dataclass
class BenchmarkMetrics:
    split: str
    engine: str
    seed: Optional[int] = None
    generator_version: Optional[str] = None
    total_scenarios: int = 0
    raw_payment_rows: int = 0
    unique_payments: int = 0
    settlements_count: int = 0
    bank_credits_count: int = 0
    refunds_count: int = 0
    quarantined_rows: int = 0
    duplicate_audits: int = 0
    auto_matches: int = 0
    exceptions: int = 0
    exact_agreement: int = 0
    accuracy: float = 0.0
    auto_match_precision: float = 0.0
    auto_match_recall: float = 0.0
    exception_precision: float = 0.0
    exception_recall: float = 0.0
    unsafe_auto_matches: int = 0
    exception_breakdown_truth: Dict[str, int] = field(default_factory=dict)
    exception_breakdown_actual: Dict[str, int] = field(default_factory=dict)
    details: List[ScenarioEvaluationDetail] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    scenarios_per_second: float = 0.0
    input_rows_per_second: float = 0.0


def calculate_benchmark_metrics(
    split: str,
    engine: str,
    dataset: Dataset,
    batch_result: ReconciliationBatchResult,
    truth_records: List[TruthRecord],
    raw_payment_count: int,
    elapsed_seconds: float = 0.0,
    seed: Optional[int] = None,
    generator_version: Optional[str] = None,
) -> BenchmarkMetrics:
    """Compute comprehensive benchmark accuracy and throughput metrics."""
    results_by_settlement: Dict[str, ReconcileResult] = {
        r.settlement_id: r for r in batch_result.results if r.settlement_id
    }
    results_by_payment: Dict[str, ReconcileResult] = {
        r.payment_id: r for r in batch_result.results if r.payment_id
    }

    duplicate_audited_payments = {
        entry.details.get("payment_id") or entry.entity_id
        for entry in batch_result.audit_logs
        if entry.event_type == "DUPLICATE_EVENT"
    }

    total_scenarios = len(truth_records)
    exact_agreement_count = 0
    unsafe_auto_match_count = 0

    truth_auto_matches = 0
    truth_exceptions = 0
    actual_auto_matches = 0
    actual_exceptions = 0

    correct_auto_matches = 0
    correct_exceptions = 0

    truth_exc_breakdown: Dict[str, int] = {}
    actual_exc_breakdown: Dict[str, int] = {}
    details: List[ScenarioEvaluationDetail] = []

    for truth in truth_records:
        expected = truth.expected_system_result
        is_truth_auto = "AUTO_MATCH" in expected

        if is_truth_auto:
            truth_auto_matches += 1
        else:
            truth_exceptions += 1
            cat = expected.replace("EXCEPTION: ", "").strip()
            truth_exc_breakdown[cat] = truth_exc_breakdown.get(cat, 0) + 1

        # Match with actual engine result
        res: Optional[ReconcileResult] = None
        if truth.settlement_record and truth.settlement_record != "NONE":
            res = results_by_settlement.get(truth.settlement_record)
        if not res and truth.payment_record and truth.payment_record != "NONE":
            clean_pay_id = truth.payment_record.replace(" twice", "").strip()
            res = results_by_payment.get(clean_pay_id)

        actual_display = res.display_result if res else "NOT_FOUND"

        # Check special case: AUTO_MATCH + DUPLICATE_AUDIT
        if "DUPLICATE_AUDIT" in expected:
            clean_pay_id = truth.payment_record.replace(" twice", "").strip()
            has_dup = (
                clean_pay_id in duplicate_audited_payments
                or any(entry.event_type == "DUPLICATE_EVENT" for entry in batch_result.audit_logs)
            )
            if res and res.match_status == MatchStatus.AUTO_MATCH and has_dup:
                actual_display = "AUTO_MATCH + DUPLICATE_AUDIT"

        is_actual_auto = "AUTO_MATCH" in actual_display
        if is_actual_auto:
            actual_auto_matches += 1
        else:
            actual_exceptions += 1
            act_cat = actual_display.replace("EXCEPTION: ", "").strip()
            actual_exc_breakdown[act_cat] = actual_exc_breakdown.get(act_cat, 0) + 1

        is_exact = (actual_display == expected)
        if is_exact:
            exact_agreement_count += 1

        # Check unsafe auto match: actual is AUTO_MATCH but truth is EXCEPTION
        is_unsafe = (is_actual_auto and not is_truth_auto)
        if is_unsafe:
            unsafe_auto_match_count += 1

        # Precision / recall components
        if is_truth_auto and is_actual_auto:
            correct_auto_matches += 1

        if not is_truth_auto and not is_actual_auto and (actual_display == expected):
            correct_exceptions += 1

        details.append(
            ScenarioEvaluationDetail(
                truth_group_id=truth.truth_group_id,
                scenario=truth.scenario,
                payment_id=res.payment_id if res else truth.payment_record,
                settlement_id=res.settlement_id if res else truth.settlement_record,
                expected_result=expected,
                actual_result=actual_display,
                is_exact_match=is_exact,
                is_unsafe_auto_match=is_unsafe,
            )
        )

    accuracy = (exact_agreement_count / total_scenarios * 100.0) if total_scenarios > 0 else 0.0
    auto_prec = (correct_auto_matches / actual_auto_matches) if actual_auto_matches > 0 else 0.0
    auto_rec = (correct_auto_matches / truth_auto_matches) if truth_auto_matches > 0 else 0.0
    exc_prec = (correct_exceptions / actual_exceptions) if actual_exceptions > 0 else 0.0
    exc_rec = (correct_exceptions / truth_exceptions) if truth_exceptions > 0 else 0.0

    # Total input rows = raw payments + settlements + bank credits + refunds
    total_input_rows = raw_payment_count + len(dataset.settlements) + len(dataset.bank_credits) + len(dataset.refunds)
    scenarios_per_sec = (total_scenarios / elapsed_seconds) if elapsed_seconds > 0 else 0.0
    rows_per_sec = (total_input_rows / elapsed_seconds) if elapsed_seconds > 0 else 0.0

    return BenchmarkMetrics(
        split=split,
        engine=engine,
        seed=seed,
        generator_version=generator_version,
        total_scenarios=total_scenarios,
        raw_payment_rows=raw_payment_count,
        unique_payments=len(dataset.payments),
        settlements_count=len(dataset.settlements),
        bank_credits_count=len(dataset.bank_credits),
        refunds_count=len(dataset.refunds),
        quarantined_rows=len(dataset.quarantined_rows),
        duplicate_audits=len([a for a in dataset.audit_logs if a.event_type == "DUPLICATE_EVENT"]),
        auto_matches=actual_auto_matches,
        exceptions=actual_exceptions,
        exact_agreement=exact_agreement_count,
        accuracy=accuracy,
        auto_match_precision=auto_prec,
        auto_match_recall=auto_rec,
        exception_precision=exc_prec,
        exception_recall=exc_rec,
        unsafe_auto_matches=unsafe_auto_match_count,
        exception_breakdown_truth=truth_exc_breakdown,
        exception_breakdown_actual=actual_exc_breakdown,
        details=details,
        elapsed_seconds=elapsed_seconds,
        scenarios_per_second=scenarios_per_sec,
        input_rows_per_second=rows_per_sec,
    )
