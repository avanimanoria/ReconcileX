"""Unit and integration tests for MetricsService and formula calculations."""

import pytest
from backend.app.benchmark.metrics import calculate_f1
from backend.app.services.metrics_service import MetricsService


def test_f1_calculation_zero_denominator():
    """F1 must return 0.0 when precision + recall == 0.0."""
    assert calculate_f1(0.0, 0.0) == 0.0
    assert calculate_f1(-1.0, 1.0) == 0.0


def test_f1_calculation_standard_values():
    """F1 harmonic mean must be computed accurately."""
    p = 0.8
    r = 0.8
    expected = 2 * (p * r) / (p + r)
    assert abs(calculate_f1(p, r) - expected) < 1e-6

    # Asymmetric
    p2 = 0.9
    r2 = 0.6
    expected2 = 2 * (p2 * r2) / (p2 + r2)
    assert abs(calculate_f1(p2, r2) - expected2) < 1e-6


def test_metrics_service_truthful_evaluation_report():
    """Verify that MetricsService returns dynamic evaluation data with correct rates and truthful human metrics."""
    service = MetricsService()
    report = service.get_evaluation_report(force_refresh=True)

    assert "generated_at" in report
    assert "deterministic_reconciliation" in report
    assert "ai_advisory_extraction" in report
    assert "human_workflow" in report

    det = report["deterministic_reconciliation"]
    assert det["sample_size"] == 500
    assert det["total_scenarios_evaluated"] == 500
    assert det["auto_match_precision"] == 1.0
    assert det["auto_match_recall"] == 1.0
    assert det["auto_match_f1"] == 1.0
    assert det["incorrect_auto_match_count"] == 0
    assert det["latency_ms"] > 0
    assert det["throughput_records_per_minute"] > 0

    # Mandatory Correction 1: category exception rates defined as category_count / total_scenarios
    assert "total_exception_rate" in det
    assert "exception_rates_by_category" in det
    assert det["total_exception_rate"] == round(det["exceptions_emitted"] / det["total_scenarios_evaluated"], 4)
    for cat, rate in det["exception_rates_by_category"].items():
        count = det["exception_breakdown_actual"][cat]
        assert rate == round(count / det["total_scenarios_evaluated"], 4)

    # Mandatory Correction 2: Human workflow metrics truthful status
    human = report["human_workflow"]
    assert human["simulated_mean_time_to_resolution"] == "Not measured / Unavailable"
    assert human["auto_resolution_rate"] == "Not applicable — human approval required"

    # AI narration extraction metrics
    ai_extr = report["ai_advisory_extraction"]
    assert ai_extr["sample_size"] == 30
    assert ai_extr["settlement_id_precision"] >= 0.9
    assert ai_extr["unsafe_output_blocked_rate"] == 1.0
    assert "disclaimer" in ai_extr
