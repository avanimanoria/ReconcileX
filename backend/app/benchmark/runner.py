"""Runner module for executing benchmark evaluations on ReconcileX engines."""

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.app.baseline import run_baseline_reconciliation
from backend.app.evaluator import evaluate_results
from backend.app.improved_matcher import run_improved_reconciliation
from backend.app.loader import load_dataset, load_truth_ledger
from backend.app.main import format_table
from backend.app.models import Dataset, ReconciliationBatchResult, TruthRecord
from .metrics import BenchmarkMetrics, calculate_benchmark_metrics

DISCLAIMER_TEXT = (
    "Results are agreement against a seeded synthetic benchmark generated under the documented "
    "ReconcileX V1 rules; they are not evidence of production merchant-data accuracy."
)


def count_csv_rows(file_path: Path) -> int:
    """Count data rows in a CSV file (excluding header)."""
    if not file_path.exists():
        return 0
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            next(reader)  # Skip header
            return sum(1 for _ in reader)
        except StopIteration:
            return 0


def print_single_report(metrics: BenchmarkMetrics) -> None:
    """Print formatted benchmark performance and accuracy report."""
    print("=" * 80)
    print(f"       RECONCILEX SYNTHETIC BENCHMARK REPORT: {metrics.split.upper()} ({metrics.engine.upper()})       ")
    print("=" * 80)
    print(f"Split Name           : {metrics.split}")
    print(f"Engine Evaluated     : {metrics.engine.upper()}")
    print(f"Seed                 : {metrics.seed if metrics.seed is not None else 'N/A'}")
    print(f"Generator Version    : {metrics.generator_version or 'N/A'}")
    print(f"Total Scenarios      : {metrics.total_scenarios}")
    print("-" * 80)

    print("\n--- INGESTION & DATASET STATS ---")
    stats_rows = [
        ["Raw Payment-Event Rows", str(metrics.raw_payment_rows)],
        ["Unique Valid Payments", str(metrics.unique_payments)],
        ["Settlements Loaded", str(metrics.settlements_count)],
        ["Bank Credits Loaded", str(metrics.bank_credits_count)],
        ["Refunds Loaded", str(metrics.refunds_count)],
        ["Quarantined Rows (INVALID_ROW)", str(metrics.quarantined_rows)],
        ["Duplicate Payment Event Audits", str(metrics.duplicate_audits)],
    ]
    print(format_table(["Metric", "Count"], stats_rows))

    print("\n--- RECONCILIATION & AGREEMENT METRICS ---")
    agree_rows = [
        ["Exact Outcome Agreement", f"{metrics.exact_agreement} / {metrics.total_scenarios}"],
        ["Accuracy Rate", f"{metrics.accuracy:.2f}%"],
        ["Auto-Match Outcomes", str(metrics.auto_matches)],
        ["Exception Outcomes", str(metrics.exceptions)],
        ["Unsafe Auto-Matches", str(metrics.unsafe_auto_matches)],
    ]
    print(format_table(["Metric", "Value"], agree_rows))

    print("\n--- PRECISION & RECALL ---")
    pr_rows = [
        ["Auto-Match Precision", f"{metrics.auto_match_precision * 100:.2f}%"],
        ["Auto-Match Recall", f"{metrics.auto_match_recall * 100:.2f}%"],
        ["Exception Precision", f"{metrics.exception_precision * 100:.2f}%"],
        ["Exception Recall", f"{metrics.exception_recall * 100:.2f}%"],
    ]
    print(format_table(["Metric", "Score"], pr_rows))

    print("\n--- EXCEPTION CATEGORY BREAKDOWN ---")
    all_categories = sorted(set(list(metrics.exception_breakdown_truth.keys()) + list(metrics.exception_breakdown_actual.keys())))
    exc_rows = []
    for cat in all_categories:
        truth_cnt = metrics.exception_breakdown_truth.get(cat, 0)
        actual_cnt = metrics.exception_breakdown_actual.get(cat, 0)
        exc_rows.append([cat, str(truth_cnt), str(actual_cnt)])
    print(format_table(["Exception Category", "Expected (Truth)", "Actual (Engine)"], exc_rows))

    print("\n--- PERFORMANCE & THROUGHPUT ---")
    perf_rows = [
        ["Elapsed Execution Time", f"{metrics.elapsed_seconds:.4f} s"],
        ["Scenario Throughput", f"{metrics.scenarios_per_second:.1f} scenarios/s"],
        ["Input-Row Throughput", f"{metrics.input_rows_per_second:.1f} rows/s"],
    ]
    print(format_table(["Benchmark Metric", "Measurement"], perf_rows))

    print("\n" + "-" * 80)
    print(f"NOTE: {DISCLAIMER_TEXT}")
    print("-" * 80)


