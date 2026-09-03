"""Unified Evaluation and Truthful Metrics Service for ReconcileX."""

from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Any, Dict, Optional

from backend.app.benchmark.ai_eval.narration_eval_runner import run_narration_evaluation
from backend.app.benchmark.metrics import calculate_benchmark_metrics
from backend.app.benchmark.runner import count_csv_rows
from backend.app.improved_matcher import run_improved_reconciliation
from backend.app.loader import load_dataset, load_truth_ledger

logger = logging.getLogger(__name__)

BENCHMARK_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "benchmark"


class MetricsService:
    """Service computing and aggregating truthful, reproducible system metrics."""

    def __init__(self, benchmark_dir: Optional[Path] = None) -> None:
        self.benchmark_dir = benchmark_dir or BENCHMARK_BASE_DIR
        self._cached_report: Optional[Dict[str, Any]] = None
        self._cached_at: Optional[float] = None

    def get_evaluation_report(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Return truthful evaluation report computed live from held-out benchmark and narration datasets."""
        now = time.time()
        # Cache for 60 seconds to avoid repeating heavy file I/O on rapid clicks
        if not force_refresh and self._cached_report is not None and self._cached_at is not None:
            if (now - self._cached_at) < 60.0:
                return self._cached_report

        heldout_dir = self.benchmark_dir / "heldout"
        input_dir = heldout_dir / "input"
        truth_path = heldout_dir / "evaluation" / "truth_ledger.csv"

        if not input_dir.exists() or not truth_path.exists():
            raise FileNotFoundError(f"Held-out benchmark files not found in {heldout_dir}")

        # 1. Compute Deterministic Reconciliation Metrics Live
        raw_payment_count = count_csv_rows(input_dir / "payments.csv")
        start_time = time.perf_counter()

        dataset = load_dataset(input_dir)
        batch_result = run_improved_reconciliation(dataset)
        truth_records = load_truth_ledger(truth_path)

        elapsed = time.perf_counter() - start_time
        metrics = calculate_benchmark_metrics(
            split="heldout",
            engine="improved",
            dataset=dataset,
            batch_result=batch_result,
            truth_records=truth_records,
            raw_payment_count=raw_payment_count,
            elapsed_seconds=elapsed,
            seed=20260902,
            generator_version="1.0.0",
        )

        deterministic_data = {
            "dataset_name": "ReconcileX Synthetic Held-Out Benchmark",
            "sample_size": metrics.total_scenarios,
            "generator_version": metrics.generator_version or "1.0.0",
            "seed": metrics.seed,
            "auto_match_precision": round(metrics.auto_match_precision, 4),
            "auto_match_recall": round(metrics.auto_match_recall, 4),
            "auto_match_f1": round(metrics.auto_match_f1, 4),
            "incorrect_auto_match_count": metrics.unsafe_auto_matches,
            "total_scenarios_evaluated": metrics.total_scenarios,
            "auto_matches_emitted": metrics.auto_matches,
            "exceptions_emitted": metrics.exceptions,
            "total_exception_rate": metrics.total_exception_rate,
            "exception_rates_by_category": metrics.exception_rates_by_category,
            "exception_breakdown_actual": metrics.exception_breakdown_actual,
            "latency_ms": metrics.latency_ms,
            "throughput_records_per_minute": metrics.throughput_records_per_minute,
            "definitions": {
                "precision": "TP / (TP + FP) where FP is an emitted AUTO_MATCH not matching truth ledger (convention: 1.0 if TP=0, FP=0)",
                "recall": "TP / (TP + FN) where FN is an un-emitted AUTO_MATCH labeled as valid match in truth ledger (convention: 1.0 if TP=0, FN=0)",
                "f1": "2 * P * R / (P + R) with zero-denominator convention (0.0 if P+R=0)",
                "incorrect_auto_matches": "False positives (FP) where system emitted AUTO_MATCH contrary to truth ledger.",
                "total_exception_rate": "total_exceptions / total_scenarios_evaluated",
                "category_exception_rate": "category_exception_count / total_scenarios_evaluated",
                "throughput": "Total input records / (elapsed processing time in seconds / 60)",
            },
            "disclaimer": (
                "Evaluated against seeded synthetic held-out truth ledger under ReconcileX V1 deterministic rules. "
                "Not evidence of third-party merchant production accuracy."
            ),
        }

        # 2. Compute AI Advisory Extraction Metrics Live
        ai_extraction_data = run_narration_evaluation()

        # 3. Human Workflow Metrics (Truthful: No simulated production fixtures in prototype)
        human_workflow_data = {
            "simulated_mean_time_to_resolution": "Not measured / Unavailable",
            "auto_resolution_rate": "Not applicable — human approval required",
            "disclaimer": (
                "ReconcileX prototype strictly requires human operator review for all exception resolutions. "
                "No autonomous resolution exists."
            ),
        }

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "deterministic_reconciliation": deterministic_data,
            "ai_advisory_extraction": ai_extraction_data,
            "human_workflow": human_workflow_data,
        }

        self._cached_report = report
        self._cached_at = now
        return report
