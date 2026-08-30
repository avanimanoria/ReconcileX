# ReconcileX — V1 Offline Reconciliation Engine

ReconcileX is a deterministic, offline Python financial reconciliation engine designed to match merchant payments, payment gateway settlements, and bank credit records.

## Project Structure

```text
ReconcileX/
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── models.py       # Dataclasses, Enums, and Result structures (using Decimal)
│       ├── loader.py       # CSV ingestion, validation, and invalid row quarantine
│       ├── baseline.py     # Deterministic baseline matcher (rules 1–9)
│       ├── evaluator.py    # Ground-truth comparison and metrics engine
│       ├── main.py         # CLI entry point and report generator
│       └── tests/
│           ├── __init__.py
│           ├── test_loader.py     # Ingestion, parsing, and quarantine tests
│           ├── test_baseline.py   # Baseline rules, idempotency, and exception tests
│           └── test_evaluator.py  # Ground truth evaluation tests
├── data/
│   ├── input/              # Input CSVs (payments, settlements, bank credits, refunds)
│   └── evaluation/         # Ground truth evaluation ledger
├── docs/                   # Decision specs and architectural documentation
└── README.md
```

## Running the Engine

### 1. Run Unit Tests with pytest

Execute all automated unit tests:

```bash
pytest -v backend/app/tests
```

### 2. Run Reconciliation CLI

Run the reconciliation engine from the project root:

```bash
python -m backend.app.main
```

Optional CLI arguments:
- `--data-dir`: Custom path to input CSV directory (default: `data/input`)
- `--truth-file`: Custom path to evaluation truth ledger (default: `data/evaluation/truth_ledger.csv`)

Example:
```bash
python -m backend.app.main --data-dir data/input --truth-file data/evaluation/truth_ledger.csv
```

## Baseline Matching Rules

1. **Idempotency**: `payment_event_id` is an idempotency key. Duplicate events are ignored during ingestion and logged as `DUPLICATE_EVENT` audit entries.
2. **Status Eligibility**: Only payments with status `captured` are eligible for reconciliation. Non-captured records result in `STATUS_CONFLICT`.
3. **Settlement Linkage**: A settlement must reference a valid captured payment ID; missing payment IDs produce `MISSING_PAYMENT_ID`.
4. **Bank Reference Linkage**: A bank credit is linked only if its narration contains the `settlement_id`. Otherwise, a `MISSING_REFERENCE` exception is raised.
5. **Data Quarantine**: Invalid rows (such as `BANK-015` with non-numeric amount) are gracefully quarantined as `INVALID_ROW` without halting batch execution.
6. **Ground Truth Separation**: Ground truth evaluation is strictly decoupled from the baseline matching engine.