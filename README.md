# ReconcileX  
## Evidence-First AI Finance Controller for Merchant Reconciliation

> **Reconcile payments, settlements, refunds, and bank credits — safely.**  
> ReconcileX closes a bounded finance-operations control loop using deterministic financial rules, auditable evidence, human review, and advisory-only AI assistance.

---

## The Problem

Merchant finance teams often reconcile four separate sources manually:

1. Captured customer payments.
2. Payment-provider settlement records.
3. Actual merchant bank credits.
4. Refunds that change the expected settlement amount.

A record may appear to match by reference but still be financially wrong because of refunds, incorrect fees, GST, duplicate events, timing delays, missing bank references, or conflicting statuses.

A safe finance system should **not guess**.

ReconcileX answers one question:

> **Can this payment, settlement, and bank credit be safely reconciled? If not, what exact evidence-backed exception needs human review?**

---

## Closed Finance-Ops Loop

```text
Captured payment
        ↓
Provider settlement
        ↓
Merchant bank credit
        ↓
Deterministic financial validation
        ↓
┌──────────────────────────────────────────────────────────────┐
│ High-evidence chain                                           │
│ → AUTO_MATCH with financial calculation and source evidence   │
└──────────────────────────────────────────────────────────────┘
        OR
┌──────────────────────────────────────────────────────────────┐
│ Missing, invalid, delayed, ambiguous, or inconsistent data    │
│ → Prioritized exception case                                  │
│ → AI advisory explanation / narration extraction              │
│ → Human review with reason                                    │
│ → Immutable audit history                                     │
└──────────────────────────────────────────────────────────────┘
        ↓
Batch-level accuracy, throughput, and exception reporting
```

A finance-operations loop is considered closed when every eligible synthetic record is either:

- Reconciled as an `AUTO_MATCH` with complete evidence, or
- Converted into a structured exception with a category, priority, evidence, human workflow state, and immutable audit events.

> ReconcileX does **not** move money or operate a real bank ledger. It closes the reconciliation and financial-controls workflow for synthetic merchant-finance data.

---

## Why ReconcileX

Most demo projects show one perfect match. ReconcileX is built to prove what happens when financial data is messy.

| Typical reconciliation demo | ReconcileX |
|---|---|
| Matches clean CSV rows | Handles invalid, duplicate, delayed, missing, conflicting, and ambiguous records |
| Uses an LLM to decide matches | Uses deterministic evidence for financial truth |
| Shows unmatched records | Creates actionable exception cases with evidence and priority |
| Reports one vague accuracy number | Reports precision, recall, F1, false auto-matches, exception rates, and throughput |
| Uses logs | Uses PostgreSQL-enforced append-only audit history |
| Optimizes automation rate | Refuses unsafe matches and routes them to a human |

---

## Key Capabilities

### Deterministic reconciliation

ReconcileX verifies a strict one-to-one chain:

```text
Payment → Settlement → Bank Credit
```

Optional refunds are linked to the payment and deducted before validating the settlement amount.

An `AUTO_MATCH` occurs only when all conditions are true:

- Payment status is `captured`.
- Settlement contains the trusted payment ID.
- Bank narration/reference contains the settlement ID.
- Payment, settlement, and bank credit form exactly one eligible chain.
- Settlement occurs within 0–7 calendar days after payment capture.
- Refund-aware financial equation is valid within ₹0.01.
- No linked source row is invalid or duplicate.

Otherwise, ReconcileX creates an exception. It does not guess.

### Financial validation

```text
expected_net =
    captured_amount
    - processed_refunds_before_settlement
    - settlement_fee_amount
    - settlement_gst_on_fee
```

A financial match is valid only when:

```text
expected_net = settlement_net_amount = bank_credit_amount
```

within a tolerance of **₹0.01**.

All money calculations use Python `Decimal`; floating-point arithmetic is not used for financial matching.

### Exception workflow

| Exception category | Example | Priority |
|---|---|---:|
| `INVALID_ROW` | Invalid amount, malformed date, missing required field | CRITICAL |
| `DUPLICATE_EVENT` | Gateway event submitted twice | LOW |
| `MISSING_PAYMENT_ID` | Settlement has no payment linkage | MEDIUM |
| `UNMATCHED` | Referenced payment or settlement does not exist | MEDIUM |
| `STATUS_CONFLICT` | Failed payment has settlement evidence | HIGH |
| `MISSING_REFERENCE` | Bank narration cannot link to settlement | MEDIUM |
| `AMBIGUOUS_CANDIDATES` | Multiple plausible candidate records | HIGH |
| `SETTLEMENT_DELAY` | Settlement arrives after policy window | MEDIUM |
| `AMOUNT_VARIANCE` | Net amount differs from settlement or bank credit | HIGH |

