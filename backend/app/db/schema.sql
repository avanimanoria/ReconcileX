-- ============================================================================
-- ReconcileX PostgreSQL DDL Schema
-- Money-safe types: NUMERIC(18, 2), TIMESTAMPTZ, UUID, JSONB
-- ============================================================================

-- Enable pgcrypto for UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Reconciliation Batches
CREATE TABLE IF NOT EXISTS reconciliation_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_number VARCHAR(64) NOT NULL UNIQUE,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'CREATED'
        CHECK (status IN ('CREATED', 'INGESTING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    engine_version VARCHAR(32) NOT NULL,
    total_payments INTEGER NOT NULL DEFAULT 0,
    total_settlements INTEGER NOT NULL DEFAULT 0,
    total_bank_credits INTEGER NOT NULL DEFAULT 0,
    total_refunds INTEGER NOT NULL DEFAULT 0,
    auto_match_count INTEGER NOT NULL DEFAULT 0,
    exception_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    processing_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- 2. Raw Source Records (Exact verbatim CSV lines + Quarantine flags)
CREATE TABLE IF NOT EXISTS raw_source_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE RESTRICT,
    source_file VARCHAR(64) NOT NULL,
    row_index INTEGER NOT NULL,
    raw_payload JSONB NOT NULL,
    is_quarantined BOOLEAN NOT NULL DEFAULT FALSE,
    quarantine_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_raw_source_row UNIQUE (batch_id, source_file, row_index)
);

-- 3. Payments (Normalized, single valid event per payment_event_id per batch)
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE RESTRICT,
    payment_event_id VARCHAR(128) NOT NULL,
    payment_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    captured_amount NUMERIC(18, 2) NOT NULL CHECK (captured_amount >= 0),
    status VARCHAR(32) NOT NULL CHECK (status IN ('captured', 'failed', 'pending')),
    captured_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payment_event_per_batch UNIQUE (batch_id, payment_event_id)
);
CREATE INDEX IF NOT EXISTS idx_payments_batch_pay_id ON payments (batch_id, payment_id);

-- 4. Settlements (Normalized)
CREATE TABLE IF NOT EXISTS settlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE RESTRICT,
    settlement_id VARCHAR(64) NOT NULL,
    payment_id VARCHAR(64),
    gross_amount NUMERIC(18, 2) NOT NULL CHECK (gross_amount >= 0),
    fee_amount NUMERIC(18, 2) NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
    gst_on_fee NUMERIC(18, 2) NOT NULL DEFAULT 0 CHECK (gst_on_fee >= 0),
    net_amount NUMERIC(18, 2) NOT NULL,
    settlement_status VARCHAR(32) NOT NULL,
    settled_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_settlement_per_batch UNIQUE (batch_id, settlement_id)
);
CREATE INDEX IF NOT EXISTS idx_settlements_batch_pay_id ON settlements (batch_id, payment_id);

-- 5. Bank Credits (Normalized)
CREATE TABLE IF NOT EXISTS bank_credits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE RESTRICT,
    bank_txn_id VARCHAR(64) NOT NULL,
    narration TEXT NOT NULL,
    credit_amount NUMERIC(18, 2) NOT NULL CHECK (credit_amount >= 0),
    credited_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bank_txn_per_batch UNIQUE (batch_id, bank_txn_id)
);

-- 6. Refunds (Normalized)
CREATE TABLE IF NOT EXISTS refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE RESTRICT,
    refund_id VARCHAR(64) NOT NULL,
    payment_id VARCHAR(64) NOT NULL,
    refund_amount NUMERIC(18, 2) NOT NULL CHECK (refund_amount > 0),
    refund_status VARCHAR(32) NOT NULL,
    refunded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_refund_per_batch UNIQUE (batch_id, refund_id)
);
CREATE INDEX IF NOT EXISTS idx_refunds_batch_pay_id ON refunds (batch_id, payment_id);

-- 7. Reconciliation Results (One-to-One Matches and Exceptions)
CREATE TABLE IF NOT EXISTS reconciliation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE RESTRICT,
    rule_version VARCHAR(64) NOT NULL,
    payment_id VARCHAR(64),
    settlement_id VARCHAR(64),
    bank_txn_id VARCHAR(64),
    refund_id VARCHAR(64),
    match_status VARCHAR(32) NOT NULL CHECK (match_status IN ('AUTO_MATCH', 'EXCEPTION')),
    exception_type VARCHAR(32) CHECK (exception_type IN (
        'DUPLICATE_EVENT', 'MISSING_PAYMENT_ID', 'MISSING_REFERENCE',
        'STATUS_CONFLICT', 'INVALID_ROW', 'UNMATCHED',
        'AMBIGUOUS_CANDIDATES', 'AMOUNT_VARIANCE', 'SETTLEMENT_DELAY'
    )),
    reason TEXT NOT NULL,
    financial_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_recon_result_per_settlement
ON reconciliation_results (batch_id, settlement_id)
WHERE settlement_id IS NOT NULL;

-- 8. Exceptions (Lifecycle Tracking & Resolution)
CREATE TABLE IF NOT EXISTS exceptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE RESTRICT,
    reconciliation_result_id UUID NOT NULL UNIQUE REFERENCES reconciliation_results(id) ON DELETE RESTRICT,
    category VARCHAR(32) NOT NULL,
    priority VARCHAR(16) NOT NULL CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    status VARCHAR(32) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'IN_REVIEW', 'RESOLVED', 'DISMISSED')),
    assigned_to VARCHAR(128),
    resolution_reason TEXT,
    resolved_by VARCHAR(128),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_exceptions_batch_status ON exceptions (batch_id, status, priority);

-- 9. Audit Events (Append-Only Immutable Ledger)
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_sequence BIGSERIAL NOT NULL UNIQUE,
    batch_id UUID REFERENCES reconciliation_batches(id) ON DELETE SET NULL,
    exception_id UUID REFERENCES exceptions(id) ON DELETE SET NULL,
    event_type VARCHAR(64) NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    actor VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    action VARCHAR(64) NOT NULL,
    before_state JSONB,
    after_state JSONB,
    reason TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_events_batch ON audit_events (batch_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events (entity_type, entity_id);

-- Database-Level Immutable Audit Triggers
CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events;
CREATE TRIGGER audit_events_no_update
BEFORE UPDATE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();

DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events;
CREATE TRIGGER audit_events_no_delete
BEFORE DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
