"""Unit tests for CSV loader and validation in ReconcileX."""

from decimal import Decimal
from pathlib import Path
import tempfile
import pytest

from backend.app.loader import load_dataset, load_truth_ledger, parse_datetime, parse_decimal


def test_parse_decimal():
    assert parse_decimal("100.50") == Decimal("100.50")
    assert parse_decimal("0") == Decimal("0")
    assert parse_decimal(None) is None
    assert parse_decimal("") is None
    assert parse_decimal("   ") is None


def test_parse_datetime():
    dt = parse_datetime("2026-08-25T10:00:00")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 8
    assert dt.day == 25
    assert dt.hour == 10
    assert parse_datetime("invalid-date") is None
    assert parse_datetime("") is None
    assert parse_datetime(None) is None


def test_load_dataset_from_default_dir():
    dataset = load_dataset("data/input")
    assert len(dataset.payments) > 0
    assert len(dataset.settlements) > 0
    assert len(dataset.bank_credits) > 0
    assert len(dataset.refunds) > 0

    # Ensure all amounts are Decimals
    for p in dataset.payments:
        assert isinstance(p.captured_amount, Decimal)
    for s in dataset.settlements:
        assert isinstance(s.gross_amount, Decimal)
        assert isinstance(s.net_amount, Decimal)
        assert isinstance(s.fee_amount, Decimal)
        assert isinstance(s.gst_on_fee, Decimal)
    for b in dataset.bank_credits:
        assert isinstance(b.credit_amount, Decimal)
    for r in dataset.refunds:
        assert isinstance(r.refund_amount, Decimal)


def test_load_dataset_duplicate_payment_event_audit():
    dataset = load_dataset("data/input")
    dup_logs = [a for a in dataset.audit_logs if a.event_type == "DUPLICATE_EVENT"]
    assert len(dup_logs) == 1
    assert dup_logs[0].entity_id == "evt_pay_012"

    # PAY-012 should only exist once in dataset.payments
    pay_012_records = [p for p in dataset.payments if p.payment_id == "PAY-012"]
    assert len(pay_012_records) == 1


def test_load_dataset_bank_015_quarantined():
    dataset = load_dataset("data/input")
    quarantined = [q for q in dataset.quarantined_rows if q.record_id == "BANK-015"]
    assert len(quarantined) == 1
    assert "Bank credit amount could not be parsed as Decimal." in quarantined[0].error_reason
    assert quarantined[0].reference == "SET-015"


def test_load_truth_ledger():
    truth = load_truth_ledger("data/evaluation/truth_ledger.csv")
    assert len(truth) == 15
    assert truth[0].truth_group_id == "TG-001"
    assert truth[0].expected_system_result == "AUTO_MATCH"
