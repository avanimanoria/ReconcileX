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

## Expected Results Comparison

| Metric | Baseline Engine (V1.0) | Improved Engine (V1.1) |
|---|---|---|
| **Total Scenarios** | 15 | 15 |
| **Exact Matches with Truth** | 13 | 15 |
| **Mismatches** | 2 (`TG-005`, `TG-007`) | 0 |
| **Accuracy** | 86.7% | 100.0% |
| **Auto-Matches** | 10 | 8 |
| **Exceptions** | 5 | 7 |

---

## Design & Architecture Principles

- **No AI in Financial Decisions**: The engine is 100% deterministic and rule-based. AI, ML, fuzzy matching, and heuristics are intentionally omitted by design to ensure absolute auditability and financial correctness.
- **Strict Decimal Math**: All calculations use Python's `decimal.Decimal` with a strict `₹0.01` (1 paisa) tolerance. Floating-point numbers are forbidden.
- **Strict 1-to-1 Matching**: One payment $\leftrightarrow$ One settlement $\leftrightarrow$ One bank credit.
- **Decoupled Evaluation**: Ground truth evaluation ledger is strictly separated from engine matching logic.
- **Offline & Self-Contained**: No external APIs, databases, or cloud dependencies.

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
│       └── tests/
│           ├── __init__.py
│           ├── test_loader.py            # Ingestion, parsing, and quarantine tests
│           ├── test_baseline.py          # Baseline rules and exception tests
│           └── test_improved_matcher.py  # V1.1 financial validation & timing tests
├── data/
│   ├── input/                       # Input CSVs (payments, settlements, bank credits, refunds)
│   └── evaluation/                  # Ground truth evaluation ledger
├── docs/
│   ├── decision-spec.md             # High-level decision specification
│   └── improved-engine-rules.md     # V1.1 Rule precedence & financial equations
├── pytest.ini
└── README.md
```

---

## Running the Engine

### 1. Run Automated Unit Tests

```bash
pytest -v backend/app/tests
```

### 2. Run Reconciliation CLI

Run in side-by-side comparison mode (default):
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

Optional CLI parameters:
- `--data-dir`: Custom path to input directory (default: `data/input`)
- `--truth-file`: Custom path to evaluation file (default: `data/evaluation/truth_ledger.csv`)