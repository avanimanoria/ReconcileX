"""Unit tests for the benchmark runner and metrics calculation in ReconcileX."""

import json
from pathlib import Path
import tempfile
import pytest

from backend.app.baseline import run_baseline_reconciliation
from backend.app.benchmark.generator import BenchmarkGenerator
from backend.app.benchmark.metrics import calculate_benchmark_metrics
from backend.app.benchmark.runner import count_csv_rows, run_benchmark
from backend.app.benchmark.scenarios import ScenarioType
from backend.app.improved_matcher import run_improved_reconciliation
from backend.app.loader import load_dataset, load_truth_ledger
from backend.app.models import MatchStatus


@pytest.fixture
def temp_benchmark_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Generate a 120-scenario dataset covering all scenario types
        gen = BenchmarkGenerator(split="dev", count=120, seed=20260901)
        gen.write_dataset(output_base_dir=tmp_path, overwrite=True)
        yield tmp_path


def test_improved_engine_has_full_agreement_on_generated_data(temp_benchmark_dir: Path):
    """Verify improved engine achieves 100% exact agreement and 0 unsafe auto-matches on synthetic benchmark."""
    input_dir = temp_benchmark_dir / "dev" / "input"
    truth_file = temp_benchmark_dir / "dev" / "evaluation" / "truth_ledger.csv"

    dataset = load_dataset(data_dir=input_dir)
    truth_records = load_truth_ledger(truth_file)
    batch_result = run_improved_reconciliation(dataset)

    raw_payments = count_csv_rows(input_dir / "payments.csv")
    metrics = calculate_benchmark_metrics(
        split="dev",
        engine="improved",
        dataset=dataset,
        batch_result=batch_result,
        truth_records=truth_records,
        raw_payment_count=raw_payments,
    )

    assert metrics.total_scenarios == 120
    assert metrics.exact_agreement == 120
    assert metrics.accuracy == 100.0
    assert metrics.unsafe_auto_matches == 0
    assert metrics.auto_match_precision == 1.0
    assert metrics.auto_match_recall == 1.0
    assert metrics.exception_precision == 1.0
    assert metrics.exception_recall == 1.0


def test_baseline_is_weaker_than_improved_on_large_dataset(temp_benchmark_dir: Path):
    """Verify baseline engine achieves lower agreement than improved engine on multi-scenario benchmark."""
    input_dir = temp_benchmark_dir / "dev" / "input"
    truth_file = temp_benchmark_dir / "dev" / "evaluation" / "truth_ledger.csv"

    dataset = load_dataset(data_dir=input_dir)
    truth_records = load_truth_ledger(truth_file)

    b_batch = run_baseline_reconciliation(dataset)
    i_batch = run_improved_reconciliation(dataset)

    raw_payments = count_csv_rows(input_dir / "payments.csv")
    b_metrics = calculate_benchmark_metrics(
        split="dev",
        engine="baseline",
        dataset=dataset,
        batch_result=b_batch,
        truth_records=truth_records,
        raw_payment_count=raw_payments,
    )
    i_metrics = calculate_benchmark_metrics(
        split="dev",
        engine="improved",
        dataset=dataset,
        batch_result=i_batch,
        truth_records=truth_records,
        raw_payment_count=raw_payments,
    )

    assert i_metrics.exact_agreement > b_metrics.exact_agreement
    assert i_metrics.accuracy > b_metrics.accuracy
    # Baseline misses timing and variance scenarios, so it produces unsafe auto matches
    assert b_metrics.unsafe_auto_matches > 0
    assert i_metrics.unsafe_auto_matches == 0


def test_generated_invalid_bank_amount_is_quarantined(temp_benchmark_dir: Path):
    """Verify INVALID_BANK_AMOUNT rows are gracefully quarantined without halting the batch."""
    input_dir = temp_benchmark_dir / "dev" / "input"
    with open(temp_benchmark_dir / "dev" / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    expected_invalid_count = manifest["scenario_distribution"][ScenarioType.INVALID_BANK_AMOUNT.value]

    dataset = load_dataset(data_dir=input_dir)
    assert len(dataset.quarantined_rows) == expected_invalid_count

    batch_result = run_improved_reconciliation(dataset)
    invalid_exceptions = [
        r for r in batch_result.results
        if r.exception_type and r.exception_type.value == "INVALID_ROW"
    ]
    assert len(invalid_exceptions) == expected_invalid_count


def test_generated_duplicate_events_create_audit_entries(temp_benchmark_dir: Path):
    """Verify duplicate payment events generate audit entries and one single AUTO_MATCH per group."""
    input_dir = temp_benchmark_dir / "dev" / "input"
    with open(temp_benchmark_dir / "dev" / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    expected_dup_count = manifest["scenario_distribution"][ScenarioType.DUPLICATE_PAYMENT_EVENT.value]

    dataset = load_dataset(data_dir=input_dir)
    dup_audits = [a for a in dataset.audit_logs if a.event_type == "DUPLICATE_EVENT"]
    assert len(dup_audits) == expected_dup_count

    batch_result = run_improved_reconciliation(dataset)
    auto_matches = [r for r in batch_result.results if r.match_status == MatchStatus.AUTO_MATCH]
    # Total auto matches should equal EXACT_MATCH + VALID_REFUND + DUPLICATE_PAYMENT_EVENT counts
    expected_auto_matches = (
        manifest["scenario_distribution"][ScenarioType.EXACT_MATCH.value]
        + manifest["scenario_distribution"][ScenarioType.VALID_REFUND.value]
        + manifest["scenario_distribution"][ScenarioType.DUPLICATE_PAYMENT_EVENT.value]
    )
    assert len(auto_matches) == expected_auto_matches


def test_runner_cli_execution_modes(temp_benchmark_dir: Path):
    """Verify runner runs successfully in baseline, improved, and compare modes."""
    ret_improved = run_benchmark(split="dev", engine="improved", benchmark_base_dir=str(temp_benchmark_dir))
    assert ret_improved == 0

    ret_baseline = run_benchmark(split="dev", engine="baseline", benchmark_base_dir=str(temp_benchmark_dir))
    assert ret_baseline == 0

    ret_compare = run_benchmark(split="dev", engine="compare", benchmark_base_dir=str(temp_benchmark_dir))
    assert ret_compare == 0
