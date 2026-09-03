"""Reproducible benchmark runner for evaluating Grounded Exception Explainer safety."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.app.ai.validator import validate_grounding



def run_ai_evaluation(cases_path: Optional[Path] = None) -> Dict[str, Any]:
    """Execute evaluation against the labelled test cases and compute metrics."""
    if cases_path is None:
        cases_path = Path(__file__).resolve().parent / "test_cases.json"

    with open(cases_path, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    total_cases = len(cases)
    valid_expected_count = 0
    valid_passed_count = 0
    adversarial_count = 0
    adversarial_blocked_count = 0
    unsupported_claim_escapes = 0

    results_detail = []

    for tc in cases:
        case_id = tc["case_id"]
        ev = tc["evidence_payload"]
        resp = tc["candidate_response"]
        expected_valid = tc["expected_valid"]
        fault = tc.get("adversarial_fault")

        allowed_ids = set(ev.get("allowed_source_ids", []))
        server_calcs = ev.get("calculations", {})

        is_valid, failure_reason = validate_grounding(
            raw_response=resp,
            allowed_source_ids=allowed_ids,
            server_calculations=server_calcs,
        )

        if expected_valid:
            valid_expected_count += 1
            if is_valid:
                valid_passed_count += 1
            else:
                results_detail.append({
                    "case_id": case_id,
                    "status": "FALSE_NEGATIVE_BLOCKED",
                    "reason": failure_reason,
                })
        else:
            adversarial_count += 1
            if not is_valid:
                adversarial_blocked_count += 1
            else:
                unsupported_claim_escapes += 1
                results_detail.append({
                    "case_id": case_id,
                    "status": "UNSUPPORTED_CLAIM_ESCAPED",
                    "fault": fault,
                })

    grounding_valid_rate = (valid_passed_count / valid_expected_count) if valid_expected_count else 1.0
    adversarial_block_rate = (adversarial_blocked_count / adversarial_count) if adversarial_count else 1.0
    unsupported_claim_rate = (unsupported_claim_escapes / total_cases) if total_cases else 0.0
    fallback_rate = (adversarial_blocked_count / total_cases) if total_cases else 0.0

    metrics = {
        "total_cases": total_cases,
        "clean_grounded_cases": valid_expected_count,
        "clean_grounded_pass_rate": round(grounding_valid_rate, 4),
        "adversarial_cases": adversarial_count,
        "adversarial_block_rate": round(adversarial_block_rate, 4),
        "unsupported_claim_escape_rate": round(unsupported_claim_rate, 4),
        "fallback_rate": round(fallback_rate, 4),
        "details": results_detail,
    }

    return metrics


def print_evaluation_report(metrics: Dict[str, Any]) -> None:
    """Print human-readable benchmark evaluation report."""
    print("=" * 65)
    print("      RECONCILEX AI EXCEPTION EXPLAINER EVALUATION REPORT")
    print("=" * 65)
    print(f"Total Test Cases Evaluated:        {metrics['total_cases']}")
    print(f"Grounded Clean Cases:              {metrics['clean_grounded_cases']}")
    print(f"Grounded Clean Pass Rate:          {metrics['clean_grounded_pass_rate'] * 100:.1f}%")
    print(f"Adversarial / Fault Cases:         {metrics['adversarial_cases']}")
    print(f"Adversarial Defense Catch Rate:    {metrics['adversarial_block_rate'] * 100:.1f}%")
    print(f"Unsupported-Claim Escape Rate:     {metrics['unsupported_claim_escape_rate'] * 100:.2f}%")
    print(f"Validator Fallback Trigger Rate:   {metrics['fallback_rate'] * 100:.1f}%")
    print("-" * 65)
    if metrics["details"]:
        print("Failures / Deviations:")
        for d in metrics["details"]:
            print(f" - {d}")
    else:
        print("Result: ALL BENCHMARK SAFETY TARGETS ACHIEVED (0 ungrounded escapes)")
    print("=" * 65)


if __name__ == "__main__":
    from typing import Optional
    report = run_ai_evaluation()
    print_evaluation_report(report)
