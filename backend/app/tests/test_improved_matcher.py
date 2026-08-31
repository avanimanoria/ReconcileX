"""Unit tests for the improved deterministic financial validator in ReconcileX V1.1."""

from datetime import datetime
from decimal import Decimal
import pytest

from backend.app.evaluator import evaluate_results
from backend.app.improved_matcher import ImprovedMatcher, run_improved_reconciliation
from backend.app.loader import load_dataset, load_truth_ledger
from backend.app.models import (
    BankCreditRecord,
    Dataset,
    ExceptionType,
    MatchStatus,
    PaymentRecord,
    RefundRecord,
    SettlementRecord,
)


@pytest.fixture
def dataset() -> Dataset:
    return load_dataset("data/input")


def test_set_005_is_settlement_delay(dataset: Dataset):
    """SET-005 settled 9 days after payment capture must return SETTLEMENT_DELAY."""
    batch_result = run_improved_reconciliation(dataset)
    res_005 = next(r for r in batch_result.results if r.settlement_id == "SET-005")

    assert res_005.match_status == MatchStatus.EXCEPTION
    assert res_005.exception_type == ExceptionType.SETTLEMENT_DELAY
    assert res_005.payment_id == "PAY-005"
    assert res_005.details["delay_days"] == 9
    assert res_005.details["max_allowed_days"] == 7


def test_set_007_is_amount_variance(dataset: Dataset):
    """SET-007 has expected net 1952.80 but bank credit 1900.00 -> AMOUNT_VARIANCE."""
    batch_result = run_improved_reconciliation(dataset)
    res_007 = next(r for r in batch_result.results if r.settlement_id == "SET-007")

    assert res_007.match_status == MatchStatus.EXCEPTION
    assert res_007.exception_type == ExceptionType.AMOUNT_VARIANCE
    assert res_007.payment_id == "PAY-007"
    assert res_007.details["expected_net"] == Decimal("1952.80")
    assert res_007.details["bank_credit_amount"] == Decimal("1900.00")
    assert res_007.details["settlement_net_amount"] == Decimal("1952.80")


def test_pay_003_validates_refund_adjusted_net(dataset: Dataset):
    """PAY-003 with ₹200 processed refund must compute expected net 781.12 and AUTO_MATCH."""
    batch_result = run_improved_reconciliation(dataset)
    res_003 = next(r for r in batch_result.results if r.settlement_id == "SET-003")

    assert res_003.match_status == MatchStatus.AUTO_MATCH
    assert res_003.payment_id == "PAY-003"
    assert res_003.details["total_processed_refunds"] == Decimal("200.00")
    assert res_003.details["captured_amount"] == Decimal("1000")
    assert res_003.details["eligible_amount"] == Decimal("800")
    assert res_003.details["fee_amount"] == Decimal("16")
    assert res_003.details["gst_on_fee"] == Decimal("2.88")
    assert res_003.details["expected_net"] == Decimal("781.12")
    assert res_003.details["settlement_net_amount"] == Decimal("781.12")
    assert res_003.details["bank_credit_amount"] == Decimal("781.12")


def test_pay_011_validates_refund_adjusted_net(dataset: Dataset):
    """PAY-011 with ₹750 processed refund must compute expected net 2196.90 and AUTO_MATCH."""
    batch_result = run_improved_reconciliation(dataset)
    res_011 = next(r for r in batch_result.results if r.settlement_id == "SET-011")

    assert res_011.match_status == MatchStatus.AUTO_MATCH
    assert res_011.payment_id == "PAY-011"
    assert res_011.details["total_processed_refunds"] == Decimal("750.00")
    assert res_011.details["captured_amount"] == Decimal("3000")
    assert res_011.details["eligible_amount"] == Decimal("2250")
    assert res_011.details["fee_amount"] == Decimal("45")
    assert res_011.details["gst_on_fee"] == Decimal("8.1")
    assert res_011.details["expected_net"] == Decimal("2196.90")
    assert res_011.details["settlement_net_amount"] == Decimal("2196.90")
    assert res_011.details["bank_credit_amount"] == Decimal("2196.90")


def test_exact_match_validates_money(dataset: Dataset):
    """PAY-001 exact match validates all amounts equal Decimal('976.40')."""
    batch_result = run_improved_reconciliation(dataset)
    res_001 = next(r for r in batch_result.results if r.settlement_id == "SET-001")

    assert res_001.match_status == MatchStatus.AUTO_MATCH
    assert res_001.payment_id == "PAY-001"
    assert res_001.details["expected_net"] == Decimal("976.40")
    assert res_001.details["settlement_net_amount"] == Decimal("976.40")
    assert res_001.details["bank_credit_amount"] == Decimal("976.40")


def test_invalid_row_has_precedence(dataset: Dataset):
    """SET-015 linked to quarantined BANK-015 returns INVALID_ROW before any amount check."""
    batch_result = run_improved_reconciliation(dataset)
    res_015 = next(r for r in batch_result.results if r.settlement_id == "SET-015")

    assert res_015.match_status == MatchStatus.EXCEPTION
    assert res_015.exception_type == ExceptionType.INVALID_ROW
    assert res_015.payment_id == "PAY-015"
    assert res_015.settlement_id == "SET-015"
    assert res_015.bank_txn_id == "BANK-015"


