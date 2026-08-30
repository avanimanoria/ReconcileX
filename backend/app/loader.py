"""CSV loader and data validation module for ReconcileX V1."""

import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import (
    AuditEntry,
    BankCreditRecord,
    Dataset,
    InvalidRowRecord,
    PaymentRecord,
    RefundRecord,
    SettlementRecord,
    TruthRecord,
)


def parse_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    return Decimal(val_str)


def parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    try:
        return datetime.fromisoformat(val_str)
    except (ValueError, TypeError):
        return None


def load_dataset(
    data_dir: Union[str, Path] = "data/input",
    payments_file: str = "payments.csv",
    settlements_file: str = "settlements.csv",
    bank_credits_file: str = "bank_credits.csv",
    refunds_file: str = "refunds.csv",
) -> Dataset:
    base_path = Path(data_dir)
    payments_path = base_path / payments_file
    settlements_path = base_path / settlements_file
    bank_credits_path = base_path / bank_credits_file
    refunds_path = base_path / refunds_file

    dataset = Dataset()
    seen_payment_event_ids = set()

    # 1. Load Payments
    if payments_path.exists():
        with open(payments_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                event_id = (row.get("payment_event_id") or "").strip()
                payment_id = (row.get("payment_id") or "").strip()
                order_id = (row.get("order_id") or "").strip()
                amount_str = (row.get("captured_amount") or "").strip()
                status = (row.get("status") or "").strip().lower()
                captured_at_str = (row.get("captured_at") or "").strip()

                if not event_id or not payment_id:
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=payments_file,
                            raw_data=row,
                            error_reason="Missing payment_event_id or payment_id",
                            record_id=payment_id or event_id,
                        )
                    )
                    continue

                # Idempotency check on payment_event_id
                if event_id in seen_payment_event_ids:
                    dataset.audit_logs.append(
                        AuditEntry(
                            event_type="DUPLICATE_EVENT",
                            entity_id=event_id,
                            reason=f"Duplicate payment_event_id '{event_id}' skipped during ingestion.",
                            details={"payment_id": payment_id, "row": row},
                        )
                    )
                    continue

                try:
                    amount = Decimal(amount_str)
                except (InvalidOperation, TypeError):
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=payments_file,
                            raw_data=row,
                            error_reason=f"Payment captured_amount '{amount_str}' is not a valid Decimal.",
                            record_id=payment_id,
                        )
                    )
                    continue

                seen_payment_event_ids.add(event_id)
                dataset.payments.append(
                    PaymentRecord(
                        payment_event_id=event_id,
                        payment_id=payment_id,
                        order_id=order_id,
                        captured_amount=amount,
                        status=status,
                        captured_at=parse_datetime(captured_at_str),
                    )
                )

    # 2. Load Settlements
    if settlements_path.exists():
        with open(settlements_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                settlement_id = (row.get("settlement_id") or "").strip()
                payment_id = (row.get("payment_id") or "").strip() or None
                gross_str = (row.get("gross_amount") or "").strip()
                fee_str = (row.get("fee_amount") or "").strip()
                gst_str = (row.get("gst_on_fee") or "").strip()
                net_str = (row.get("net_amount") or "").strip()
                status = (row.get("settlement_status") or "").strip().lower()
                settled_at_str = (row.get("settled_at") or "").strip()

                if not settlement_id:
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=settlements_file,
                            raw_data=row,
                            error_reason="Missing settlement_id",
                        )
                    )
                    continue

                try:
                    gross_amount = Decimal(gross_str) if gross_str else Decimal(0)
                    fee_amount = Decimal(fee_str) if fee_str else Decimal(0)
                    gst_on_fee = Decimal(gst_str) if gst_str else Decimal(0)
                    net_amount = Decimal(net_str) if net_str else Decimal(0)
                except (InvalidOperation, TypeError) as e:
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=settlements_file,
                            raw_data=row,
                            error_reason=f"Settlement amount fields could not be parsed as Decimal: {e}",
                            record_id=settlement_id,
                            reference=payment_id,
                        )
                    )
                    continue

                dataset.settlements.append(
                    SettlementRecord(
                        settlement_id=settlement_id,
                        payment_id=payment_id,
                        gross_amount=gross_amount,
                        fee_amount=fee_amount,
                        gst_on_fee=gst_on_fee,
                        net_amount=net_amount,
                        settlement_status=status,
                        settled_at=parse_datetime(settled_at_str),
                    )
                )

    # 3. Load Bank Credits
    if bank_credits_path.exists():
        with open(bank_credits_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bank_txn_id = (row.get("bank_txn_id") or "").strip()
                narration = (row.get("narration") or "").strip()
                credit_str = (row.get("credit_amount") or "").strip()
                credited_at_str = (row.get("credited_at") or "").strip()

                # Extract settlement reference from narration if present (e.g., SET-xxx)
                ref_match = re.search(r"\bSET-\d+\b", narration)
                reference = ref_match.group(0) if ref_match else None

                if not bank_txn_id:
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=bank_credits_file,
                            raw_data=row,
                            error_reason="Missing bank_txn_id",
                            reference=reference,
                        )
                    )
                    continue

                try:
                    credit_amount = Decimal(credit_str)
                except (InvalidOperation, TypeError):
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=bank_credits_file,
                            raw_data=row,
                            error_reason="Bank credit amount could not be parsed as Decimal.",
                            record_id=bank_txn_id,
                            reference=reference,
                        )
                    )
                    continue

                dataset.bank_credits.append(
                    BankCreditRecord(
                        bank_txn_id=bank_txn_id,
                        narration=narration,
                        credit_amount=credit_amount,
                        credited_at=parse_datetime(credited_at_str),
                    )
                )

    # 4. Load Refunds
    if refunds_path.exists():
        with open(refunds_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                refund_id = (row.get("refund_id") or "").strip()
                payment_id = (row.get("payment_id") or "").strip()
                amount_str = (row.get("refund_amount") or "").strip()
                status = (row.get("refund_status") or "").strip().lower()
                refunded_at_str = (row.get("refunded_at") or "").strip()

                if not refund_id or not payment_id:
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=refunds_file,
                            raw_data=row,
                            error_reason="Missing refund_id or payment_id",
                            record_id=refund_id,
                            reference=payment_id,
                        )
                    )
                    continue

                try:
                    refund_amount = Decimal(amount_str)
                except (InvalidOperation, TypeError):
                    dataset.quarantined_rows.append(
                        InvalidRowRecord(
                            source_file=refunds_file,
                            raw_data=row,
                            error_reason=f"Refund amount '{amount_str}' is not a valid Decimal.",
                            record_id=refund_id,
                            reference=payment_id,
                        )
                    )
                    continue

                dataset.refunds.append(
                    RefundRecord(
                        refund_id=refund_id,
                        payment_id=payment_id,
                        refund_amount=refund_amount,
                        refund_status=status,
                        refunded_at=parse_datetime(refunded_at_str),
                    )
                )

    return dataset


def load_truth_ledger(
    file_path: Union[str, Path] = "data/evaluation/truth_ledger.csv"
) -> List[TruthRecord]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Truth ledger file not found at: {path}")

    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(
                TruthRecord(
                    truth_group_id=row.get("truth_group_id", "").strip(),
                    scenario=row.get("scenario", "").strip(),
                    payment_record=row.get("payment_record", "").strip(),
                    settlement_record=row.get("settlement_record", "").strip(),
                    bank_record=row.get("bank_record", "").strip(),
                    refund_record=row.get("refund_record", "").strip(),
                    expected_system_result=row.get("expected_system_result", "").strip(),
                    reason=row.get("reason", "").strip(),
                )
            )
    return records
