"""Reproducible synthetic benchmark dataset generator for ReconcileX."""

import argparse
import csv
import hashlib
import json
import random
import shutil
import sys
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .scenarios import (
    allocate_scenario_counts,
    SCENARIO_EXPECTED_RESULTS,
    SCENARIO_REASONS,
    ScenarioType,
)

GENERATOR_VERSION = "1.0.0"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class BenchmarkGenerator:
    """Generates deterministic, synthetic datasets for ReconcileX benchmark evaluation."""

    def __init__(self, split: str = "dev", count: int = 250, seed: int = 20260901) -> None:
        self.split = split.lower()
        self.count = count
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_data(self) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]], Dict[str, int]]:
        """Generate all input rows and truth ledger records in memory deterministically."""
        scenario_counts = allocate_scenario_counts(self.count, self.split)

        # Build list of scenario types according to allocated counts
        scenario_list: List[ScenarioType] = []
        for st, sc_count in scenario_counts.items():
            scenario_list.extend([st] * sc_count)

        # Sort scenarios deterministically by scenario type enum order, then we process with index
        scenario_list.sort(key=lambda st: list(ScenarioType).index(st))

        payment_rows: List[Dict[str, str]] = []
        settlement_rows: List[Dict[str, str]] = []
        bank_rows: List[Dict[str, str]] = []
        refund_rows: List[Dict[str, str]] = []
        truth_rows: List[Dict[str, str]] = []

        base_time = datetime(2026, 9, 1, 9, 0, 0)

        for idx, st in enumerate(scenario_list, start=1):
            truth_group_id = f"BENCH-{self.split.upper()}-{idx:06d}"
            payment_id = f"PAY-{self.split.upper()}-{idx:06d}"
            payment_event_id = f"evt_pay_{self.split.lower()}_{idx:06d}"
            order_id = f"ORD-{self.split.upper()}-{idx:06d}"
            settlement_id = f"SET-{self.split.upper()}-{idx:06d}"
            bank_txn_id = f"BANK-{self.split.upper()}-{idx:06d}"
            refund_id = f"REF-{self.split.upper()}-{idx:06d}"

            # Deterministic captured amount in INR (500.00 to 50000.00)
            captured_int = self.rng.randint(5, 500) * 100
            captured_amount = Decimal(str(captured_int)).quantize(Decimal("0.01"))

            captured_dt = base_time + timedelta(minutes=idx * 15)
            captured_at_str = captured_dt.strftime("%Y-%m-%dT%H:%M:%S")

            status = "failed" if st == ScenarioType.STATUS_CONFLICT else "captured"

            # 1. Payment Record
            payment_row = {
                "payment_event_id": payment_event_id,
                "payment_id": payment_id,
                "order_id": order_id,
                "captured_amount": f"{captured_amount:.2f}",
                "status": status,
                "captured_at": captured_at_str,
            }
            payment_rows.append(payment_row)

            # Extra duplicate payment event for DUPLICATE_PAYMENT_EVENT
            if st == ScenarioType.DUPLICATE_PAYMENT_EVENT:
                duplicate_payment_row = dict(payment_row)
                payment_rows.append(duplicate_payment_row)

            # 2. Refund Record
            refund_amount = Decimal("0.00")
            if st == ScenarioType.VALID_REFUND:
                # 10% to 50% partial refund
                pct = self.rng.randint(10, 50)
                refund_amount = (captured_amount * Decimal(str(pct)) / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                refund_dt = captured_dt + timedelta(hours=2)
                refund_row = {
                    "refund_id": refund_id,
                    "payment_id": payment_id,
                    "refund_amount": f"{refund_amount:.2f}",
                    "refund_status": "processed",
                    "refunded_at": refund_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                refund_rows.append(refund_row)

            # 3. Settlement Record
            if st == ScenarioType.SETTLEMENT_DELAY:
                delay_days = self.rng.randint(8, 14)
            else:
                delay_days = self.rng.randint(1, 4)

            settled_dt = captured_dt + timedelta(days=delay_days, hours=self.rng.randint(1, 4))
            settled_at_str = settled_dt.strftime("%Y-%m-%dT%H:%M:%S")

            eligible_amount = captured_amount - refund_amount
            fee_amount = (eligible_amount * Decimal("0.02")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            gst_on_fee = (fee_amount * Decimal("0.18")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            net_amount = (eligible_amount - fee_amount - gst_on_fee).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            settlement_pay_id = "" if st == ScenarioType.MISSING_PAYMENT_ID else payment_id

            settlement_row = {
                "settlement_id": settlement_id,
                "payment_id": settlement_pay_id,
                "gross_amount": f"{captured_amount:.2f}",
                "fee_amount": f"{fee_amount:.2f}",
                "gst_on_fee": f"{gst_on_fee:.2f}",
                "net_amount": f"{net_amount:.2f}",
                "settlement_status": "settled",
                "settled_at": settled_at_str,
            }
            settlement_rows.append(settlement_row)

            # 4. Bank Credit Record
            credited_dt = settled_dt + timedelta(hours=self.rng.randint(2, 6))
            credited_at_str = credited_dt.strftime("%Y-%m-%dT%H:%M:%S")

            if st == ScenarioType.MISSING_REFERENCE:
                narration = "NEFT RAZORPAY SETTLEMENT"
            else:
                narration = f"NEFT RAZORPAY SETTLEMENT {settlement_id}"

            if st == ScenarioType.INVALID_BANK_AMOUNT:
                credit_amount_str = "NOT_A_NUMBER"
            elif st == ScenarioType.AMOUNT_VARIANCE:
                # Add or subtract variance > 0.01
                variance_choices = [
                    Decimal("-50.00"),
                    Decimal("-25.00"),
                    Decimal("-10.00"),
                    Decimal("10.00"),
                    Decimal("25.00"),
                    Decimal("50.00"),
                ]
                variance = self.rng.choice(variance_choices)
                credit_amount = net_amount + variance
                if credit_amount <= Decimal("0.01"):
                    credit_amount = net_amount + Decimal("25.00")
                credit_amount_str = f"{credit_amount:.2f}"
            else:
                credit_amount_str = f"{net_amount:.2f}"

            bank_row = {
                "bank_txn_id": bank_txn_id,
                "narration": narration,
                "credit_amount": credit_amount_str,
                "credited_at": credited_at_str,
            }
            bank_rows.append(bank_row)

            # 5. Truth Ledger Record
            payment_record_val = f"{payment_id} twice" if st == ScenarioType.DUPLICATE_PAYMENT_EVENT else payment_id
            refund_record_val = refund_id if st == ScenarioType.VALID_REFUND else "NONE"

            truth_row = {
                "truth_group_id": truth_group_id,
                "scenario": st.value,
                "payment_record": payment_record_val,
                "settlement_record": settlement_id,
                "bank_record": bank_txn_id,
                "refund_record": refund_record_val,
                "expected_system_result": SCENARIO_EXPECTED_RESULTS[st],
                "reason": SCENARIO_REASONS[st],
            }
            truth_rows.append(truth_row)

        distribution_counts = {st.value: scenario_counts[st] for st in ScenarioType}
        return payment_rows, settlement_rows, bank_rows, refund_rows, truth_rows, distribution_counts

    def write_dataset(self, output_base_dir: Path, overwrite: bool = False) -> Path:
        """Generate and write CSV files and manifest.json to the target split directory."""
        split_dir = output_base_dir / self.split
        if split_dir.exists():
            if not overwrite:
                raise FileExistsError(
                    f"Target directory '{split_dir}' already exists. Pass --overwrite to replace it."
                )
            shutil.rmtree(split_dir)

        input_dir = split_dir / "input"
        eval_dir = split_dir / "evaluation"
        input_dir.mkdir(parents=True, exist_ok=True)
        eval_dir.mkdir(parents=True, exist_ok=True)

        payments, settlements, bank_credits, refunds, truth, distribution = self.generate_data()

        # Write payments.csv
        payments_path = input_dir / "payments.csv"
        with open(payments_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "payment_event_id",
                    "payment_id",
                    "order_id",
                    "captured_amount",
                    "status",
                    "captured_at",
                ],
            )
            writer.writeheader()
            writer.writerows(payments)

        # Write settlements.csv
        settlements_path = input_dir / "settlements.csv"
        with open(settlements_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "settlement_id",
                    "payment_id",
                    "gross_amount",
                    "fee_amount",
                    "gst_on_fee",
                    "net_amount",
                    "settlement_status",
                    "settled_at",
                ],
            )
            writer.writeheader()
            writer.writerows(settlements)

        # Write bank_credits.csv
        bank_credits_path = input_dir / "bank_credits.csv"
        with open(bank_credits_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["bank_txn_id", "narration", "credit_amount", "credited_at"],
            )
            writer.writeheader()
            writer.writerows(bank_credits)

        # Write refunds.csv
        refunds_path = input_dir / "refunds.csv"
        with open(refunds_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "refund_id",
                    "payment_id",
                    "refund_amount",
                    "refund_status",
                    "refunded_at",
                ],
            )
            writer.writeheader()
            writer.writerows(refunds)

        # Write truth_ledger.csv
        truth_path = eval_dir / "truth_ledger.csv"
        with open(truth_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "truth_group_id",
                    "scenario",
                    "payment_record",
                    "settlement_record",
                    "bank_record",
                    "refund_record",
                    "expected_system_result",
                    "reason",
                ],
            )
            writer.writeheader()
            writer.writerows(truth)

        # Compute Checksums
        checksums = {
            "payments.csv": compute_sha256(payments_path),
            "settlements.csv": compute_sha256(settlements_path),
            "bank_credits.csv": compute_sha256(bank_credits_path),
            "refunds.csv": compute_sha256(refunds_path),
            "truth_ledger.csv": compute_sha256(truth_path),
        }

        # Write manifest.json
        manifest = {
            "split": self.split,
            "seed": self.seed,
            "scenario_count": self.count,
            "generator_version": GENERATOR_VERSION,
            "scenario_distribution": distribution,
            "generated_files": [
                "input/payments.csv",
                "input/settlements.csv",
                "input/bank_credits.csv",
                "input/refunds.csv",
                "evaluation/truth_ledger.csv",
            ],
            "checksums": checksums,
        }

        manifest_path = split_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return split_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="ReconcileX Benchmark Generator")
    parser.add_argument("--split", choices=["dev", "heldout", "chaos"], default="dev", help="Dataset split name")
    parser.add_argument("--count", type=int, default=250, help="Total number of truth scenarios")
    parser.add_argument("--seed", type=int, default=20260901, help="Random seed for deterministic generation")
    parser.add_argument("--output-dir", default="data/benchmark", help="Base directory for benchmark outputs")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite target split directory if it exists")

    args = parser.parse_args()

    generator = BenchmarkGenerator(split=args.split, count=args.count, seed=args.seed)
    try:
        split_dir = generator.write_dataset(output_base_dir=Path(args.output_dir), overwrite=args.overwrite)
        print(f"Successfully generated benchmark split '{args.split}' ({args.count} scenarios) at: {split_dir}")
        print(f"Seed: {args.seed}, Generator Version: {GENERATOR_VERSION}")
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error generating benchmark: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
