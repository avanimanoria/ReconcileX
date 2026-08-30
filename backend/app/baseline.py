"""Baseline reconciliation engine for ReconcileX V1.

Implements conservative baseline matching rules without side-effects or external dependencies.
"""

from typing import Dict, List, Optional, Set

from .models import (
    AuditEntry,
    BankCreditRecord,
    Dataset,
    ExceptionType,
    InvalidRowRecord,
    MatchStatus,
    PaymentRecord,
    ReconcileResult,
    ReconciliationBatchResult,
    SettlementRecord,
)


class BaselineMatcher:
    """Deterministic, conservative baseline reconciliation matcher."""

    def __init__(self) -> None:
        pass

    def reconcile(self, dataset: Dataset) -> ReconciliationBatchResult:
        results: List[ReconcileResult] = []
        audit_logs: List[AuditEntry] = list(dataset.audit_logs)
        quarantined_rows: List[InvalidRowRecord] = list(dataset.quarantined_rows)

        # Index payments by payment_id
        payment_map: Dict[str, PaymentRecord] = {
            p.payment_id: p for p in dataset.payments
        }

        # Index quarantined bank records referencing a settlement_id
        quarantined_bank_by_settlement: Dict[str, InvalidRowRecord] = {}
        for q in quarantined_rows:
            if q.reference:
                quarantined_bank_by_settlement[q.reference] = q
            else:
                # Also inspect raw narration if reference wasn't directly extracted
                narration = q.raw_data.get("narration", "")
                for s in dataset.settlements:
                    if s.settlement_id in narration:
                        quarantined_bank_by_settlement[s.settlement_id] = q

        matched_payment_ids: Set[str] = set()
        matched_settlement_ids: Set[str] = set()
        matched_bank_txn_ids: Set[str] = set()

        for settlement in dataset.settlements:
            settlement_id = settlement.settlement_id
            payment_id = settlement.payment_id

            # Rule 3 & 7: Check for missing payment_id in settlement
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

            # Lookup payment
            payment = payment_map.get(payment_id)

            # Rule 7: Payment not found in payment dataset
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

            # Find matching bank records by searching for settlement_id in narration
            matching_banks: List[BankCreditRecord] = [
                b for b in dataset.bank_credits if settlement_id in b.narration
            ]

            # Check if there is a quarantined bank record linked to this settlement
            quarantined_bank = quarantined_bank_by_settlement.get(settlement_id)

            # Rule 2 & 7: Payment status validation
            if payment.status != "captured":
                bank_txn_id = matching_banks[0].bank_txn_id if matching_banks else (
                    quarantined_bank.record_id if quarantined_bank else None
                )
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.STATUS_CONFLICT,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        bank_txn_id=bank_txn_id,
                        reason=f"Payment '{payment_id}' status is '{payment.status}'; only 'captured' payments are eligible for reconciliation.",
                    )
                )
                continue

            # Rule 8: Quarantined invalid bank row linked to this settlement
            if quarantined_bank:
                results.append(
                    ReconcileResult(
                        match_status=MatchStatus.EXCEPTION,
                        exception_type=ExceptionType.INVALID_ROW,
                        payment_id=payment_id,
                        settlement_id=settlement_id,
                        bank_txn_id=quarantined_bank.record_id,
                        reason=quarantined_bank.error_reason,
                    )
                )
                continue

            # Rule 4 & 7: Bank record reference linkage
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

            # Exactly one bank credit linked
            bank_credit = matching_banks[0]

            # Rule 6: All baseline conditions satisfied -> AUTO_MATCH
            results.append(
                ReconcileResult(
                    match_status=MatchStatus.AUTO_MATCH,
                    payment_id=payment_id,
                    settlement_id=settlement_id,
                    bank_txn_id=bank_credit.bank_txn_id,
                    reason=f"Valid payment '{payment_id}', settlement '{settlement_id}', and bank credit '{bank_credit.bank_txn_id}' matched.",
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


def run_baseline_reconciliation(dataset: Dataset) -> ReconciliationBatchResult:
    """Convenience function to run baseline reconciliation on a dataset."""
    matcher = BaselineMatcher()
    return matcher.reconcile(dataset)
