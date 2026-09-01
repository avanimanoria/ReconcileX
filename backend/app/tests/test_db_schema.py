"""Tests for PostgreSQL relational schema integrity and constraints."""

import pytest
import psycopg


def test_schema_tables_exist(db_conn):
    """Verify all 9 required schema tables exist in the test database."""
    expected_tables = {
        "reconciliation_batches",
        "raw_source_records",
        "payments",
        "settlements",
        "bank_credits",
        "refunds",
        "reconciliation_results",
        "exceptions",
        "audit_events",
    }
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public';
            """
        )
        existing_tables = {row["table_name"] for row in cur.fetchall()}

    assert expected_tables.issubset(existing_tables), f"Missing tables: {expected_tables - existing_tables}"


def test_batch_scoped_uniqueness_constraints(db_conn):
    """Verify entity identifiers are scoped to batch_id."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT conname, contype
            FROM pg_constraint
            WHERE conname IN (
                'uq_payment_event_per_batch',
                'uq_settlement_per_batch',
                'uq_bank_txn_per_batch',
                'uq_refund_per_batch',
                'uq_raw_source_row'
            );
            """
        )
        constraints = {row["conname"] for row in cur.fetchall()}

    assert "uq_payment_event_per_batch" in constraints
    assert "uq_settlement_per_batch" in constraints
    assert "uq_bank_txn_per_batch" in constraints
    assert "uq_refund_per_batch" in constraints
    assert "uq_raw_source_row" in constraints