Deterministic precedence prevents invalid data from being treated as a financial result:

```text
INVALID_ROW
→ MISSING_PAYMENT_ID
→ UNMATCHED
→ STATUS_CONFLICT
→ MISSING_REFERENCE
→ AMBIGUOUS_CANDIDATES
→ SETTLEMENT_DELAY
→ AMOUNT_VARIANCE
→ AUTO_MATCH
```

### Human control

Exception lifecycle is deliberately human-controlled:

```text
OPEN → IN_REVIEW → RESOLVED / DISMISSED
```

- A named actor and reason are required for resolution or dismissal.
- Reopening returns the case to `IN_REVIEW`.
- AI cannot resolve, dismiss, assign, reopen, or reprioritize an exception.
- Every human action produces an immutable audit event.

---

## Advisory AI, Not AI Matching

ReconcileX uses an LLM as an **analyst copilot**, never as a financial decision maker.

```text
Deterministic system = money truth, matching, exceptions, state
LLM = explanation, text-reference extraction, advisory context
Human = approval of uncertain financial decisions
```

### 1. Grounded exception explainer

For an existing exception, the backend retrieves trusted evidence from PostgreSQL:

- Payment, settlement, refund, and bank-credit IDs.
- Precomputed deterministic financial calculations.
- Statuses, dates, exception reason, policy/rule version.
- Relevant audit context.

The LLM returns a structured advisory explanation:

```text
What happened
→ Which trusted evidence supports it
→ Calculation summary
→ Unknowns or missing evidence
→ Suggested investigation step
```

If the LLM is unavailable, malformed, cites unknown IDs, changes monetary values, or emits unsafe instructions, ReconcileX returns a deterministic fallback explanation.

### 2. Bank-narration reference extractor

Bank narrations are often inconsistent:

```text
NEFT RAZORPAY SETTLMNT SET-5001 UTR 9812
```

The LLM may extract:

```json
{
  "settlement_id_candidate": "SET-5001",
  "utr_candidate": "9812",
  "confidence": 0.96
}
```

This is **not proof of a match**.

The server then deterministically verifies and ranks candidates within the same batch using:

- Exact settlement-ID candidate equality.
- Literal settlement-ID appearance in bank narration.
- Bank amount versus settlement net amount.
- Settlement/payment date relationship.
- Candidate uniqueness and ambiguity.

Amount-only similarity never adds unrelated settlements. Equal top-ranked candidates remain ambiguous.

Every extractor response explicitly states:

```json
{
  "advisory_only": true,
  "financial_match_decision": "NOT_MADE"
}
```

---

## AI Safety Guarantees

The LLM cannot:

- Create or change an `AUTO_MATCH`.
- Calculate, overwrite, approve, or change financial amounts.
- Change fees, GST, refunds, tolerance, or financial policy.
- Resolve, dismiss, reopen, assign, or reprioritize an exception.
- Modify payments, settlements, bank credits, refunds, reconciliation results, or source records.
- Override deterministic rule precedence.
- Trigger payout, refund, bank, accounting, or external-provider actions.

Every AI request creates an append-only audit event. Financial state remains unchanged.

---

## Architecture

