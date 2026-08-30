"""CLI entry point for ReconcileX V1 reconciliation engine."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .baseline import run_baseline_reconciliation
from .evaluator import evaluate_results
from .loader import load_dataset, load_truth_ledger
from .models import MatchStatus


def format_table(headers: list[str], rows: list[list[str]], col_align: Optional[list[str]] = None) -> str:
    if not rows:
        return "No records."
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    col_align = col_align or ["<"] * len(headers)

    header_line = " | ".join(
        f"{h:<{widths[i]}}" if col_align[i] == "<" else f"{h:>{widths[i]}}"
        for i, h in enumerate(headers)
    )
    separator_line = "-+-".join("-" * widths[i] for i in range(len(headers)))

    data_lines = []
    for row in rows:
        line = " | ".join(
            f"{str(cell):<{widths[i]}}" if col_align[i] == "<" else f"{str(cell):>{widths[i]}}"
            for i, cell in enumerate(row)
        )
        data_lines.append(line)

    return f"{header_line}\n{separator_line}\n" + "\n".join(data_lines)


def run_cli(data_dir: str = "data/input", truth_file: str = "data/evaluation/truth_ledger.csv") -> int:
    print("=" * 80)
    print("                      RECONCILEX V1 RECONCILIATION ENGINE                       ")
    print("=" * 80)
    print(f"Input Directory  : {data_dir}")
    print(f"Evaluation File  : {truth_file}")
    print("-" * 80)

    # 1. Load Data
    try:
        dataset = load_dataset(data_dir=data_dir)
    except Exception as e:
        print(f"Error loading input datasets: {e}", file=sys.stderr)
        return 1

    print("\n--- INGESTION SUMMARY ---")
    print(f"Payments Loaded      : {len(dataset.payments)}")
    print(f"Settlements Loaded   : {len(dataset.settlements)}")
    print(f"Bank Credits Loaded  : {len(dataset.bank_credits)}")
    print(f"Refunds Loaded       : {len(dataset.refunds)}")
    print(f"Quarantined Rows     : {len(dataset.quarantined_rows)}")
    print(f"Duplicate Event Logs : {len(dataset.audit_logs)}")

    # 2. Run Reconciliation
    batch_result = run_baseline_reconciliation(dataset)

    auto_matches = [r for r in batch_result.results if r.match_status == MatchStatus.AUTO_MATCH]
    exceptions = [r for r in batch_result.results if r.match_status == MatchStatus.EXCEPTION]

    exception_counts: dict[str, int] = {}
    for exc in exceptions:
        k = exc.exception_type.value if exc.exception_type else "UNKNOWN"
        exception_counts[k] = exception_counts.get(k, 0) + 1

    print("\n--- RECONCILIATION OUTCOMES ---")
    print(f"Total Results Generated : {len(batch_result.results)}")
    print(f"Auto-Matches            : {len(auto_matches)}")
    print(f"Exceptions              : {len(exceptions)}")
    for exc_type, count in sorted(exception_counts.items()):
        print(f"  - {exc_type:<22}: {count}")

    if dataset.quarantined_rows:
        print("\n--- QUARANTINED ROWS ---")
        q_rows = [
            [q.source_file, q.record_id or "-", q.reference or "-", q.error_reason]
            for q in dataset.quarantined_rows
        ]
        print(format_table(["Source File", "Record ID", "Reference", "Error Reason"], q_rows))

    if dataset.audit_logs:
        print("\n--- AUDIT LOG ENTRIES ---")
        audit_rows = [
            [a.event_type, a.entity_id, a.reason]
            for a in dataset.audit_logs
        ]
        print(format_table(["Event Type", "Entity ID", "Reason"], audit_rows))

    print("\n--- DETAILED ENGINE RESULTS ---")
    result_rows = []
    for r in batch_result.results:
        result_rows.append([
            r.payment_id or "-",
            r.settlement_id or "-",
            r.bank_txn_id or "-",
            r.display_result,
            r.reason,
        ])
    print(format_table(["Payment ID", "Settlement ID", "Bank Txn ID", "Result", "Reason"], result_rows))

    # 3. Evaluate against Truth Ledger
    truth_path = Path(truth_file)
    if truth_path.exists():
        truth_records = load_truth_ledger(truth_file)
        report = evaluate_results(batch_result, truth_records)

        print("\n" + "=" * 80)
        print("                   GROUND TRUTH EVALUATION REPORT                              ")
        print("=" * 80)
        print(f"Total Scenarios Evaluated : {report.total_scenarios}")
        print(f"Exact Matches With Truth  : {report.exact_matches}")
        print(f"Mismatches                : {report.mismatches}")
        print(f"Accuracy Rate             : {report.accuracy:.1f}%")

        print("\n--- SCENARIO COMPARISON TABLE ---")
        comp_rows = []
        for c in report.comparisons:
            status_symbol = "MATCH" if c.is_match else "DIFF"
            comp_rows.append([
                c.truth_group_id,
                c.scenario[:28],
                c.expected_result,
                c.actual_result,
                status_symbol,
                c.notes or "OK",
            ])
        print(format_table(["Group", "Scenario", "Expected Truth", "Actual Engine", "Eval", "Notes"], comp_rows))

        print("\n--- KNOWN BASELINE LIMITATIONS ---")
        for lim in report.known_baseline_limitations:
            print(f"  * {lim}")
        print("-" * 80)
    else:
        print(f"\n[NOTE] Truth ledger not found at {truth_file}, skipping evaluation.")

    print("\nReconciliation batch completed successfully.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="ReconcileX V1 Offline Reconciliation Engine")
    parser.add_argument("--data-dir", default="data/input", help="Path to directory containing input CSVs")
    parser.add_argument("--truth-file", default="data/evaluation/truth_ledger.csv", help="Path to truth ledger CSV")
    args = parser.parse_args()

    sys.exit(run_cli(data_dir=args.data_dir, truth_file=args.truth_file))


if __name__ == "__main__":
    main()
