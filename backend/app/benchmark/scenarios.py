"""Scenario definitions and deterministic distribution allocations for ReconcileX Benchmark."""

from enum import Enum
from typing import Dict, List


class ScenarioType(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    VALID_REFUND = "VALID_REFUND"
    SETTLEMENT_DELAY = "SETTLEMENT_DELAY"
    AMOUNT_VARIANCE = "AMOUNT_VARIANCE"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    MISSING_PAYMENT_ID = "MISSING_PAYMENT_ID"
    STATUS_CONFLICT = "STATUS_CONFLICT"
    INVALID_BANK_AMOUNT = "INVALID_BANK_AMOUNT"
    DUPLICATE_PAYMENT_EVENT = "DUPLICATE_PAYMENT_EVENT"


# Target weights for dev and heldout splits (sum = 100)
STANDARD_SPLIT_WEIGHTS: Dict[ScenarioType, int] = {
    ScenarioType.EXACT_MATCH: 45,
    ScenarioType.VALID_REFUND: 15,
    ScenarioType.SETTLEMENT_DELAY: 8,
    ScenarioType.AMOUNT_VARIANCE: 8,
    ScenarioType.MISSING_REFERENCE: 7,
    ScenarioType.MISSING_PAYMENT_ID: 5,
    ScenarioType.STATUS_CONFLICT: 5,
    ScenarioType.INVALID_BANK_AMOUNT: 4,
    ScenarioType.DUPLICATE_PAYMENT_EVENT: 3,
}

# Target weights for chaos split (sum = 100)
CHAOS_SPLIT_WEIGHTS: Dict[ScenarioType, int] = {
    ScenarioType.EXACT_MATCH: 15,
    ScenarioType.VALID_REFUND: 10,
    ScenarioType.SETTLEMENT_DELAY: 10,
    ScenarioType.AMOUNT_VARIANCE: 15,
    ScenarioType.MISSING_REFERENCE: 15,
    ScenarioType.MISSING_PAYMENT_ID: 10,
    ScenarioType.STATUS_CONFLICT: 10,
    ScenarioType.INVALID_BANK_AMOUNT: 10,
    ScenarioType.DUPLICATE_PAYMENT_EVENT: 5,
}

# Mapping of scenario type to truth expected result string
SCENARIO_EXPECTED_RESULTS: Dict[ScenarioType, str] = {
    ScenarioType.EXACT_MATCH: "AUTO_MATCH",
    ScenarioType.VALID_REFUND: "AUTO_MATCH",
    ScenarioType.SETTLEMENT_DELAY: "EXCEPTION: SETTLEMENT_DELAY",
    ScenarioType.AMOUNT_VARIANCE: "EXCEPTION: AMOUNT_VARIANCE",
    ScenarioType.MISSING_REFERENCE: "EXCEPTION: MISSING_REFERENCE",
    ScenarioType.MISSING_PAYMENT_ID: "EXCEPTION: MISSING_PAYMENT_ID",
    ScenarioType.STATUS_CONFLICT: "EXCEPTION: STATUS_CONFLICT",
    ScenarioType.INVALID_BANK_AMOUNT: "EXCEPTION: INVALID_ROW",
    ScenarioType.DUPLICATE_PAYMENT_EVENT: "AUTO_MATCH + DUPLICATE_AUDIT",
}

# Mapping of scenario type to truth reason description
SCENARIO_REASONS: Dict[ScenarioType, str] = {
    ScenarioType.EXACT_MATCH: "Payment ID, settlement ID, and net amount all match",
    ScenarioType.VALID_REFUND: "Refund explains reduced net amount",
    ScenarioType.SETTLEMENT_DELAY: "Settlement occurs more than 7 days after payment capture",
    ScenarioType.AMOUNT_VARIANCE: "Bank credit differs from expected net amount",
    ScenarioType.MISSING_REFERENCE: "Bank narration does not contain settlement ID",
    ScenarioType.MISSING_PAYMENT_ID: "Settlement record has a blank payment_id",
    ScenarioType.STATUS_CONFLICT: "Payment status is failed; only captured payments are eligible",
    ScenarioType.INVALID_BANK_AMOUNT: "Bank credit amount is NOT_A_NUMBER and quarantined as INVALID_ROW",
    ScenarioType.DUPLICATE_PAYMENT_EVENT: "One payment is reconciled; duplicate event is ignored and audited",
}


def allocate_scenario_counts(count: int, split: str = "dev") -> Dict[ScenarioType, int]:
    """Deterministically allocate integer scenario counts using the Largest Remainder Method.
    
    Guarantees:
    - sum(counts.values()) == count exactly
    - deterministic for any given count and split
    - when count >= 100, every scenario type receives at least 1 count
    """
    if count <= 0:
        return {st: 0 for st in ScenarioType}

    weights = CHAOS_SPLIT_WEIGHTS if split == "chaos" else STANDARD_SPLIT_WEIGHTS
    total_weight = sum(weights.values())

    # Step 1: Compute floor counts and fractional remainders
    exact_shares = {st: (count * weights[st]) / total_weight for st in weights}
    allocated_counts = {st: int(exact_shares[st]) for st in weights}
    remainders = {st: exact_shares[st] - allocated_counts[st] for st in weights}

    remaining_seats = count - sum(allocated_counts.values())

    # Step 2: Distribute remaining seats by largest fractional remainder
    # Sort by remainder descending, breaking ties with scenario definition order (index in enum list)
    scenario_order = list(weights.keys())
    sorted_scenarios = sorted(
        scenario_order,
        key=lambda st: (remainders[st], -scenario_order.index(st)),
        reverse=True,
    )

    for i in range(remaining_seats):
        st = sorted_scenarios[i % len(sorted_scenarios)]
        allocated_counts[st] += 1

    # Guarantee all scenario types are present when count >= 100
    if count >= 100:
        for st in scenario_order:
            if allocated_counts[st] == 0:
                # Borrow 1 count from the scenario with the highest count > 1
                max_st = max(scenario_order, key=lambda s: allocated_counts[s])
                if allocated_counts[max_st] > 1:
                    allocated_counts[max_st] -= 1
                    allocated_counts[st] += 1

    return allocated_counts