def test_status_conflict_has_precedence(dataset: Dataset):
    """SET-014 linked to failed payment PAY-014 returns STATUS_CONFLICT."""
    batch_result = run_improved_reconciliation(dataset)
    res_014 = next(r for r in batch_result.results if r.settlement_id == "SET-014")

    assert res_014.match_status == MatchStatus.EXCEPTION
    assert res_014.exception_type == ExceptionType.STATUS_CONFLICT
    assert res_014.payment_id == "PAY-014"


def test_missing_reference_has_precedence_over_financial_validation(dataset: Dataset):
    """SET-006 narration lacks SET-006 reference, returning MISSING_REFERENCE before amount check."""
    batch_result = run_improved_reconciliation(dataset)
    res_006 = next(r for r in batch_result.results if r.settlement_id == "SET-006")

    assert res_006.match_status == MatchStatus.EXCEPTION
    assert res_006.exception_type == ExceptionType.MISSING_REFERENCE
    assert res_006.payment_id == "PAY-006"


def test_exactly_seven_days_is_allowed():
    """Settlement date exactly 7 days after payment capture must AUTO_MATCH."""
    dataset = Dataset(
        payments=[
            PaymentRecord(
                payment_event_id="evt_test_7d",
                payment_id="PAY-7D",
                order_id="ORD-7D",
                captured_amount=Decimal("1000"),
                status="captured",
                captured_at=datetime(2026, 8, 1, 10, 0, 0),
            )
        ],
        settlements=[
            SettlementRecord(
                settlement_id="SET-7D",
                payment_id="PAY-7D",
                gross_amount=Decimal("1000"),
                fee_amount=Decimal("20"),
                gst_on_fee=Decimal("3.60"),
                net_amount=Decimal("976.40"),
                settlement_status="settled",
                settled_at=datetime(2026, 8, 8, 10, 0, 0),  # Exactly 7 days
            )
        ],
        bank_credits=[
            BankCreditRecord(
                bank_txn_id="BANK-7D",
                narration="NEFT RAZORPAY SETTLEMENT SET-7D",
                credit_amount=Decimal("976.40"),
                credited_at=datetime(2026, 8, 8, 12, 0, 0),
            )
        ],
    )
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    assert result.results[0].match_status == MatchStatus.AUTO_MATCH
    assert result.results[0].details["settlement_delay_days"] == 7


def test_more_than_seven_days_is_rejected():
    """Settlement date 8 days after payment capture must return SETTLEMENT_DELAY."""
    dataset = Dataset(
        payments=[
            PaymentRecord(
                payment_event_id="evt_test_8d",
                payment_id="PAY-8D",
                order_id="ORD-8D",
                captured_amount=Decimal("1000"),
                status="captured",
                captured_at=datetime(2026, 8, 1, 10, 0, 0),
            )
        ],
        settlements=[
            SettlementRecord(
                settlement_id="SET-8D",
                payment_id="PAY-8D",
                gross_amount=Decimal("1000"),
                fee_amount=Decimal("20"),
                gst_on_fee=Decimal("3.60"),
                net_amount=Decimal("976.40"),
                settlement_status="settled",
                settled_at=datetime(2026, 8, 9, 10, 0, 0),  # 8 days
            )
        ],
        bank_credits=[
            BankCreditRecord(
                bank_txn_id="BANK-8D",
                narration="NEFT RAZORPAY SETTLEMENT SET-8D",
                credit_amount=Decimal("976.40"),
                credited_at=datetime(2026, 8, 9, 12, 0, 0),
            )
        ],
    )
    matcher = ImprovedMatcher()
    result = matcher.reconcile(dataset)

    assert len(result.results) == 1
    assert result.results[0].match_status == MatchStatus.EXCEPTION
    assert result.results[0].exception_type == ExceptionType.SETTLEMENT_DELAY
    assert result.results[0].details["delay_days"] == 8


def test_improved_engine_matches_all_truth_scenarios(dataset: Dataset):
    """Run full improved engine against CSVs and evaluate against truth ledger."""
    batch_result = run_improved_reconciliation(dataset)
    truth_records = load_truth_ledger("data/evaluation/truth_ledger.csv")

    report = evaluate_results(batch_result, truth_records, engine_name="improved")

    assert report.total_scenarios == 15
    assert report.exact_matches == 15
    assert report.mismatches == 0
    assert report.accuracy == 100.0

    # Verify counts: 8 AUTO_MATCH (including TG-012), 7 EXCEPTION
    auto_matches = [c for c in report.comparisons if "AUTO_MATCH" in c.actual_result]
    exceptions = [c for c in report.comparisons if "EXCEPTION" in c.actual_result]
    assert len(auto_matches) == 8
    assert len(exceptions) == 7
