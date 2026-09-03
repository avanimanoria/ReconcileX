ReconcileX
Evidence-first reconciliation operations for merchant finance.

ReconcileX reconciles captured payments, provider settlements, bank credits, and optional refunds from synthetic CSV batches. It auto-matches only when deterministic financial evidence is complete; otherwise it creates an auditable exception for a human operator.

Core principle: deterministic code decides financial truth. AI is advisory-only: it explains verified evidence and extracts candidate references from messy bank narration. It cannot auto-match records, alter money values, change exception state, or perform financial actions.

Why ReconcileX
Finance-operations teams often reconcile payment-provider records against settlement files and bank credits manually. A safe system must do more than find a happy-path match:

Verify payment → settlement → bank-credit linkage.

Validate net settlement amounts after refunds, fees, and GST.

Refuse ambiguity rather than guess.

Preserve evidence, calculation, rule version, and human outcome.

Measure accuracy, throughput, and unresolved exceptions across a batch.

ReconcileX implements that loop using synthetic data and a documented V1 policy.

What it does
text
CSV batch: payments + settlements + bank credits + refunds
        ↓
Validation, normalization, quarantine, and idempotent ingestion
        ↓
Deterministic reconciliation and financial validation
        ↓
AUTO_MATCH only for complete high-evidence chains
        ↓
Prioritized exception queue for all uncertainty or invalid data
        ↓
Human review and immutable audit history
        ↓
Optional grounded AI assistance for explanation and narration extraction
In scope
One synthetic merchant and one currency: INR.

CSV ingestion for payments, settlements, bank credits, and refunds.

Strict 1:1 payment → settlement → bank-credit reconciliation in V1.

Refund-aware expected-net validation.

Synthetic fee model: 2% processing fee and 18% GST on the fee, or source-supplied settlement fee/GST evidence where present.

₹0.01 tolerance for money comparisons.

Settlement timing window of 0–7 calendar days after capture.

Row-level invalid-data quarantine.

Duplicate-event and duplicate-batch protection.

PostgreSQL persistence, human exception workflow, and append-only audit history.

Synthetic held-out benchmark and adversarial regression tests.

Advisory-only LLM explanation and narration-reference extraction.

Explicitly out of scope
Real bank, Razorpay, Stripe, UPI, or payment-gateway connectivity.

Real customer/merchant financial data.

Money movement, refunds, payouts, journal posting, or accounting ERP integration.

Multi-currency and FX conversion.

OCR/PDF statement ingestion.

Grouped or split settlements in V1.

Autonomous LLM matching or autonomous financial decisions.

Production authentication, multi-tenancy, compliance certification, or production deployment controls.

Deterministic financial policy
For a captured payment, the V1 expected net is:

text
expected_net = captured_amount
             - processed_refunds_before_settlement
             - settlement_fee_amount
             - settlement_gst_on_fee
A match is financially valid only when, within ₹0.01:

text
expected_net = settlement_net_amount = bank_credit_amount
An AUTO_MATCH requires all of the following:

Payment status is captured.

The settlement links to the payment ID.

The bank narration/reference links to the settlement ID.

The net-amount equation is valid within ₹0.01.

Settlement date is 0–7 calendar days after capture.

Exactly one eligible payment, settlement, and bank credit are linked.

Linked source rows are not invalid or duplicate.

Otherwise, the system creates an exception. It does not guess.

Exception handling
Category	Meaning	Default priority
INVALID_ROW	Required field, money value, or date is invalid	CRITICAL
DUPLICATE_EVENT	Source event was previously ingested	LOW
MISSING_PAYMENT_ID	Settlement lacks payment linkage	MEDIUM
UNMATCHED	Referenced source record is absent	MEDIUM
STATUS_CONFLICT	Non-captured payment has settlement evidence	HIGH
MISSING_REFERENCE	Bank narration does not link to settlement	MEDIUM
AMBIGUOUS_CANDIDATES	More than one eligible candidate exists	HIGH
SETTLEMENT_DELAY	Settlement is beyond the 7-day policy window	MEDIUM
AMOUNT_VARIANCE	Expected net, settlement net, and bank amount do not agree	HIGH
The deterministic precedence order is explicit so invalid data cannot accidentally become a financial decision:

text
INVALID_ROW
→ MISSING_PAYMENT_ID
→ UNMATCHED
→ STATUS_CONFLICT
→ MISSING_REFERENCE
→ AMBIGUOUS_CANDIDATES
→ SETTLEMENT_DELAY
→ AMOUNT_VARIANCE
→ AUTO_MATCH
AI safety boundary
ReconcileX uses an LLM as a read-only analyst copilot, not a financial decision maker.

1. Grounded exception explainer
For an existing exception, the server retrieves only trusted persisted evidence—source IDs, deterministic calculations, statuses, dates, rule version, and exception details. The LLM can produce a structured explanation, evidence summary, unknowns, and suggested investigation step.

The response is schema-validated. It falls back to a deterministic explanation if the model is unconfigured, times out, produces malformed JSON, cites unknown evidence, changes monetary values, or emits unsafe instructions.

