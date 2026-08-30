"""Data models and type definitions for ReconcileX V1."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class MatchStatus(str, Enum):
    AUTO_MATCH = "AUTO_MATCH"
    EXCEPTION = "EXCEPTION"


class ExceptionType(str, Enum):
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    MISSING_PAYMENT_ID = "MISSING_PAYMENT_ID"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    STATUS_CONFLICT = "STATUS_CONFLICT"
    INVALID_ROW = "INVALID_ROW"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS_CANDIDATES = "AMBIGUOUS_CANDIDATES"
    AMOUNT_VARIANCE = "AMOUNT_VARIANCE"
    SETTLEMENT_DELAY = "SETTLEMENT_DELAY"


@dataclass(frozen=True)
class PaymentRecord:
    payment_event_id: str
    payment_id: str
    order_id: str
    captured_amount: Decimal
    status: str
    captured_at: Optional[datetime] = None


@dataclass(frozen=True)
class SettlementRecord:
    settlement_id: str
    payment_id: Optional[str]
    gross_amount: Decimal
    fee_amount: Decimal
    gst_on_fee: Decimal
    net_amount: Decimal
    settlement_status: str
    settled_at: Optional[datetime] = None


@dataclass(frozen=True)
class BankCreditRecord:
    bank_txn_id: str
    narration: str
    credit_amount: Decimal
    credited_at: Optional[datetime] = None


@dataclass(frozen=True)
class RefundRecord:
    refund_id: str
    payment_id: str
    refund_amount: Decimal
    refund_status: str
    refunded_at: Optional[datetime] = None


@dataclass
class InvalidRowRecord:
    source_file: str
    raw_data: Dict[str, str]
    error_reason: str
    record_id: Optional[str] = None
    reference: Optional[str] = None


@dataclass
class AuditEntry:
    event_type: str
    entity_id: str
    reason: str
    timestamp: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconcileResult:
    match_status: MatchStatus
    exception_type: Optional[ExceptionType] = None
    payment_id: Optional[str] = None
    settlement_id: Optional[str] = None
    bank_txn_id: Optional[str] = None
    refund_id: Optional[str] = None
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def display_result(self) -> str:
        if self.match_status == MatchStatus.AUTO_MATCH:
            return "AUTO_MATCH"
        if self.exception_type:
            return f"EXCEPTION: {self.exception_type.value}"
        return "EXCEPTION"


@dataclass
class Dataset:
    payments: List[PaymentRecord] = field(default_factory=list)
    settlements: List[SettlementRecord] = field(default_factory=list)
    bank_credits: List[BankCreditRecord] = field(default_factory=list)
    refunds: List[RefundRecord] = field(default_factory=list)
    quarantined_rows: List[InvalidRowRecord] = field(default_factory=list)
    audit_logs: List[AuditEntry] = field(default_factory=list)


@dataclass
class ReconciliationBatchResult:
    results: List[ReconcileResult] = field(default_factory=list)
    audit_logs: List[AuditEntry] = field(default_factory=list)
    quarantined_rows: List[InvalidRowRecord] = field(default_factory=list)


@dataclass(frozen=True)
class TruthRecord:
    truth_group_id: str
    scenario: str
    payment_record: str
    settlement_record: str
    bank_record: str
    refund_record: str
    expected_system_result: str
    reason: str


@dataclass
class EvaluationComparison:
    truth_group_id: str
    scenario: str
    payment_id: Optional[str]
    settlement_id: Optional[str]
    bank_txn_id: Optional[str]
    expected_result: str
    actual_result: str
    is_match: bool
    notes: str = ""


@dataclass
class EvaluationReport:
    total_scenarios: int
    exact_matches: int
    mismatches: int
    accuracy: float
    comparisons: List[EvaluationComparison] = field(default_factory=list)
    known_baseline_limitations: List[str] = field(default_factory=list)