```text
┌─────────────────────────────────────────────────────┐
│ React Operator Dashboard                             │
│ Upload -  Results -  Exceptions -  Audit -  Metrics      │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ FastAPI API                                          │
│ Batch -  Exceptions -  AI Advisory -  Metrics           │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ Deterministic Reconciliation Engine                  │
│ Decimal math -  Rule precedence -  Matching -  Evidence │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ Advisory AI Boundary                                 │
│ Grounded explanation -  Narration extraction          │
│ Schema validation -  Deterministic fallback           │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ PostgreSQL                                           │
│ Raw records -  Normalized data -  Results -  Exceptions │
│ Append-only audit events                             │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Financial arithmetic | Python `decimal.Decimal` |
| Database | PostgreSQL, psycopg v3 |
| Audit protection | PostgreSQL triggers blocking audit `UPDATE` and `DELETE` |
| Frontend | React 18, Vite, TypeScript |
| AI | Configurable Gemini-compatible LLM adapter, structured JSON output |
| Testing | Pytest, Vitest |
| Data | Fully synthetic CSV datasets and truth ledgers |

---

## Evaluation Results

### Deterministic reconciliation benchmark

The improved V1.1 matcher was evaluated on a seeded **held-out synthetic truth ledger** containing 500 reconciliation scenarios.

| Metric | Result |
|---|---:|
| Total scenarios evaluated | 500 |
| Exact outcome agreement | 500 / 500 |
| Auto-match precision | 100.0% |
| Auto-match recall | 100.0% |
| Auto-match F1 | 100.0% |
| Incorrect auto-matches | 0 |
| Auto-matches emitted | 315 |
| Exceptions emitted | 185 |
| Total exception rate | 37.0% |

Exception rates are calculated against all 500 scenarios:

| Exception category | Count | Rate |
|---|---:|---:|
| `AMOUNT_VARIANCE` | 40 | 8.0% |
| `SETTLEMENT_DELAY` | 40 | 8.0% |
| `MISSING_REFERENCE` | 35 | 7.0% |
| `MISSING_PAYMENT_ID` | 25 | 5.0% |
| `STATUS_CONFLICT` | 25 | 5.0% |
| `INVALID_ROW` | 20 | 4.0% |

### AI exception-explanation evaluation

A 20-case synthetic evaluation suite tests valid grounded outputs and adversarial model failures.

| Metric | Result |
|---|---:|
| Grounded clean pass rate | 100.0% |
| Adversarial defense catch rate | 100.0% |
| Unsupported-claim escape rate | 0.0% on fixture cases |
| Validator fallback trigger rate | 50.0% |

### AI narration extraction evaluation

A separate 30-case synthetic narration corpus evaluates advisory extraction and deterministic candidate ranking.

| Metric | Result |
|---|---:|
| Settlement-ID precision / recall / F1 | 100.0% / 100.0% / 100.0% |
| UTR precision / recall / F1 | 100.0% / 100.0% / 100.0% |
| False extraction count | 0 |
| Candidate-ranking Precision@1 | 100.0% |
| Candidate-ranking Recall@3 | 100.0% |
| Fallback rate | 10.0% |
| Unsafe-output blocked rate | 100.0% on injected unsafe directives |

### Honest evaluation limits

These are **synthetic, seeded, held-out regression benchmarks** created for ReconcileX V1 policy validation.

They demonstrate that the implementation behaves correctly on the documented benchmark and adversarial fixtures. They do **not** prove:

- 100% accuracy on real merchant/payment-provider data.
- Generalization to arbitrary real bank narration formats.
- That hallucinations are impossible.
- Production readiness, financial compliance, or regulatory suitability.

The 30-case narration benchmark is suitable for regression/demo evidence, not a statistically reliable production-quality accuracy estimate.

---

## Test Verification

Verified locally with PostgreSQL runtime and test databases configured:

```text
pytest -q
114 passed
```

Additional verification includes:

```text
Held-out deterministic benchmark: 500 / 500 agreement, 0 false auto-matches
AI explanation evaluation: 20 synthetic test cases
Narration extraction evaluation: 30 synthetic test cases
Frontend tests: Vitest passing
Frontend production build: passing
Health endpoint: API and PostgreSQL connected
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 15+ running locally
- Node.js 18+ and npm
- Optional: Gemini-compatible API key for live advisory demonstrations using synthetic data only

### 1. Create local databases

```powershell
psql -U postgres -c "CREATE DATABASE reconcilex;"
psql -U postgres -c "CREATE DATABASE reconcilex_test;"
```

### 2. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` with your local PostgreSQL password:

```env
DATABASE_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/reconcilex
DATABASE_URL_TEST=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/reconcilex_test
```

Optional LLM configuration:

```env
LLM_PROVIDER=google
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
LLM_MODEL=YOUR_SUPPORTED_MODEL_NAME
```

> Do not commit `.env`. Without an API key, AI endpoints safely use deterministic fallback behavior.

### 3. Initialize schemas

```powershell
python -m backend.app.db.migrations
python -m backend.app.db.migrations --test-db
```

### 4. Run all backend tests