2. Advisory bank-narration extractor
For messy bank narration such as:

text
NEFT RAZORPAY SETTLMNT SET-5001 UTR 9812
The LLM may extract a candidate settlement reference and UTR. The server then performs all validation and candidate ranking deterministically, scoped to the same batch.

A settlement enters the candidate set only when:

its settlement ID exactly equals the extracted candidate, or

its complete settlement ID appears literally in the stored bank narration.

Amount-only similarity never introduces unrelated candidates. Equal top-ranked candidates remain ambiguous and require human review.

Non-negotiable AI controls
The LLM cannot:

Create or change an AUTO_MATCH.

Calculate, overwrite, or approve money amounts, fees, GST, refunds, or tolerances.

Resolve, dismiss, reopen, assign, or reprioritize an exception.

Modify payments, settlements, bank credits, refunds, reconciliation results, or source evidence.

Override deterministic policies or rule precedence.

Trigger money movement or external-provider actions.

Both AI endpoints return advisory output only. The narration endpoint explicitly returns:

json
{"financial_match_decision": "NOT_MADE"}
Architecture
text
React operator dashboard
        ↓
FastAPI API
        ↓
Service layer
        ↓
Deterministic reconciliation engine + advisory AI adapters
        ↓
PostgreSQL: raw records, normalized records, results, exceptions, audit events
Core components
Deterministic engine: Python Decimal calculations, matching policy, exception precedence, and high-evidence decisions.

Ingestion: CSV validation, canonical normalization, source-row retention, quarantine, and idempotency.

Persistence: PostgreSQL tables for batches, raw source records, payments, settlements, bank credits, refunds, reconciliation results, exceptions, and audit events.

Auditability: PostgreSQL triggers block UPDATE and DELETE on audit_events.

API: FastAPI endpoints for upload, batches, results, exception lifecycle, audit history, AI advisory endpoints, and metrics.

Dashboard: React/Vite/TypeScript UI for upload, batch monitoring, evidence drill-down, exception review, audit timeline, and evaluation metrics.

Key API endpoints
Endpoint	Purpose
POST /batches	Upload a four-file synthetic CSV batch
GET /batches	List persisted batches
GET /batches/{batch_id}	Retrieve batch status and summary
GET /batches/{batch_id}/results	Retrieve reconciliation results
GET /batches/{batch_id}/exceptions	Retrieve the exception queue
GET /exceptions/{exception_id}	Retrieve exception evidence
PATCH /exceptions/{exception_id}	Human-only exception lifecycle action with actor/reason
GET /audit-events	Query immutable audit history
POST /exceptions/{exception_id}/ai-explanation	Generate a grounded advisory explanation
POST /exceptions/{exception_id}/ai-narration-candidates	Extract advisory narration references and deterministically rank candidates
GET /metrics/evaluation-report	Return reproducible deterministic and AI advisory evaluation metrics
GET /health	Health and database connectivity check
Evaluation results
Deterministic reconciliation
The improved matcher was evaluated against a seeded, held-out synthetic truth ledger containing 500 scenarios under the documented ReconcileX V1 policy.

Metric	Result
Scenarios evaluated	500
Exact outcome agreement	500 / 500
Auto-match precision	100.0%
Auto-match recall	100.0%
Auto-match F1	100.0%
Incorrect auto-matches	0
Auto-matches emitted	315
Exceptions emitted	185
Total exception rate	37.0%
Exception rates are measured against total scenarios:

Exception category	Count	Rate
AMOUNT_VARIANCE	40	8.0%
SETTLEMENT_DELAY	40	8.0%
MISSING_REFERENCE	35	7.0%
MISSING_PAYMENT_ID	25	5.0%
STATUS_CONFLICT	25	5.0%
INVALID_ROW	20	4.0%
Interpretation: this is strong regression evidence that the matcher follows the synthetic V1 policy. It is not evidence of production performance on third-party merchant data.

AI exception-explanation evaluation
A 20-case synthetic evaluation suite tests valid grounded outputs and adversarial failures.

Metric	Result
Grounded clean pass rate	100.0%
Adversarial defense catch rate	100.0%
Unsupported-claim escape rate	0.0% on the fixture set
Validator fallback trigger rate	50.0%
This does not prove hallucinations are impossible. It shows that, on the injected test failures, the validation boundary and deterministic fallback behaved as designed.

Advisory narration extraction evaluation
A separate 30-case synthetic narration corpus measures extraction and deterministic candidate ranking.

Metric	Result
Settlement-ID precision / recall / F1	100.0% / 100.0% / 100.0%
UTR precision / recall / F1	100.0% / 100.0% / 100.0%
False extraction count	0
Candidate ranking Precision@1	100.0%
Candidate ranking Recall@3	100.0%
Fallback rate	10.0%
Unsafe-output blocked rate	100.0% on injected unsafe directives
Important limitation: the 30-case narration corpus is a small synthetic regression/demo benchmark. It is not a statistically reliable production accuracy estimate, and narration metrics are not financial reconciliation accuracy.

