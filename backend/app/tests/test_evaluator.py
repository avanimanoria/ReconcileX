"""Unit tests for truth ledger evaluator in ReconcileX."""

from backend.app.baseline import run_baseline_reconciliation
from backend.app.evaluator import evaluate_results
from backend.app.loader import load_dataset, load_truth_ledger


def test_evaluate_results_with_truth_ledger():
    dataset = load_dataset("data/input")
    batch_result = run_baseline_reconciliation(dataset)
    truth_records = load_truth_ledger("data/evaluation/truth_ledger.csv")

    report = evaluate_results(batch_result, truth_records)

    assert report.total_scenarios == 15
    assert len(report.comparisons) == 15
    assert len(report.known_baseline_limitations) == 3

    # Check that known limitations are highlighted in notes
    tg_005 = next(c for c in report.comparisons if c.truth_group_id == "TG-005")
    assert not tg_005.is_match
    assert "settlement delay" in tg_005.notes.lower()

    tg_007 = next(c for c in report.comparisons if c.truth_group_id == "TG-007")
    assert not tg_007.is_match
    assert "amount variance" in tg_007.notes.lower()

    # Check exact matching scenarios
    tg_001 = next(c for c in report.comparisons if c.truth_group_id == "TG-001")
    assert tg_001.is_match

    tg_006 = next(c for c in report.comparisons if c.truth_group_id == "TG-006")
    assert tg_006.is_match
    assert tg_006.actual_result == "EXCEPTION: MISSING_REFERENCE"

    tg_012 = next(c for c in report.comparisons if c.truth_group_id == "TG-012")
    assert tg_012.is_match
    assert tg_012.actual_result == "AUTO_MATCH + DUPLICATE_AUDIT"

    tg_013 = next(c for c in report.comparisons if c.truth_group_id == "TG-013")
    assert tg_013.is_match
    assert tg_013.actual_result == "EXCEPTION: MISSING_PAYMENT_ID"

    tg_014 = next(c for c in report.comparisons if c.truth_group_id == "TG-014")
    assert tg_014.is_match
    assert tg_014.actual_result == "EXCEPTION: STATUS_CONFLICT"

    tg_015 = next(c for c in report.comparisons if c.truth_group_id == "TG-015")
    assert tg_015.is_match
    assert tg_015.actual_result == "EXCEPTION: INVALID_ROW"
