# ReconcileX PostgreSQL Persistence & Immutable Audit Architecture

## 1. Architectural Principles

ReconcileX separates financial reconciliation execution from relational persistence:

1. **Authoritative Python Engine**: The database stores raw source lines, normalized entities, execution batches, reconciliation outcomes, exceptions, and audit events. The database **never** computes or infers matches.
2. **Strict Money Safety**: All monetary values use `NUMERIC(18, 2)` (mapped to `decimal.Decimal` in Python). Floating-point data types are prohibited.
3. **Batch-Scoped Entity Keys**: Identifiers (`payment_event_id`, `settlement_id`, `bank_txn_id`, `refund_id`) are constrained per `batch_id` via `UNIQUE (batch_id, <entity_id>)`, ensuring clean multi-batch history and re-processing.
4. **Database-Level Immutability**: PostgreSQL database triggers explicitly block `UPDATE` and `DELETE` on `audit_events`.
5. **Deterministic Priority Mapping**: Exception priorities are assigned at creation time using a deterministic mapping hierarchy.

---

## 2. Relational Schema Reference

```mermaid
erDiagram
    reconciliation_batches ||--o{ raw_source_records : contains
    reconciliation_batches ||--o{ payments : ingests
    reconciliation_batches ||--o{ settlements : ingests
    reconciliation_batches ||--o{ bank_credits : ingests
    reconciliation_batches ||--o{ refunds : ingests
    reconciliation_batches ||--o{ reconciliation_results : produces
    reconciliation_results ||--o| exceptions : creates
    exceptions ||--o{ audit_events : tracks
    reconciliation_batches ||--o{ audit_events : tracks
```

### Table Summary

| Table Name | Primary Key | Key Constraints & Indexes | Description |
|---|---|---|---|
| `reconciliation_batches` | `UUID` | `content_hash UNIQUE`, `batch_number UNIQUE` | Tracks batch lifecycle (`CREATED`, `INGESTING`, `PROCESSING`, `COMPLETED`, `FAILED`), counts, and execution timestamps. |
| `raw_source_records` | `UUID` | `UNIQUE (batch_id, source_file, row_index)` | Preserves verbatim input line payloads (`JSONB`) and quarantine flags. |
| `payments` | `UUID` | `UNIQUE (batch_id, payment_event_id)`, `INDEX (batch_id, payment_id)` | Normalized valid payments (`captured_amount NUMERIC(18, 2)`). |
| `settlements` | `UUID` | `UNIQUE (batch_id, settlement_id)`, `INDEX (batch_id, payment_id)` | Normalized provider settlements. |
| `bank_credits` | `UUID` | `UNIQUE (batch_id, bank_txn_id)` | Normalized bank credit transactions. |
| `refunds` | `UUID` | `UNIQUE (batch_id, refund_id)`, `INDEX (batch_id, payment_id)` | Normalized refund transactions. |
| `reconciliation_results` | `UUID` | `UNIQUE (batch_id, settlement_id)` partial index | Output match results with `rule_version` (`v1.1-deterministic`) and `financial_evidence` (`JSONB`). |
| `exceptions` | `UUID` | `reconciliation_result_id UNIQUE`, `INDEX (batch_id, status, priority)` | Exception workflow tracker (`OPEN`, `IN_REVIEW`, `RESOLVED`, `DISMISSED`). |
| `audit_events` | `UUID` | `event_sequence BIGSERIAL UNIQUE`, DB Triggers blocking `UPDATE`/`DELETE` | Append-only audit ledger tracking entity and state transitions. |

---

## 3. Exception Priority Mapping

| Exception Category | Priority | Rationale |
|---|---|---|
| `INVALID_ROW` | **CRITICAL** | Data pipeline failure, unparseable money, or corrupted payload |
| `AMOUNT_VARIANCE` | **HIGH** | Financial discrepancy between provider settlement and bank credit |
| `STATUS_CONFLICT` | **HIGH** | Life-cycle contradiction (payment failed but settled/credited) |
| `AMBIGUOUS_CANDIDATES` | **HIGH** | Multiple competing bank transactions; potential duplicate credit |
| `MISSING_PAYMENT_ID` | **MEDIUM** | Settlement record missing payment link |
| `MISSING_REFERENCE` | **MEDIUM** | Bank narration missing settlement ID reference |
| `SETTLEMENT_DELAY` | **MEDIUM** | Settlement SLA timing policy breach (> 7 calendar days) |
| `UNMATCHED` | **MEDIUM** | Referenced payment record not present in batch |
| `DUPLICATE_EVENT` | **LOW** | Idempotently handled duplicate ingestion event |

---

## 4. State Machines

### A. Batch Lifecycle
```text
  [CREATED]
     │
     ▼
 [INGESTING] ───(error)───► [FAILED]
     │
     ▼
[PROCESSING] ───(error)───► [FAILED]
     │
     ▼
[COMPLETED]
```

### B. Exception Lifecycle
```text
      [OPEN]
     /      \
    ▼        ▼
[IN_REVIEW] [DISMISSED]
  │      ▲       ▲
  ▼      │       │
[RESOLVED]───────┘
```
- Allowed transitions: `OPEN -> IN_REVIEW`, `OPEN -> DISMISSED` (with reason), `IN_REVIEW -> RESOLVED` (with reason & actor), `IN_REVIEW -> DISMISSED` (with reason & actor), `RESOLVED -> IN_REVIEW`, `DISMISSED -> IN_REVIEW`.
- Reopening clears `resolved_by` and `resolved_at` while preserving previous state in immutable `audit_events`.

---

## 5. Local PostgreSQL Setup (Windows / PowerShell)

### 1. Create Databases in PostgreSQL
```powershell
psql -U postgres -c "CREATE DATABASE reconcilex;"
psql -U postgres -c "CREATE DATABASE reconcilex_test;"
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Ensure `.env` contains:
```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/reconcilex
DATABASE_URL_TEST=postgresql://postgres:postgres@localhost:5432/reconcilex_test
```

### 3. Initialize Schema
```powershell
# Initialize application database
python -m backend.app.db.migrations

# Initialize test database
python -m backend.app.db.migrations --test-db
```

### 4. Run Tests
```powershell
# Run all tests (including database integration tests when DATABASE_URL_TEST is set)
pytest -v backend/app/tests
```
