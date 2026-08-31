"""Adversarial combination and rule precedence tests for ReconcileX Improved Matcher.

Tests multi-fault scenarios against the real CSV loader and improved matcher workflow.
"""

import csv
from decimal import Decimal
from pathlib import Path
import pytest

from backend.app.improved_matcher import ImprovedMatcher
from backend.app.loader import load_dataset
from backend.app.models import ExceptionType, MatchStatus


def create_fixture_files(
    tmp_path: Path,
    payments: list[dict],
    settlements: list[dict],
    bank_credits: list[dict],
    refunds: list[dict] = None,
) -> Path:
    """Helper to write isolated CSV files to pytest tmp_path."""
    refunds = refunds or []

    # Write payments.csv
    with open(tmp_path / "payments.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["payment_event_id", "payment_id", "order_id", "captured_amount", "status", "captured_at"],
        )
        writer.writeheader()
        writer.writerows(payments)

    # Write settlements.csv
    with open(tmp_path / "settlements.csv", "w", newline="", encoding="utf-8") as f:
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
    with open(tmp_path / "bank_credits.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["bank_txn_id", "narration", "credit_amount", "credited_at"],
        )
        writer.writeheader()
        writer.writerows(bank_credits)

    # Write refunds.csv
    with open(tmp_path / "refunds.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["refund_id", "payment_id", "refund_amount", "refund_status", "refunded_at"],
        )
        writer.writeheader()
        writer.writerows(refunds)

    return tmp_path


