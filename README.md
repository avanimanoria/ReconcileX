# ReconcileX — Deterministic Offline Financial Reconciliation Engine

ReconcileX is a modular, deterministic, offline Python financial reconciliation engine designed to reconcile captured merchant payments, gateway settlements, and bank credit records with strict auditability.

---

## Engine Versions: Baseline (V1.0) vs Improved (V1.1)

| Capability / Rule | Baseline Matcher (V1.0) | Improved Matcher (V1.1) |
|---|---|---|
| **Idempotency & Duplicate Events** | Handled (`DUPLICATE_EVENT` audit) | Handled (`DUPLICATE_EVENT` audit) |
| **Status Eligibility (`captured`)** | Validated (`STATUS_CONFLICT`) | Validated (`STATUS_CONFLICT`) |
| **Missing Settlement Payment ID** | Validated (`MISSING_PAYMENT_ID`) | Validated (`MISSING_PAYMENT_ID`) |
| **Exact Bank Narration Reference** | Validated (`MISSING_REFERENCE`) | Validated (`MISSING_REFERENCE`) |
| **Invalid Data Quarantine** | Validated (`INVALID_ROW`) | Validated (`INVALID_ROW`) |
| **Settlement Timing Window (<= 7 days)** | ❌ *Ignored (Known limitation)* | ✅ **Validated (`SETTLEMENT_DELAY`)** |
| **Refund-Aware Net Amount** | ❌ *Ignored (Known limitation)* | ✅ **Validated (Deducts processed refunds)** |
| **Settlement Net Validation** | ❌ *Ignored (Known limitation)* | ✅ **Validated (<= ₹0.01 tolerance)** |
| **Bank Credit Amount Validation** | ❌ *Ignored (Known limitation)* | ✅ **Validated (<= ₹0.01 tolerance)** |
| **Truth Ledger Accuracy** | **86.7%** (13/15 matched) | **100.0%** (15/15 matched) |

---

## Design & Architecture Principles

- **No AI in Financial Decisions**: The engine is 100% deterministic and rule-based. AI, ML, fuzzy matching, and heuristics are intentionally omitted by design to ensure absolute auditability and financial correctness.
- **Strict Decimal Math**: All calculations use Python's `decimal.Decimal` with a strict `₹0.01` (1 paisa) tolerance. Floating-point numbers are forbidden.
- **Strict 1-to-1 Matching**: One payment $\longleftrightarrow$ One settlement $\longleftrightarrow$ One bank credit.
- **Decoupled Evaluation**: Ground truth evaluation ledger is strictly separated from engine matching logic.
- **PostgreSQL Persistence & Append-Only Audit**: Full relational persistence using raw `psycopg` (v3) with database triggers preventing `UPDATE` and `DELETE` on `audit_events`.
- **Reproducible Synthetic Benchmark**: Byte-reproducible benchmark generation and evaluation suite to test engines against scaled distributions without label leakage.
- **Adversarial Precedence Hardening**: Explicit multi-fault test matrix proving safe refusal and deterministic precedence.
- **Offline & Self-Contained**: Core matching engine operates 100% offline with zero external dependencies.

---

## Project Structure

```text
ReconcileX/
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── models.py                # Dataclasses, Enums, and Result models
│       ├── loader.py                # CSV ingestion, validation, and invalid row quarantine
│       ├── baseline.py              # Baseline conservative matcher (rules 1–9)
│       ├── improved_matcher.py      # Improved deterministic financial validator (V1.1)
│       ├── evaluator.py             # Ground-truth comparison and metrics engine
│       ├── main.py                  # CLI entry point (baseline / improved / compare)
│       ├── benchmark/
│       │   ├── __init__.py
│       │   ├── scenarios.py         # Scenario types and deterministic allocations
│       │   ├── generator.py         # Synthetic benchmark dataset generator
│       │   ├── metrics.py           # Precision, recall, and throughput calculations
│       │   └── runner.py            # Benchmark execution and reporting CLI
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py        # psycopg connection pool & transaction helper
│       │   ├── schema.sql           # PostgreSQL DDL with triggers & constraints
│       │   ├── migrations.py        # Schema initializer CLI
│       │   └── repositories/
│       │       ├── __init__.py
│       │       ├── batch_repo.py    # Batch metadata and entity persistence
│       │       ├── recon_repo.py    # Results and exception persistence
│       │       └── audit_repo.py    # Append-only audit repository (no update/delete)
│       ├── services/
│       │   ├── __init__.py
│       │   ├── batch_service.py     # Idempotent batch ingestion & matching orchestration
│       │   └── exception_service.py # Exception lifecycle transitions & assignments
│       └── tests/
│           ├── __init__.py
│           ├── conftest.py               # Database test fixtures & skip guards
│           ├── test_loader.py            # Ingestion, parsing, and quarantine tests
│           ├── test_baseline.py          # Baseline rules and exception tests
│           ├── test_improved_matcher.py  # V1.1 financial validation & timing tests
│           ├── test_adversarial_precedence.py # 12 multi-fault combination tests
│           ├── test_benchmark_generator.py # Generator reproducibility tests
│           ├── test_benchmark_runner.py  # Runner & metrics tests
│           ├── test_db_schema.py         # PostgreSQL schema & constraint tests
│           ├── test_batch_service.py     # End-to-end persistence & idempotency tests
│           ├── test_exception_workflow.py # Exception state machine tests
│           └── test_immutable_audit.py   # DB trigger immutability & audit tests
├── data/
│   ├── input/                       # Handcrafted input CSVs (payments, settlements, bank credits, refunds)
│   ├── evaluation/                  # Handcrafted ground truth evaluation ledger
│   └── benchmark/                   # Synthetic benchmark datasets (dev, heldout, chaos)
├── docs/
│   ├── decision-spec.md             # High-level decision specification
│   ├── improved-engine-rules.md     # V1.1 Rule precedence & financial equations
│   ├── benchmark-methodology.md     # Benchmark design and metric definitions
│   ├── adversarial-test-matrix.md   # 12-case multi-fault precedence matrix
│   └── database-architecture.md     # PostgreSQL persistence and audit architecture
├── .env.example
├── pytest.ini
└── README.md
```