```powershell
pytest -q
```

### 5. Run evaluations

```powershell
# Deterministic held-out reconciliation benchmark
python -m backend.app.benchmark.runner --split heldout

# Grounded exception-explanation safety evaluation
python -m backend.app.benchmark.ai_eval.eval_runner

# Advisory narration extraction/ranking evaluation
python -m backend.app.benchmark.ai_eval.narration_eval_runner
```

### 6. Start the API

```powershell
uvicorn backend.app.api.app:app --reload --host 127.0.0.1 --port 8000
```

Check service health:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

API docs:

```text
http://127.0.0.1:8000/docs
```

### 7. Start the dashboard

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL shown by Vite, commonly:

```text
http://localhost:5173
```

---

## API Surface

| Endpoint | Purpose |
|---|---|
| `POST /batches` | Upload synthetic payment, settlement, bank-credit, and refund CSVs |
| `GET /batches` | List reconciliation batches |
| `GET /batches/{batch_id}` | View batch status and summary |
| `GET /batches/{batch_id}/results` | View reconciliation outcomes |
| `GET /batches/{batch_id}/exceptions` | View prioritized exception queue |
| `GET /exceptions/{exception_id}` | View evidence for an exception |
| `PATCH /exceptions/{exception_id}` | Human-only review, resolve, dismiss, or reopen action |
| `GET /audit-events` | View append-only audit timeline |
| `POST /exceptions/{exception_id}/ai-explanation` | Generate a grounded AI advisory explanation |
| `POST /exceptions/{exception_id}/ai-narration-candidates` | Extract narration references and deterministically rank candidates |
| `GET /metrics/evaluation-report` | View deterministic and AI evaluation metrics |
| `GET /health` | Verify API and database connectivity |

---

## Demo Flow

For a 2–3 minute demo:

1. Upload a synthetic four-file batch.
2. Show auto-match count, exception count, and batch status.
3. Open an `AMOUNT_VARIANCE` exception.
4. Show payment, settlement, bank-credit, refund, and expected-net evidence.
5. Generate a grounded AI explanation.
6. Show the advisory-only safety label and deterministic fallback behavior if applicable.
7. Extract a reference from messy bank narration.
8. Show deterministic candidate ranking or ambiguity refusal.
9. Perform a human exception review with an actor and reason.
10. Open the audit timeline and show immutable history.
11. Open `/metrics` and show throughput, precision/recall/F1, zero incorrect auto-matches, and exception breakdown.

---

## Project Structure

```text
ReconcileX/
├── backend/
│   └── app/
│       ├── ai/                  # Advisory LLM adapters, validators, fallbacks
│       ├── api/                 # FastAPI routes, schemas, dependencies
│       ├── benchmark/           # Generator, metrics, AI evaluation suites
│       ├── db/                  # PostgreSQL schema, migrations, repositories
│       ├── services/            # Batch, exception, AI, and metrics services
│       ├── baseline.py          # V1.0 comparison matcher
│       ├── improved_matcher.py  # V1.1 deterministic financial matcher
│       ├── loader.py            # CSV validation, normalization, quarantine
│       └── tests/               # Unit, integration, safety, and workflow tests
├── data/
│   ├── input/                   # Synthetic example CSV inputs
│   ├── evaluation/              # Synthetic truth ledger
│   └── benchmark/               # Dev, held-out, and chaos datasets
├── docs/                        # Policy, rules, benchmark, and DB documentation
├── frontend/
│   └── src/                     # React operator dashboard
├── .env.example
├── pytest.ini
└── README.md
```

---

## Future Work

- Independently authored blind test cases and reviewer-labelled datasets.
- Larger and more diverse bank-narration evaluation corpus.
- Grouped, split, and partial settlement support.
- Multi-provider ingestion adapters.
- Authentication, RBAC, tenancy, and production-grade controls.
- Real operational studies of analyst resolution time.
- Production observability, privacy review, retention, and compliance work.

---

## Honest Project Claim

> ReconcileX is a deterministic, auditable reconciliation-operations prototype for synthetic merchant-finance data. It reconciles payment, settlement, bank-credit, and refund records; refuses uncertain cases rather than guessing; provides human review with PostgreSQL-enforced immutable audit history; and reports held-out synthetic accuracy, throughput, and exception metrics. Its LLM features are bounded advisory tools, never autonomous financial decision makers.
