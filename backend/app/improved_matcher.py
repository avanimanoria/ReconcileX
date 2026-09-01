"""Improved Deterministic Financial Reconciliation Engine for ReconcileX V1.1.

Implements strict, deterministic rule precedence including settlement timing,
refund-aware net amount calculation, settlement net validation, and bank credit amount validation.
Uses Decimal exclusively for all financial amounts.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Set

from .models import (
    AuditEntry,
    BankCreditRecord,
    Dataset,
    ExceptionType,
    InvalidRowRecord,
    MatchStatus,
    PaymentRecord,
    RefundRecord,
    ReconcileResult,
    ReconciliationBatchResult,
    SettlementRecord,
)

MONEY_TOLERANCE = Decimal("0.01")
MAX_SETTLEMENT_DELAY_DAYS = 7


class ImprovedMatcher:
    """Deterministic, refund-aware and timing-aware reconciliation matcher."""

    def __init__(self, tolerance: Decimal = MONEY_TOLERANCE, max_delay_days: int = MAX_SETTLEMENT_DELAY_DAYS) -> None:
        self.tolerance = tolerance
        self.max_delay_days = max_delay_days

    def reconcile(self, dataset: Dataset) -> ReconciliationBatchResult:
        results: List[ReconcileResult] = []
        audit_logs: List[AuditEntry] = list(dataset.audit_logs)
        quarantined_rows: List[InvalidRowRecord] = list(dataset.quarantined_rows)

        # Index payments by payment_id
        payment_map: Dict[str, PaymentRecord] = {
            p.payment_id: p for p in dataset.payments
        }

        # Index refunds by payment_id
        refunds_by_payment: Dict[str, List[RefundRecord]] = {}
        for r in dataset.refunds:
            refunds_by_payment.setdefault(r.payment_id, []).append(r)

        # Index quarantined bank records referencing a settlement_id
        quarantined_bank_by_settlement: Dict[str, InvalidRowRecord] = {}
        unreferenced_quarantined_banks: List[InvalidRowRecord] = []
        for q in quarantined_rows:
            ref_found = False
            if q.reference:
                quarantined_bank_by_settlement[q.reference] = q
                ref_found = True
            else:
                narration = q.raw_data.get("narration", "")
                for s in dataset.settlements:
                    if s.settlement_id in narration:
                        quarantined_bank_by_settlement[s.settlement_id] = q
                        ref_found = True
            if not ref_found and q.source_file == "bank_credits.csv":
                unreferenced_quarantined_banks.append(q)

        matched_payment_ids: Set[str] = set()
        matched_settlement_ids: Set[str] = set()
        matched_bank_txn_ids: Set[str] = set()

        for settlement in dataset.settlements:
            settlement_id = settlement.settlement_id
            payment_id = settlement.payment_id

            # Rule 1: Check if linked quarantined/invalid row exists for this settlement
            quarantined_bank = quarantined_bank_by_settlement.get(settlement_id)
            if not quarantined_bank and unreferenced_quarantined_banks:
                matching_valid = [b for b in dataset.bank_credits if settlement_id in b.narration]
                if not matching_valid:
                    quarantined_bank = unreferenced_quarantined_banks[0]
            if quarantined_bank:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.INVALID_ROW,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        bank_txn_id=quarantined_bank.record_id,
                        reason=quarantined_bank.error_reason,
                        details={"source_file": quarantined_bank.source_file, "raw_data": quarantined_bank.raw_data},
                    )
                )
                continue

            # Rule 2: MISSING_PAYMENT_ID
            if not payment_id:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.MISSING_PAYMENT_ID,
                        settlement_id=settlement_id,
                        reason=f"Settlement '{settlement_id}' has a missing or empty payment_id.",
                    )
                )
                continue

            # Rule 3: UNMATCHED (payment_id not found in dataset)
            payment = payment_map.get(payment_id)
            if not payment:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.UNMATCHED,
                        settlement_id=settlement_id,
                        payment_id=payment_id,
                        reason=f"Payment record '{payment_id}' referenced by settlement '{settlement_id}' was not found.",
                    )
                )
                continue

            # Rule 4: STATUS_CONFLICT (payment status is not 'captured')
            if payment.status != "captured":
                # Find any bank credit for reference retention
                matching_banks_for_ref = [b for b in dataset.bank_credits if settlement_id in b.narration]
                bank_ref_id = matching_banks_for_ref[0].bank_txn_id if matching_banks_for_ref else None
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.STATUS_CONFLICT,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        bank_txn_id=bank_ref_id,
                        reason=f"Payment '{payment_id}' status is '{payment.status}'; only 'captured' payments are eligible for reconciliation.",
                    )
                )
                continue

            # Rule 5: MISSING_REFERENCE (search valid bank credits for exact settlement_id in narration)
            matching_banks: List[BankCreditRecord] = [
                b for b in dataset.bank_credits if settlement_id in b.narration
            ]

            if not matching_banks:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.MISSING_REFERENCE,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        reason=f"No bank credit record found containing settlement_id '{settlement_id}' in narration.",
                    )
                )
                continue

            # Rule 6: AMBIGUOUS_CANDIDATES (more than one bank record matches settlement_id)
            if len(matching_banks) > 1:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.AMBIGUOUS_CANDIDATES,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        reason=f"Multiple bank credits ({len(matching_banks)}) matched settlement_id '{settlement_id}'.",
                    )
                )
                continue

            bank_credit = matching_banks[0]

            # Rule 7: SETTLEMENT_DELAY (settlement date > 7 calendar days after capture)
            settlement_delay_days = 0
            if settlement.settled_at and payment.captured_at:
                settlement_delay_days = (settlement.settled_at.date() - payment.captured_at.date()).days
                if settlement_delay_days > self.max_delay_days:
                    results.append(
                        ReconcileResult(
                            match_status=MatchStatus.EXCEPTION,
                            exception_type=ExceptionType.SETTLEMENT_DELAY,
                            payment_id=payment_id,
                            settlement_id=settlement_id,
                            bank_txn_id=bank_credit.bank_txn_id,
                            reason=f"Settlement is {settlement_delay_days} days after payment; policy maximum is {self.max_delay_days} days.",
                            details={
                                "payment_date": payment.captured_at.date().isoformat(),
                                "settlement_date": settlement.settled_at.date().isoformat(),
                                "delay_days": settlement_delay_days,
                                "max_allowed_days": self.max_delay_days,
                            },
                        )
                    )
                    continue

            # Rule 8: REFUND-AWARE EXPECTED NET
            # Sum only refunds for this payment that are "processed" and occurred on or before settlement date
            payment_refunds = refunds_by_payment.get(payment_id, [])
            eligible_refunds = [
                r for r in payment_refunds
                if r.refund_status == "processed" and (
                    settlement.settled_at is None or r.refunded_at is None or r.refunded_at <= settlement.settled_at
                )
            ]
            total_processed_refunds = sum((r.refund_amount for r in eligible_refunds), Decimal("0"))
            eligible_amount = payment.captured_amount - total_processed_refunds
            expected_net = eligible_amount - settlement.fee_amount - settlement.gst_on_fee

            refund_ids = [r.refund_id for r in eligible_refunds]
            primary_refund_id = refund_ids[0] if refund_ids else None

            financial_details = {
                "captured_amount": payment.captured_amount,
                "total_processed_refunds": total_processed_refunds,
                "eligible_amount": eligible_amount,
                "fee_amount": settlement.fee_amount,
                "gst_on_fee": settlement.gst_on_fee,
                "expected_net": expected_net,
                "settlement_net_amount": settlement.net_amount,
                "bank_credit_amount": bank_credit.credit_amount,
                "settlement_delay_days": settlement_delay_days,
                "money_tolerance": self.tolerance,
                "refund_ids": refund_ids,
            }

            # Rule 9: SETTLEMENT NET VALIDATION
            diff_settlement = abs(expected_net - settlement.net_amount)
            if diff_settlement > self.tolerance:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.AMOUNT_VARIANCE,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        bank_txn_id=bank_credit.bank_txn_id,
                        refund_id=primary_refund_id,
                        reason=f"Settlement net amount INR {settlement.net_amount} differs from expected net INR {expected_net} (diff: INR {diff_settlement}).",
                        details=financial_details,
                    )
                )
                continue

            # Rule 10: BANK CREDIT VALIDATION
            diff_bank = abs(expected_net - bank_credit.credit_amount)
            if diff_bank > self.tolerance:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.AMOUNT_VARIANCE,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        bank_txn_id=bank_credit.bank_txn_id,
                        refund_id=primary_refund_id,
                        reason=f"Expected INR {expected_net} but bank credit is INR {bank_credit.credit_amount} (diff: INR {diff_bank}).",
                        details=financial_details,
                    )
                )
                continue

            # Rule 11: AUTO_MATCH
            match_reason = "Payment ID, settlement ID, and net amount all match"
            if total_processed_refunds > Decimal("0"):
                match_reason = f"Refund explains reduced net amount (processed refunds: INR {total_processed_refunds})"

            results.append(
                ReconcileResult(
                    match_status=MatchStatus.AUTO_MATCH,
                    payment_id=payment_id,
                    settlement_id=settlement_id,
                    bank_txn_id=bank_credit.bank_txn_id,
                    refund_id=primary_refund_id,
                    reason=match_reason,
                    details=financial_details,
                )
            )
            matched_payment_ids.add(payment_id)
            matched_settlement_ids.add(settlement_id)
            matched_bank_txn_ids.add(bank_credit.bank_txn_id)

        return ReconciliationBatchResult(
            results=results,
            audit_logs=audit_logs,
            quarantined_rows=quarantined_rows,
        )


def run_improved_reconciliation(dataset: Dataset) -> ReconciliationBatchResult:
    """Convenience function to run improved reconciliation on a dataset."""
    matcher = ImprovedMatcher()
    return matcher.reconcile(dataset)
