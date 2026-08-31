# ReconcileX Adversarial Safety & Rule Precedence Test Matrix

## Overview

In real-world financial operations, dirty data frequently exhibits **multiple simultaneous anomalies** (e.g., corrupt bank credit amounts combined with failed payment statuses, or missing references combined with amount variances).

ReconcileX strictly enforces a deterministic, priority-ordered decision pipeline. When multiple conflicting conditions occur in a single reconciliation transaction, the engine must safely and deterministically halt at the highest-priority root cause.

---

## Rule Precedence Hierarchy

The table below defines the strict precedence order implemented in ReconcileX:

| Priority | Category | Why it wins |
|---:|---|---|
| 1 | `INVALID_ROW` | Data cannot be trusted or financially interpreted |
| 2 | `MISSING_PAYMENT_ID` | No payment linkage exists for reconciliation |
| 3 | `UNMATCHED` | Referenced payment does not exist in the payment dataset |
| 4 | `STATUS_CONFLICT` | Payment state disallows reconciliation (only `captured` is valid) |
| 5 | `MISSING_REFERENCE` | No trusted bank linkage exists in narration (never guess) |
| 6 | `AMBIGUOUS_CANDIDATES` | Multiple possible bank records; never guess or arbitrate |
| 7 | `SETTLEMENT_DELAY` | Settlement timing policy is violated (> 7 calendar days) |
| 8 | `AMOUNT_VARIANCE` | Financial equation or bank credit differs beyond ₹0.01 tolerance |
| 9 | `AUTO_MATCH` | All required structural, timing, and financial evidence passes |

---

## 12 Adversarial Combination Test Matrix

### Case 1: Invalid Bank Amount + Missing Reference
- **Test Function**: `test_case_01_invalid_bank_amount_plus_missing_reference`
- **Combined Conditions**: Bank credit amount is `"NOT_A_NUMBER"` and bank narration lacks the settlement ID.
- **Expected Result**: `EXCEPTION: INVALID_ROW`
- **Precedence Rationale**: Data corruption (`INVALID_ROW`, Priority 1) takes precedence over missing reference (`MISSING_REFERENCE`, Priority 5).
- **Safety Risk Avoided**: Prevents classifying unparseable or corrupted records as missing-linkage operational errors.

### Case 2: Invalid Bank Amount + Status Conflict
- **Test Function**: `test_case_02_invalid_bank_amount_plus_status_conflict`
- **Combined Conditions**: Payment has status `failed`, but bank credit amount is `"NOT_A_NUMBER"`.
- **Expected Result**: `EXCEPTION: INVALID_ROW`
- **Precedence Rationale**: Source data validation (`INVALID_ROW`, Priority 1) precedes transaction state validation (`STATUS_CONFLICT`, Priority 4).
- **Safety Risk Avoided**: Prevents executing state transitions or fraud logic on corrupted input rows.

### Case 3: Missing Payment ID + Amount Mismatch
- **Test Function**: `test_case_03_missing_payment_id_plus_amount_mismatch`
- **Combined Conditions**: Settlement record has a blank `payment_id`, and settlement net amount differs from bank credit.
- **Expected Result**: `EXCEPTION: MISSING_PAYMENT_ID`
- **Precedence Rationale**: Structural identifier linkage (`MISSING_PAYMENT_ID`, Priority 2) precedes financial net validation (`AMOUNT_VARIANCE`, Priority 8).
- **Safety Risk Avoided**: Prevents meaningless variance computations when the fundamental transaction identifier is missing.

### Case 4: Missing Payment ID + Settlement Delay
- **Test Function**: `test_case_04_missing_payment_id_plus_settlement_delay`
- **Combined Conditions**: Settlement record has a blank `payment_id` and settlement date is 10 days after payment capture.
- **Expected Result**: `EXCEPTION: MISSING_PAYMENT_ID`
- **Precedence Rationale**: Linkage requirement (`MISSING_PAYMENT_ID`, Priority 2) precedes timing evaluation (`SETTLEMENT_DELAY`, Priority 7).
- **Safety Risk Avoided**: Prevents evaluating SLA delay penalties on unlinked settlement records.

### Case 5: Status Conflict + Amount Variance
- **Test Function**: `test_case_05_status_conflict_plus_amount_variance`
- **Combined Conditions**: Payment has status `failed`, but linked settlement and bank amounts also have a ₹50 variance.
- **Expected Result**: `EXCEPTION: STATUS_CONFLICT`
- **Precedence Rationale**: Payment lifecycle validation (`STATUS_CONFLICT`, Priority 4) precedes financial equation validation (`AMOUNT_VARIANCE`, Priority 8).
- **Safety Risk Avoided**: Prevents financial reconciliation workflows on failed payments that erroneously received provider settlements.