def print_comparison_report(b_metrics: BenchmarkMetrics, i_metrics: BenchmarkMetrics) -> None:
    """Print side-by-side comparison between baseline and improved engines."""
    print("=" * 80)
    print(f"     RECONCILEX BENCHMARK COMPARISON: {b_metrics.split.upper()} (BASELINE vs IMPROVED)     ")
    print("=" * 80)
    print(f"Split Name           : {b_metrics.split}")
    print(f"Seed                 : {b_metrics.seed if b_metrics.seed is not None else 'N/A'}")
    print(f"Total Scenarios      : {b_metrics.total_scenarios}")
    print("-" * 80)

    print("\n--- ACCURACY & QUALITY COMPARISON ---")
    comp_rows = [
        ["Exact Outcome Agreement", f"{b_metrics.exact_agreement}/{b_metrics.total_scenarios}", f"{i_metrics.exact_agreement}/{i_metrics.total_scenarios}"],
        ["Accuracy Rate", f"{b_metrics.accuracy:.2f}%", f"{i_metrics.accuracy:.2f}%"],
        ["Auto-Match Precision", f"{b_metrics.auto_match_precision * 100:.2f}%", f"{i_metrics.auto_match_precision * 100:.2f}%"],
        ["Auto-Match Recall", f"{b_metrics.auto_match_recall * 100:.2f}%", f"{i_metrics.auto_match_recall * 100:.2f}%"],
        ["Exception Precision", f"{b_metrics.exception_precision * 100:.2f}%", f"{i_metrics.exception_precision * 100:.2f}%"],
        ["Exception Recall", f"{b_metrics.exception_recall * 100:.2f}%", f"{i_metrics.exception_recall * 100:.2f}%"],
        ["Unsafe Auto-Matches", str(b_metrics.unsafe_auto_matches), str(i_metrics.unsafe_auto_matches)],
    ]
    print(format_table(["Metric", "Baseline Engine", "Improved Engine"], comp_rows))

    print("\n--- THROUGHPUT COMPARISON ---")
    thru_rows = [
        ["Elapsed Time", f"{b_metrics.elapsed_seconds:.4f} s", f"{i_metrics.elapsed_seconds:.4f} s"],
        ["Scenario Throughput", f"{b_metrics.scenarios_per_second:.1f} sc/s", f"{i_metrics.scenarios_per_second:.1f} sc/s"],
        ["Input-Row Throughput", f"{b_metrics.input_rows_per_second:.1f} rows/s", f"{i_metrics.input_rows_per_second:.1f} rows/s"],
    ]
    print(format_table(["Metric", "Baseline Engine", "Improved Engine"], thru_rows))

    print("\n" + "-" * 80)
    print(f"NOTE: {DISCLAIMER_TEXT}")
    print("-" * 80)


def run_benchmark(
    split: str = "dev",
    engine: str = "improved",
    benchmark_base_dir: str = "data/benchmark",
) -> int:
    base_path = Path(benchmark_base_dir)
    split_dir = base_path / split
    input_dir = split_dir / "input"
    truth_file = split_dir / "evaluation" / "truth_ledger.csv"
    manifest_file = split_dir / "manifest.json"

    if not split_dir.exists() or not input_dir.exists() or not truth_file.exists():
        print(
            f"Error: Benchmark split '{split}' not found at '{split_dir}'. "
            f"Please run generator first:\n"
            f"  python -m backend.app.benchmark.generator --split {split}",
            file=sys.stderr,
        )
        return 1

    # Load Manifest
    seed: Optional[int] = None
    gen_version: Optional[str] = None
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                seed = manifest_data.get("seed")
                gen_version = manifest_data.get("generator_version")
        except Exception:
            pass

    # Count raw payment rows
    raw_payment_count = count_csv_rows(input_dir / "payments.csv")

    # Load input dataset
    dataset = load_dataset(data_dir=input_dir)
    truth_records = load_truth_ledger(truth_file)

    if engine == "improved":
        t0 = time.perf_counter()
        batch_result = run_improved_reconciliation(dataset)
        elapsed = time.perf_counter() - t0
        metrics = calculate_benchmark_metrics(
            split=split,
            engine="improved",
            dataset=dataset,
            batch_result=batch_result,
            truth_records=truth_records,
            raw_payment_count=raw_payment_count,
            elapsed_seconds=elapsed,
            seed=seed,
            generator_version=gen_version,
        )
        print_single_report(metrics)

    elif engine == "baseline":
        t0 = time.perf_counter()
        batch_result = run_baseline_reconciliation(dataset)
        elapsed = time.perf_counter() - t0
        metrics = calculate_benchmark_metrics(
            split=split,
            engine="baseline",
            dataset=dataset,
            batch_result=batch_result,
            truth_records=truth_records,
            raw_payment_count=raw_payment_count,
            elapsed_seconds=elapsed,
            seed=seed,
            generator_version=gen_version,
        )
        print_single_report(metrics)

    elif engine == "compare":
        # Run Baseline
        t0_b = time.perf_counter()
        b_batch = run_baseline_reconciliation(dataset)
        b_elapsed = time.perf_counter() - t0_b
        b_metrics = calculate_benchmark_metrics(
            split=split,
            engine="baseline",
            dataset=dataset,
            batch_result=b_batch,
            truth_records=truth_records,
            raw_payment_count=raw_payment_count,
            elapsed_seconds=b_elapsed,
            seed=seed,
            generator_version=gen_version,
        )

        # Run Improved
        t0_i = time.perf_counter()
        i_batch = run_improved_reconciliation(dataset)
        i_elapsed = time.perf_counter() - t0_i
        i_metrics = calculate_benchmark_metrics(
            split=split,
            engine="improved",
            dataset=dataset,
            batch_result=i_batch,
            truth_records=truth_records,
            raw_payment_count=raw_payment_count,
            elapsed_seconds=i_elapsed,
            seed=seed,
            generator_version=gen_version,
        )

        print_comparison_report(b_metrics, i_metrics)

    else:
        print(f"Unknown engine mode: {engine}. Choose from 'baseline', 'improved', or 'compare'.", file=sys.stderr)
        return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="ReconcileX Benchmark Runner")
    parser.add_argument("--split", choices=["dev", "heldout", "chaos"], default="dev", help="Benchmark split to evaluate")
    parser.add_argument("--engine", choices=["baseline", "improved", "compare"], default="improved", help="Engine to run")
    parser.add_argument("--benchmark-dir", default="data/benchmark", help="Base directory of benchmarks")

    args = parser.parse_args()
    sys.exit(run_benchmark(split=args.split, engine=args.engine, benchmark_base_dir=args.benchmark_dir))


if __name__ == "__main__":
    main()