Human-workflow metrics
Metric	Status
Simulated mean time to resolution	Not measured / unavailable
Auto-resolution rate	Not applicable — human approval is required
Quick start
Prerequisites
Python 3.12+.

PostgreSQL 15+ running locally.

Node.js 18+ and npm.

Optional: a Gemini-compatible API key for live advisory demonstrations using synthetic data only.

1. Configure local databases
Create two local PostgreSQL databases:

powershell
psql -U postgres -c "CREATE DATABASE reconcilex;"
psql -U postgres -c "CREATE DATABASE reconcilex_test;"
Copy the environment template:

powershell
Copy-Item .env.example .env
Edit .env with your local password. Do not commit this file:

text
DATABASE_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/reconcilex
DATABASE_URL_TEST=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/reconcilex_test
Optional live LLM configuration:

text
LLM_PROVIDER=google
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
LLM_MODEL=YOUR_SUPPORTED_MODEL_NAME
Without an LLM key, AI features remain testable through deterministic fallback behavior.

2. Initialize schemas
powershell
python -m backend.app.db.migrations
python -m backend.app.db.migrations --test-db
3. Run the test suite
powershell
pytest -q
The verified repository state includes 114 passing tests when both local databases are configured and reachable.

4. Run benchmarks
powershell
# Held-out deterministic matcher evaluation
python -m backend.app.benchmark.runner --split heldout

# AI grounded-explanation safety evaluation
python -m backend.app.benchmark.ai_eval.eval_runner

# Advisory narration extraction/ranking evaluation
python -m backend.app.benchmark.ai_eval.narration_eval_runner
5. Start the backend
powershell
uvicorn backend.app.api.app:app --reload --host 127.0.0.1 --port 8000
Check health:

powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
Open API documentation is available at:

text
http://127.0.0.1:8000/docs
6. Start the dashboard
In a second terminal:

powershell
cd frontend
npm install
npm run dev
Open the local URL printed by Vite, typically:

text
http://localhost:5173
The dashboard includes batch upload, batch results, exception evidence/review, audit timeline, AI advisory panels, and the /metrics evaluation view.

Useful verification commands
powershell
# Full backend test suite
pytest -q

# Frontend tests
cd frontend
npm run test
npm run build
cd ..

# Held-out deterministic benchmark
python -m backend.app.benchmark.runner --split heldout

# API metrics report
Invoke-RestMethod -Uri "http://127.0.0.1:8000/metrics/evaluation-report" |
  ConvertTo-Json -Depth 10

# Check working tree before a commit
git diff --check
git status
Repository structure
text
ReconcileX/
├── backend/
│   └── app/
│       ├── ai/                      # Advisory LLM adapters, validators, fallback, extraction
│       ├── api/                     # FastAPI routes, schemas, dependencies
│       ├── benchmark/               # Generator, held-out metrics, AI evaluation suites
│       ├── db/                      # PostgreSQL schema, migrations, repositories
│       ├── services/                # Batch, exception, and metrics services
│       ├── baseline.py              # V1.0 comparison matcher
│       ├── improved_matcher.py      # V1.1 deterministic financial matcher
│       ├── loader.py                # CSV validation, normalization, quarantine
│       └── tests/                   # Unit, integration, safety, and workflow tests
├── data/
│   ├── input/                       # Synthetic example CSVs
│   ├── evaluation/                  # Synthetic truth ledger
│   └── benchmark/                   # Dev, held-out, and chaos synthetic benchmarks
├── docs/                            # Decision policy, rules, methodology, database architecture
├── frontend/
│   └── src/                         # React operator dashboard
├── .env.example
├── pytest.ini
└── README.md
Demo flow
A concise demonstration should show:

Upload a synthetic four-file batch.

Show auto-match and exception counts.

Open an AMOUNT_VARIANCE exception and inspect payment, settlement, bank, refund, and calculation evidence.

Generate an AI explanation; show that it is advisory-only.

Extract a narration reference; show deterministic candidate ranking or ambiguity refusal.

Perform a human review action with actor and reason.

Open the audit timeline and show immutable event history.

Open /metrics and distinguish deterministic reconciliation metrics from AI advisory metrics.

Limitations and future work
ReconcileX is a well-scoped prototype, not production fintech infrastructure. Future validation and development should include:

Independently authored blind test cases and reviewer-labelled data.

More diverse narration formats and larger evaluation corpora.

Grouped/split settlement models.

Source-specific integration adapters and secure authentication.

Production observability, access controls, privacy review, retention policy, and compliance work.

Human-in-the-loop usability studies measuring actual resolution time.

Honest project claim
ReconcileX is a deterministic, auditable reconciliation-operations prototype for synthetic merchant-finance data. It reconciles payment, settlement, bank-credit, and refund records; safely refuses uncertain cases; provides a human-review workflow with database-enforced immutable audit history; and measures its results on held-out synthetic benchmarks. Its LLM features are bounded advisory tools, never autonomous financial decision makers.