def test_case_01_invalid_bank_amount_plus_missing_reference(tmp_path: Path):
    """CASE 1: Invalid bank amount + missing reference -> EXCEPTION: INVALID_ROW."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_001",
            "payment_id": "PAY-ADV-001",
            "order_id": "ORD-ADV-001",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-001",
            "payment_id": "PAY-ADV-001",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-001",
            "narration": "NEFT CREDIT MISC",  # Does NOT contain SET-ADV-001
            "credit_amount": "NOT_A_NUMBER",   # Invalid amount
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    assert len(dataset.quarantined_rows) == 1
    assert dataset.quarantined_rows[0].record_id == "BANK-ADV-001"

    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.INVALID_ROW
    assert res.settlement_id == "SET-ADV-001"
    assert res.payment_id == "PAY-ADV-001"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_02_invalid_bank_amount_plus_status_conflict(tmp_path: Path):
    """CASE 2: Invalid bank amount + status conflict -> EXCEPTION: INVALID_ROW."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_002",
            "payment_id": "PAY-ADV-002",
            "order_id": "ORD-ADV-002",
            "captured_amount": "1000.00",
            "status": "failed",  # Status conflict
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-002",
            "payment_id": "PAY-ADV-002",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-002",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-002",
            "credit_amount": "NOT_A_NUMBER",  # Invalid amount
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    assert len(dataset.quarantined_rows) == 1

    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.INVALID_ROW
    assert res.settlement_id == "SET-ADV-002"
    assert res.payment_id == "PAY-ADV-002"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_03_missing_payment_id_plus_amount_mismatch(tmp_path: Path):
    """CASE 3: Missing payment ID + amount mismatch -> EXCEPTION: MISSING_PAYMENT_ID."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_003",
            "payment_id": "PAY-ADV-003",
            "order_id": "ORD-ADV-003",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-003",
            "payment_id": "",  # Blank payment ID
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-003",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-003",
            "credit_amount": "900.00",  # Disagreeing amount
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.MISSING_PAYMENT_ID
    assert res.settlement_id == "SET-ADV-003"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_04_missing_payment_id_plus_settlement_delay(tmp_path: Path):
    """CASE 4: Missing payment ID + settlement delay -> EXCEPTION: MISSING_PAYMENT_ID."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_004",
            "payment_id": "PAY-ADV-004",
            "order_id": "ORD-ADV-004",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-004",
            "payment_id": "",  # Blank payment ID
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-12T10:00:00",  # 11 days later (delay)
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-004",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-004",
            "credit_amount": "976.40",
            "credited_at": "2026-09-12T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.MISSING_PAYMENT_ID
    assert res.settlement_id == "SET-ADV-004"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_05_status_conflict_plus_amount_variance(tmp_path: Path):
    """CASE 5: Status conflict + amount variance -> EXCEPTION: STATUS_CONFLICT."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_005",
            "payment_id": "PAY-ADV-005",
            "order_id": "ORD-ADV-005",
            "captured_amount": "1000.00",
            "status": "failed",  # Status conflict
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-005",
            "payment_id": "PAY-ADV-005",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",  # Within 7 days
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-005",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-005",
            "credit_amount": "926.40",  # Amount variance > 0.01
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.STATUS_CONFLICT
    assert res.payment_id == "PAY-ADV-005"
    assert res.settlement_id == "SET-ADV-005"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_06_status_conflict_plus_settlement_delay(tmp_path: Path):
    """CASE 6: Status conflict + settlement delay -> EXCEPTION: STATUS_CONFLICT."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_006",
            "payment_id": "PAY-ADV-006",
            "order_id": "ORD-ADV-006",
            "captured_amount": "1000.00",
            "status": "failed",  # Status conflict
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-006",
            "payment_id": "PAY-ADV-006",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-11T10:00:00",  # 10 days later (delay)
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-006",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-006",
            "credit_amount": "976.40",
            "credited_at": "2026-09-11T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.STATUS_CONFLICT
    assert res.payment_id == "PAY-ADV-006"
    assert res.settlement_id == "SET-ADV-006"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_07_missing_reference_plus_amount_variance(tmp_path: Path):
    """CASE 7: Missing reference + amount variance -> EXCEPTION: MISSING_REFERENCE."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_007",
            "payment_id": "PAY-ADV-007",
            "order_id": "ORD-ADV-007",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-007",
            "payment_id": "PAY-ADV-007",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-007",
            "narration": "NEFT CREDIT UNRELATED",  # Missing reference to SET-ADV-007
            "credit_amount": "500.00",             # Wrong numeric amount
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.MISSING_REFERENCE
    assert res.settlement_id == "SET-ADV-007"
    assert res.payment_id == "PAY-ADV-007"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_08_settlement_delay_plus_amount_variance(tmp_path: Path):
    """CASE 8: Settlement delay + amount variance -> EXCEPTION: SETTLEMENT_DELAY."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_008",
            "payment_id": "PAY-ADV-008",
            "order_id": "ORD-ADV-008",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-008",
            "payment_id": "PAY-ADV-008",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-10T10:00:00",  # 9 days later (delay > 7)
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-008",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-008",
            "credit_amount": "876.40",  # Amount variance
            "credited_at": "2026-09-10T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.SETTLEMENT_DELAY
    assert res.settlement_id == "SET-ADV-008"
    assert res.payment_id == "PAY-ADV-008"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_09_ambiguous_bank_candidates_plus_amount_variance(tmp_path: Path):
    """CASE 9: Ambiguous bank candidates + amount variance -> EXCEPTION: AMBIGUOUS_CANDIDATES."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_009",
            "payment_id": "PAY-ADV-009",
            "order_id": "ORD-ADV-009",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-009",
            "payment_id": "PAY-ADV-009",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[
            {
                "bank_txn_id": "BANK-ADV-009A",
                "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-009",
                "credit_amount": "976.40",
                "credited_at": "2026-09-02T14:00:00",
            },
            {
                "bank_txn_id": "BANK-ADV-009B",
                "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-009 DUPLICATE",
                "credit_amount": "800.00",  # Different amount
                "credited_at": "2026-09-02T15:00:00",
            },
        ],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.AMBIGUOUS_CANDIDATES
    assert res.settlement_id == "SET-ADV-009"
    assert res.payment_id == "PAY-ADV-009"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_10_duplicate_payment_event_plus_invalid_bank_amount(tmp_path: Path):
    """CASE 10: Duplicate payment event + invalid bank amount -> EXCEPTION: INVALID_ROW + DUPLICATE_EVENT audit."""
    create_fixture_files(
        tmp_path,
        payments=[
            {
                "payment_event_id": "evt_adv_010",
                "payment_id": "PAY-ADV-010",
                "order_id": "ORD-ADV-010",
                "captured_amount": "1000.00",
                "status": "captured",
                "captured_at": "2026-09-01T10:00:00",
            },
            {
                "payment_event_id": "evt_adv_010",  # Identical duplicate event
                "payment_id": "PAY-ADV-010",
                "order_id": "ORD-ADV-010",
                "captured_amount": "1000.00",
                "status": "captured",
                "captured_at": "2026-09-01T10:00:00",
            },
        ],
        settlements=[{
            "settlement_id": "SET-ADV-010",
            "payment_id": "PAY-ADV-010",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-010",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-010",
            "credit_amount": "NOT_A_NUMBER",  # Invalid amount
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    # Loader deduplicates payment event and records audit log
    assert len(dataset.payments) == 1
    assert len(dataset.audit_logs) == 1
    assert dataset.audit_logs[0].event_type == "DUPLICATE_EVENT"
    assert len(dataset.quarantined_rows) == 1

    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.INVALID_ROW
    assert res.settlement_id == "SET-ADV-010"
    assert res.payment_id == "PAY-ADV-010"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)


def test_case_11_rounding_tolerance_boundary_accepted(tmp_path: Path):
    """CASE 11: Rounding tolerance boundary accepted (diff = ₹0.01) -> AUTO_MATCH."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_011",
            "payment_id": "PAY-ADV-011",
            "order_id": "ORD-ADV-011",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-011",
            "payment_id": "PAY-ADV-011",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-011",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-011",
            "credit_amount": "976.41",  # Exactly Decimal("0.01") variance
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.AUTO_MATCH
    assert res.exception_type is None
    assert res.payment_id == "PAY-ADV-011"
    assert res.settlement_id == "SET-ADV-011"
    assert res.bank_txn_id == "BANK-ADV-011"

    # Verify financial details are properly recorded
    assert "expected_net" in res.details
    assert "bank_credit_amount" in res.details
    assert res.details["expected_net"] == Decimal("976.40")
    assert res.details["bank_credit_amount"] == Decimal("976.41")
    assert abs(res.details["expected_net"] - res.details["bank_credit_amount"]) == Decimal("0.01")