### Case 6: Status Conflict + Settlement Delay
- **Test Function**: `test_case_06_status_conflict_plus_settlement_delay`
- **Combined Conditions**: Payment has status `failed`, and settlement occurs 9 days after payment capture.
- **Expected Result**: `EXCEPTION: STATUS_CONFLICT`
- **Precedence Rationale**: Payment lifecycle validation (`STATUS_CONFLICT`, Priority 4) precedes SLA timing checks (`SETTLEMENT_DELAY`, Priority 7).
- **Safety Risk Avoided**: Ensures failed payment disputes take priority over timing delays.

### Case 7: Missing Reference + Amount Variance
- **Test Function**: `test_case_07_missing_reference_plus_amount_variance`
- **Combined Conditions**: Bank credit narration does not mention the settlement ID, and bank amount differs from expected net.
- **Expected Result**: `EXCEPTION: MISSING_REFERENCE`
- **Precedence Rationale**: Reference integrity (`MISSING_REFERENCE`, Priority 5) precedes financial equation validation (`AMOUNT_VARIANCE`, Priority 8).
- **Safety Risk Avoided**: Prevents amount comparisons against arbitrary, unlinked bank credits.

### Case 8: Settlement Delay + Amount Variance
- **Test Function**: `test_case_08_settlement_delay_plus_amount_variance`
- **Combined Conditions**: Settlement occurs 8 days after payment capture (> 7 days), and bank credit has a variance.
- **Expected Result**: `EXCEPTION: SETTLEMENT_DELAY`
- **Precedence Rationale**: SLA timing policy (`SETTLEMENT_DELAY`, Priority 7) precedes financial amount variance (`AMOUNT_VARIANCE`, Priority 8).
- **Safety Risk Avoided**: Flags provider settlement SLA breach as the primary exception category.

### Case 9: Ambiguous Bank Candidates + Amount Variance
- **Test Function**: `test_case_09_ambiguous_bank_candidates_plus_amount_variance`
- **Combined Conditions**: Multiple bank credits contain the same settlement ID, and one of them has an amount variance.
- **Expected Result**: `EXCEPTION: AMBIGUOUS_CANDIDATES`
- **Precedence Rationale**: Candidate uniqueness (`AMBIGUOUS_CANDIDATES`, Priority 6) precedes financial amount checks (`AMOUNT_VARIANCE`, Priority 8).
- **Safety Risk Avoided**: Prevents guessing or arbitrarily picking among multiple ambiguous candidate records.

### Case 10: Duplicate Payment Event + Invalid Bank Amount
- **Test Function**: `test_case_10_duplicate_payment_event_plus_invalid_bank_amount`
- **Combined Conditions**: Ingestion receives duplicate `payment_event_id` rows, while bank credit amount is `"NOT_A_NUMBER"`.
- **Expected Result**: `EXCEPTION: INVALID_ROW` + `DUPLICATE_EVENT` Audit Entry
- **Precedence Rationale**: Duplicate payment is handled idempotently via audit log; corrupted bank row triggers `INVALID_ROW` (Priority 1).
- **Safety Risk Avoided**: Ensures idempotency audit logging occurs without preventing detection of bank-side data corruption.

### Case 11: Rounding Tolerance Boundary (Accepted)
- **Test Function**: `test_case_11_rounding_tolerance_boundary_accepted`
- **Combined Conditions**: All IDs, dates, and references match; bank credit differs from expected net by exactly `₹0.01` (`Decimal("0.01")`).
- **Expected Result**: `AUTO_MATCH`
- **Precedence Rationale**: The difference falls within the inclusive `Decimal("0.01")` tolerance limit.
- **Safety Risk Avoided**: Prevents spurious exceptions on standard sub-paisa banking rounding variations.

### Case 12: Rounding Tolerance Boundary (Rejected)
- **Test Function**: `test_case_12_rounding_tolerance_rejection`
- **Combined Conditions**: All IDs, dates, and references match; bank credit differs from expected net by `₹0.02` (`Decimal("0.02")`).
- **Expected Result**: `EXCEPTION: AMOUNT_VARIANCE`
- **Precedence Rationale**: The difference exceeds the `Decimal("0.01")` financial tolerance limit.
- **Safety Risk Avoided**: Prevents leaking financial discrepancies into automated reconciliations.
