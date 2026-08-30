"""Unit tests for baseline reconciliation matcher in ReconcileX."""

from decimal import Decimal
import pytest

from backend.app.baseline import BaselineMatcher, run_baseline_reconciliation
from backend.app.loader import load_dataset
from backend.app.models import (
    BankCreditRecord,
    Dataset,
    ExceptionType,
    InvalidRowRecord,
    MatchStatus,
    PaymentRecord,
    SettlementRecord,
)


@pytest.fixture
def loaded_dataset() -> Dataset:
    return load_dataset("data/input")


def test_normal_exact_match(loaded_dataset: Dataset):
    """Test standard 3-way match (PAY-001 -> SET-001 -> BANK-001)."""
    matcher = BaselineMatcher()
    result = matcher.reconcile(loaded_dataset)

    res_001 = next(r for r in result.results if r.settlement_id == "SET-001")
    assert res_001.match_status == MatchStatus.AUTO_MATCH
    assert res_001.payment_id == "PAY-001"
    assert res_001.settlement_id == "SET-001"
    assert res_001.bank_txn_id == "BANK-001"
    assert res_001.exception_type is None
    assert "matched" in res_001.reason.lower()


def test_pay_012_duplicate_ingestion(loaded_dataset: Dataset):
    """Test duplicate payment event ingestion (idempotency + single AUTO_MATCH + duplicate audit)."""
    matcher = BaselineMatcher()
    result = matcher.reconcile(loaded_dataset)

    # PAY-012 should produce exactly one reconciliation result
    res_012_list = [r for r in result.results if r.payment_id == "PAY-012"]
    assert len(res_012_list) == 1
    res_012 = res_012_list[0]
    assert res_012.match_status == MatchStatus.AUTO_MATCH
    assert res_012.settlement_id == "SET-012"
    assert res_012.bank_txn_id == "BANK-012"

    # Exactly one DUPLICATE_EVENT audit entry
    dup_audits = [a for a in result.audit_logs if a.event_type == "DUPLICATE_EVENT"]
    assert len(dup_audits) == 1
    assert dup_audits[0].entity_id == "evt_pay_012"


def test_set_013_missing_payment_id(loaded_dataset: Dataset):
    """Test settlement SET-013 with blank payment_id produces MISSING_PAYMENT_ID exception."""
    matcher = BaselineMatcher()
    result = matcher.reconcile(loaded_dataset)

    res_013 = next(r for r in result.results if r.settlement_id == "SET-013")
    assert res_013.match_status == MatchStatus.EXCEPTION
    assert res_013.exception_type == ExceptionType.MISSING_PAYMENT_ID
    assert "missing or empty payment_id" in res_013.reason.lower()


def test_pay_014_failed_status_conflict(loaded_dataset: Dataset):
    """Test payment PAY-014 with status 'failed' produces STATUS_CONFLICT exception."""
    matcher = BaselineMatcher()
    result = matcher.reconcile(loaded_dataset)

    res_014 = next(r for r in result.results if r.settlement_id == "SET-014")
    assert res_014.match_status == MatchStatus.EXCEPTION
    assert res_014.exception_type == ExceptionType.STATUS_CONFLICT
    assert res_014.payment_id == "PAY-014"
    assert "failed" in res_014.reason.lower()


def test_bank_015_invalid_amount(loaded_dataset: Dataset):
    """Test BANK-015 with invalid credit_amount produces INVALID_ROW exception."""
    matcher = BaselineMatcher()
    result = matcher.reconcile(loaded_dataset)

    res_015 = next(r for r in result.results if r.settlement_id == "SET-015")
    assert res_015.match_status == MatchStatus.EXCEPTION
    assert res_015.exception_type == ExceptionType.INVALID_ROW
    assert res_015.payment_id == "PAY-015"
    assert res_015.settlement_id == "SET-015"
    assert res_015.bank_txn_id == "BANK-015"
    assert "could not be parsed as Decimal" in res_015.reason


def test_missing_bank_settlement_reference(loaded_dataset: Dataset):
    """Test missing settlement ID in bank narration produces MISSING_REFERENCE."""
    matcher = BaselineMatcher()
    result = matcher.reconcile(loaded_dataset)

    # SET-006 narration is "NEFT CREDIT" without SET-006
    res_006 = next(r for r in result.results if r.settlement_id == "SET-006")
    assert res_006.match_status == MatchStatus.EXCEPTION
    assert res_006.exception_type == ExceptionType.MISSING_REFERENCE

    # SET-008 narration is "IMPS RAZORPAY PAYOUT" without SET-008
    res_008 = next(r for r in result.results if r.settlement_id == "SET-008")
    assert res_008.match_status == MatchStatus.EXCEPTION
    assert res_008.exception_type == ExceptionType.MISSING_REFERENCE


def test_unmatched_payment():
    """Test unmatched payment when settlement references non-existent payment ID."""
    dataset = Dataset(
        payments=[],
        settlements=[
            SettlementRecord(
                settlement_id="SET-999",
                payment_id="PAY-999",
                gross_amount=Decimal("100"),
                fee_amount=Decimal("2"),
                gst_on_fee=Decimal("0.36"),
                net_amount=Decimal("97.64"),
                settlement_status="settled",
            )
        ],
        bank_credits=[
            BankCreditRecord(
                bank_txn_id="BANK-999",
                narration="NEFT SET-999",
                credit_amount=Decimal("97.64"),
            )
        ],
    )
    result = run_baseline_reconciliation(dataset)
    assert len(result.results) == 1
    assert result.results[0].match_status == MatchStatus.EXCEPTION
    assert result.results[0].exception_type == ExceptionType.UNMATCHED
