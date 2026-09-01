from typing import Any, Dict, List, Optional, Tuple
import psycopg
from psycopg.types.json import Jsonb

from backend.app.db.connection import jsonify
from backend.app.models import (
    BankCreditRecord,
    PaymentRecord,
    RefundRecord,
    SettlementRecord,
)


class BatchRepository:
    """Handles persistence for batches, raw source lines, and normalized input records."""

    def create_batch(
        self,
        conn: psycopg.Connection,
        batch_number: str,
        content_hash: str,
        engine_version: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new reconciliation batch record in CREATED state."""
        sql = """
        INSERT INTO reconciliation_batches (batch_number, content_hash, engine_version, status, metadata)
        VALUES (%s, %s, %s, 'CREATED', %s)
        RETURNING id;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (batch_number, content_hash, engine_version, Jsonb(jsonify(metadata or {}))))
            row = cur.fetchone()
            return str(row["id"])

    def find_by_content_hash(self, conn: psycopg.Connection, content_hash: str) -> Optional[Dict[str, Any]]:
        """Look up a batch by its canonical input content hash."""
        sql = "SELECT * FROM reconciliation_batches WHERE content_hash = %s;"
        with conn.cursor() as cur:
            cur.execute(sql, (content_hash,))
            row = cur.fetchone()
            return dict(row) if row else None

    def find_by_id(self, conn: psycopg.Connection, batch_id: str) -> Optional[Dict[str, Any]]:
        """Fetch batch by UUID primary key."""
        sql = "SELECT * FROM reconciliation_batches WHERE id = %s;"
        with conn.cursor() as cur:
            cur.execute(sql, (batch_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_batches(
        self,
        conn: psycopg.Connection,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List batches with optional status filter, ordered newest first."""
        clauses = []
        params: List[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        count_sql = f"SELECT COUNT(*) as count FROM reconciliation_batches {where_clause};"
        with conn.cursor() as cur:
            cur.execute(count_sql, tuple(params))
            total = cur.fetchone()["count"]

        query_sql = f"""
        SELECT * FROM reconciliation_batches
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])
        with conn.cursor() as cur:
            cur.execute(query_sql, tuple(params))
            items = [dict(row) for row in cur.fetchall()]

        return items, total

    def update_batch_status(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        status: str,
        error_message: Optional[str] = None,
        started_at: Optional[Any] = None,
        processing_started_at: Optional[Any] = None,
        completed_at: Optional[Any] = None,
        counts: Optional[Dict[str, int]] = None,
    ) -> None:
        """Update batch lifecycle status, timestamps, and aggregate counts."""
        updates = ["status = %s"]
        params: List[Any] = [status]

        if error_message is not None:
            updates.append("error_message = %s")
            params.append(error_message)

        if started_at is not None:
            updates.append("started_at = %s")
            params.append(started_at)

        if processing_started_at is not None:
            updates.append("processing_started_at = %s")
            params.append(processing_started_at)

        if completed_at is not None:
            updates.append("completed_at = %s")
            params.append(completed_at)

        if counts:
            for k, v in counts.items():
                updates.append(f"{k} = %s")
                params.append(v)

        params.append(batch_id)
        sql = f"UPDATE reconciliation_batches SET {', '.join(updates)} WHERE id = %s;"
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))

    def insert_raw_records(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        raw_records: List[Dict[str, Any]],
    ) -> None:
        """Bulk insert raw CSV source line payloads with quarantine status."""
        if not raw_records:
            return
        sql = """
        INSERT INTO raw_source_records (batch_id, source_file, row_index, raw_payload, is_quarantined, quarantine_reason)
        VALUES (%s, %s, %s, %s, %s, %s);
        """
        data = [
            (
                batch_id,
                r["source_file"],
                r["row_index"],
                Jsonb(r["raw_payload"]),
                r.get("is_quarantined", False),
                r.get("quarantine_reason"),
            )
            for r in raw_records
        ]
        with conn.cursor() as cur:
            cur.executemany(sql, data)

    def insert_payments(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        payments: List[PaymentRecord],
    ) -> None:
        """Bulk insert normalized payment entities."""
        if not payments:
            return
        sql = """
        INSERT INTO payments (batch_id, payment_event_id, payment_id, order_id, captured_amount, status, captured_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (batch_id, payment_event_id) DO NOTHING;
        """
        data = [
            (
                batch_id,
                p.payment_event_id,
                p.payment_id,
                p.order_id,
                p.captured_amount,
                p.status,
                p.captured_at,
            )
            for p in payments
        ]
        with conn.cursor() as cur:
            cur.executemany(sql, data)

    def insert_settlements(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        settlements: List[SettlementRecord],
    ) -> None:
        """Bulk insert normalized settlement entities."""
        if not settlements:
            return
        sql = """
        INSERT INTO settlements (batch_id, settlement_id, payment_id, gross_amount, fee_amount, gst_on_fee, net_amount, settlement_status, settled_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (batch_id, settlement_id) DO NOTHING;
        """
        data = [
            (
                batch_id,
                s.settlement_id,
                s.payment_id,
                s.gross_amount,
                s.fee_amount,
                s.gst_on_fee,
                s.net_amount,
                s.settlement_status,
                s.settled_at,
            )
            for s in settlements
        ]
        with conn.cursor() as cur:
            cur.executemany(sql, data)

    def insert_bank_credits(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        bank_credits: List[BankCreditRecord],
    ) -> None:
        """Bulk insert normalized bank credit entities."""
        if not bank_credits:
            return
        sql = """
        INSERT INTO bank_credits (batch_id, bank_txn_id, narration, credit_amount, credited_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (batch_id, bank_txn_id) DO NOTHING;
        """
        data = [
            (
                batch_id,
                b.bank_txn_id,
                b.narration,
                b.credit_amount,
                b.credited_at,
            )
            for b in bank_credits
        ]
        with conn.cursor() as cur:
            cur.executemany(sql, data)

    def insert_refunds(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        refunds: List[RefundRecord],
    ) -> None:
        """Bulk insert normalized refund entities."""
        if not refunds:
            return
        sql = """
        INSERT INTO refunds (batch_id, refund_id, payment_id, refund_amount, refund_status, refunded_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (batch_id, refund_id) DO NOTHING;
        """
        data = [
            (
                batch_id,
                r.refund_id,
                r.payment_id,
                r.refund_amount,
                r.refund_status,
                r.refunded_at,
            )
            for r in refunds
        ]
        with conn.cursor() as cur:
            cur.executemany(sql, data)