---

## Running the Engine & Automated Tests

### 1. Run Automated Unit Tests

Run all unit, benchmark, and adversarial precedence tests:
```bash
pytest -v backend/app/tests
```

> [!NOTE]
> When `DATABASE_URL_TEST` is not configured, database integration tests are cleanly marked as **SKIPPED**. All 49 core unit, benchmark, and adversarial tests run completely offline.

### 2. Run Reconciliation CLI

Run in side-by-side comparison mode:
```bash
python -m backend.app.main --engine compare
```

Run improved engine only:
```bash
python -m backend.app.main --engine improved
```

Run baseline engine only:
```bash
python -m backend.app.main --engine baseline
```

---

## PostgreSQL Persistence & Audit Setup

### 1. Local Database Creation (Windows / PowerShell)

```powershell
psql -U postgres -c "CREATE DATABASE reconcilex;"
psql -U postgres -c "CREATE DATABASE reconcilex_test;"
```

### 2. Local Environment Configuration

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Ensure your `.env` contains:
```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/reconcilex
DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5432/reconcilex_test
```

### 3. Initialize Database Schema

```powershell
# Initialize application database
python -m backend.app.db.migrations

# Initialize test database
python -m backend.app.db.migrations --test-db
```

### 4. Run Database Integration Tests

```powershell
pytest -v backend/app/tests/test_db_schema.py backend/app/tests/test_batch_service.py backend/app/tests/test_exception_workflow.py backend/app/tests/test_immutable_audit.py
```

---

## Adversarial Safety Testing

ReconcileX includes a 12-case adversarial test suite ([`docs/adversarial-test-matrix.md`](file:///c:/Users/avani%20manoria/OneDrive/Desktop/ReconcileX/docs/adversarial-test-matrix.md)) that subjects the engine to simultaneous multi-fault anomalies (e.g. data corruption combined with status conflicts, or missing payment IDs combined with amount variances).

Key safety guarantees:
- **Strict Precedence**: When multiple faults exist, the engine halts at the highest-priority root cause (`INVALID_ROW` $\rightarrow$ `MISSING_PAYMENT_ID` $\rightarrow$ `UNMATCHED` $\rightarrow$ `STATUS_CONFLICT` $\rightarrow$ `MISSING_REFERENCE` $\rightarrow$ `AMBIGUOUS_CANDIDATES` $\rightarrow$ `SETTLEMENT_DELAY` $\rightarrow$ `AMOUNT_VARIANCE`).
- **Zero Accidental Auto-Matches**: No adversarial combination scenario may produce an accidental `AUTO_MATCH`.
- **Deterministic Refusal**: Decisions are 100% deterministic and rule-based—no AI or heuristic guessing.

---

## Synthetic Benchmark Suite

### 1. Generate Benchmark Datasets

```bash
# Generate dev split (250 scenarios, standard distribution)
python -m backend.app.benchmark.generator --split dev --count 250 --seed 20260901

# Generate heldout split (500 scenarios, evaluation distribution)
python -m backend.app.benchmark.generator --split heldout --count 500 --seed 20260902

# Generate chaos split (100 scenarios, exception-heavy distribution)
python -m backend.app.benchmark.generator --split chaos --count 100 --seed 20260903
```

### 2. Run Benchmark Evaluations

```bash
# Evaluate improved engine on dev split
python -m backend.app.benchmark.runner --split dev --engine improved

# Compare baseline vs improved engine on heldout split
python -m backend.app.benchmark.runner --split heldout --engine compare

# Evaluate improved engine on chaos split
python -m backend.app.benchmark.runner --split chaos --engine improved
```