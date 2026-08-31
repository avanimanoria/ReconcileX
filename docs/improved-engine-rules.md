# ReconcileX V1.1 — Improved Deterministic Financial Validator Rules

## Overview

The ReconcileX V1.1 Improved Matcher extends the conservative baseline reconciliation engine with strict financial validation, refund awareness, and settlement timing checks.

The improved engine is **100% deterministic, rule-based, and side-effect-free**. No AI, machine learning, heuristics, or fuzzy matching are used in financial decision-making.

---

## One-to-One Reconciliation Constraint

ReconcileX V1.1 operates under a strict one-to-one financial reconciliation model:
$$\text{One Payment} \longleftrightarrow \text{One Settlement} \longleftrightarrow \text{One Bank Credit}$$

If evidence is incomplete, corrupt, delayed, conflicting, or ambiguous, the engine creates a specific exception and never guesses a financial match.

---

## Strict Rule Precedence

For each settlement record, the engine applies the following evaluation pipeline in exact order:

```mermaid
graph TD
    A[Settlement Record] --> R1{1. Linked Invalid Row?}
    R1 -- Yes --> E1[EXCEPTION: INVALID_ROW]
    R1 -- No --> R2{2. Missing Payment ID?}
    R2 -- Yes --> E2[EXCEPTION: MISSING_PAYMENT_ID]
    R2 -- No --> R3{3. Payment Not Found?}
    R3 -- Yes --> E3[EXCEPTION: UNMATCHED]
    R3 -- No --> R4{4. Payment Status != 'captured'?}
    R4 -- Yes --> E4[EXCEPTION: STATUS_CONFLICT]
    R4 -- No --> R5{5. Bank Narration Lacks Settlement ID?}
    R5 -- Yes --> E5[EXCEPTION: MISSING_REFERENCE]
    R5 -- No --> R6{6. Multiple Bank Matches?}
    R6 -- Yes --> E6[EXCEPTION: AMBIGUOUS_CANDIDATES]
    R6 -- No --> R7{7. Settlement Delay > 7 Days?}
    R7 -- Yes --> E7[EXCEPTION: SETTLEMENT_DELAY]
    R7 -- No --> R8[8. Compute Refund-Aware Net]
    R8 --> R9{9. |Expected - Set Net| > ₹0.01?}
    R9 -- Yes --> E9[EXCEPTION: AMOUNT_VARIANCE]
    R9 -- No --> R10{10. |Expected - Bank Amt| > ₹0.01?}
    R10 -- Yes --> E10[EXCEPTION: AMOUNT_VARIANCE]
    R10 -- No --> M[AUTO_MATCH]
```

### Detailed Rule Specifications

1. **`INVALID_ROW` (Precedence 1)**
   - Triggered when any linked source row fails parsing or validation (e.g. `BANK-015` with `credit_amount=NOT_A_NUMBER`).
   - Retains parsed narration and linked IDs so that `SET-015` reports `INVALID_ROW` rather than `MISSING_REFERENCE` or `AMOUNT_VARIANCE`.

2. **`MISSING_PAYMENT_ID` (Precedence 2)**
   - Triggered when `settlement.payment_id` is empty or missing (e.g. `SET-013`).

3. **`UNMATCHED` (Precedence 3)**
   - Triggered when `settlement.payment_id` is specified but does not exist in the payment dataset.

4. **`STATUS_CONFLICT` (Precedence 4)**
   - Triggered when the linked payment exists but has a non-captured status (e.g. `PAY-014` with status `failed`).
   - Prevents reconciliation of failed/pending payments even if settlement and bank amounts match.

5. **`MISSING_REFERENCE` (Precedence 5)**
   - Search valid bank credit narrations for exact `settlement_id`.
   - If no valid bank narration contains `settlement_id`, return `MISSING_REFERENCE` (e.g. `SET-006`, `SET-008`).
   - No fuzzy matching or amount-based guessing is permitted.

6. **`AMBIGUOUS_CANDIDATES` (Precedence 6)**
   - Triggered if more than one valid bank credit contains the `settlement_id`.

7. **`SETTLEMENT_DELAY` (Precedence 7)**
   - Policy: Settlement must occur within **0 to 7 calendar days** of payment capture.
   - Equation:
     $$\text{delay\_days} = \text{settled\_at.date}() - \text{captured\_at.date}()$$
   - Exactly 7 days is allowed ($\text{delay\_days} \le 7$).
   - Greater than 7 days ($\text{delay\_days} > 7$) triggers `EXCEPTION: SETTLEMENT_DELAY` (e.g. `SET-005` with 9 days delay).

8. **Refund-Aware Expected Net Calculation (Precedence 8)**
   - **Refund Eligibility**: A refund is included if and only if:
     1. `refund.payment_id == payment.payment_id`
     2. `refund.refund_status == "processed"`
     3. `refund.refunded_at <= settlement.settled_at`
   - **Equations**:
     $$\text{eligible\_amount} = \text{captured\_amount} - \sum \text{eligible\_processed\_refunds}$$
     $$\text{expected\_net} = \text{eligible\_amount} - \text{settlement.fee\_amount} - \text{settlement.gst\_on\_fee}$$

9. **Settlement Net Validation (Precedence 9)**
   - Checks:
     $$|\text{expected\_net} - \text{settlement.net\_amount}| > \text{Decimal}("0.01")$$
   - Trigger: `EXCEPTION: AMOUNT_VARIANCE` if variance exceeds ₹0.01 tolerance.

10. **Bank Credit Amount Validation (Precedence 10)**
    - Checks:
      $$|\text{expected\_net} - \text{bank\_credit.credit\_amount}| > \text{Decimal}("0.01")$$
    - Trigger: `EXCEPTION: AMOUNT_VARIANCE` if variance exceeds ₹0.01 tolerance (e.g. `SET-007` expected ₹1952.80 vs bank ₹1900.00).

11. **`AUTO_MATCH` (Precedence 11)**
    - Returns `AUTO_MATCH` only when all 10 preceding checks pass cleanly.

---

## Why Structural & Linkage Checks Precede Financial Validation

1. **Data Integrity First**: Attempting financial math on unverified, missing, or malformed records produces misleading variance errors instead of identifying root data-quality issues.
2. **Audit Reliability**: Classifying `BANK-015` as `INVALID_ROW` rather than `AMOUNT_VARIANCE` directs the operations team to repair data pipeline corruption rather than contacting the bank for financial discrepancy.
3. **Fraud & Conflict Prevention**: Checking payment status before financial amount prevents reconciling failed charges that erroneously received settlement credits.

---

## Financial Decimal Policy

- All monetary calculations and comparisons use standard library `decimal.Decimal`.
- Floating-point numbers (`float`) are strictly forbidden across models, calculations, and tests to eliminate rounding discrepancies.
- The standard financial matching tolerance is strictly fixed at `Decimal("0.01")` (1 paisa).