def test_case_12_rounding_tolerance_rejection(tmp_path: Path):
    """CASE 12: Rounding tolerance boundary rejected (diff = ₹0.02) -> EXCEPTION: AMOUNT_VARIANCE."""
    create_fixture_files(
        tmp_path,
        payments=[{
            "payment_event_id": "evt_adv_012",
            "payment_id": "PAY-ADV-012",
            "order_id": "ORD-ADV-012",
            "captured_amount": "1000.00",
            "status": "captured",
            "captured_at": "2026-09-01T10:00:00",
        }],
        settlements=[{
            "settlement_id": "SET-ADV-012",
            "payment_id": "PAY-ADV-012",
            "gross_amount": "1000.00",
            "fee_amount": "20.00",
            "gst_on_fee": "3.60",
            "net_amount": "976.40",
            "settlement_status": "settled",
            "settled_at": "2026-09-02T10:00:00",
        }],
        bank_credits=[{
            "bank_txn_id": "BANK-ADV-012",
            "narration": "NEFT RAZORPAY SETTLEMENT SET-ADV-012",
            "credit_amount": "976.42",  # Exactly Decimal("0.02") variance (> 0.01)
            "credited_at": "2026-09-02T14:00:00",
        }],
    )
    dataset = load_dataset(data_dir=tmp_path)
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    res = result.results[0]
    assert res.match_status == MatchStatus.EXCEPTION
    assert res.exception_type == ExceptionType.AMOUNT_VARIANCE
    assert res.payment_id == "PAY-ADV-012"
    assert res.settlement_id == "SET-ADV-012"
    assert not any(r.match_status == MatchStatus.AUTO_MATCH for r in result.results)
