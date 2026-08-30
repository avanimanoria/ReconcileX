# ReconcileX V1 — Decision Specification

## Goal

Reconcile captured merchant payments with provider settlements and
merchant bank credits. Auto-match only when evidence is complete and
financial amounts reconcile. Create auditable exceptions for every
uncertain, conflicting, delayed, duplicate, or invalid case.

## V1 scope

### In scope
- One merchant
- One currency: INR
- CSV batch ingestion
- Payments, settlements, bank credits, and processed refunds
- One payment → one settlement → one bank credit
- Refunds that occur before settlement
- Settlement window: 0–7 calendar days after payment capture
- Deterministic matching, validation, and exception creation
- Analyst review: resolve or dismiss an exception with a required reason
- Immutable audit events
- Synthetic test data and hidden truth-ledger evaluation
- AI-generated grounded exception explanation and suggested investigation step

### Out of scope
- Live Razorpay, bank, UPI, or payment-gateway connections
- Money movement, payouts, refunds, or accounting journal posting
- Multi-currency, FX, and real GST compliance
- OCR/PDF parsing
- One-to-many, many-to-one, split, or grouped settlements
- Fully autonomous AI decisions
- AI-created financial matches or resolution
- Production compliance certification and multi-tenant access control

## Financial policy

Eligible amount = captured amount − total processed refunds

Expected net =
eligible amount − settlement fee_amount − settlement gst_on_fee

Money tolerance = ₹0.01.

A financial amount is valid only when:
expected net = settlement net_amount = bank credit_amount,
within ₹0.01 tolerance.

## Auto-match policy

The system creates an `AUTO_MATCH` only when every condition is true:

1. Payment status is `captured`.
2. Exactly one valid payment exists for the settlement payment_id.
3. Settlement contains a non-empty payment_id.
4. Exactly one valid bank credit narration contains the settlement_id.
5. Settlement date is 0–7 calendar days after payment capture.
6. The financial equation is valid within ₹0.01.
7. No linked source row is invalid.
8. The event is not a duplicate.

All other conditions result in an exception.

## Exception categories

| Category | Trigger |
|---|---|
| `INVALID_ROW` | Required field, timestamp, or monetary amount cannot be validated |
| `DUPLICATE_EVENT` | A payment_event_id has already been processed |
| `MISSING_PAYMENT_ID` | A settlement has no linked payment_id |
| `MISSING_REFERENCE` | Bank narration lacks the settlement_id |
| `AMBIGUOUS_CANDIDATES` | More than one possible record can be linked |
| `AMOUNT_VARIANCE` | Expected, settlement, or bank amount differs beyond ₹0.01 |
| `SETTLEMENT_DELAY` | Settlement occurs more than seven days after capture |
| `STATUS_CONFLICT` | A non-captured payment has a settlement or bank credit |

## Exception priority

- `CRITICAL`: Invalid source data or high-value unexplained amount variance
- `HIGH`: Status conflict or amount variance
- `MEDIUM`: Missing payment ID, missing reference, settlement delay
- `LOW`: Duplicate event

## Audit and idempotency policy

- `payment_event_id` is the payment ingestion idempotency key.
- A duplicate event does not create a second payment or reconciliation outcome.
- Retain raw source records and normalized records separately.
- Every decision records input/source IDs, matching rule version,
  calculation values, result, exception type, timestamp, and actor.
- AI suggestions are retained as audit events but cannot change financial state.

## AI policy

### AI input
Only validated and structured evidence from an existing exception:
linked record IDs, amounts, dates, calculated variance, known exception
category, and allowed context.

### AI output
- A concise evidence-grounded explanation
- A suggested next investigation step
- A structured confidence / insufficient-evidence indicator

### AI constraints
AI cannot:
- alter amounts, IDs, or source records
- create or approve an auto-match
- resolve or dismiss an exception
- write to financial-state tables
- invent missing financial evidence

If AI output fails schema or evidence validation, the system displays a
deterministic template explanation instead.

## Evaluation

### Baseline
Auto-match only if:
- `payment_id` appears in settlement, and
- `settlement_id` appears in bank narration.

### Improved engine
Baseline plus payment-status validation, duplicate detection, settlement
date validation, net-amount validation, refund handling, and exception
classification.

### Metrics
- Auto-match precision
- Auto-match recall
- Incorrect auto-match count
- Auto-resolution rate
- Exception count by category
- Amount auto-reconciled
- Batch-processing time
- AI explanation validation pass rate