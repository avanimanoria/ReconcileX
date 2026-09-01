from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import psycopg
from psycopg.types.json import Jsonb

from backend.app.db.connection import jsonify
from backend.app.models import MatchStatus, ReconcileResult

CATEGORY_PRIORITY_MAP = {
    "INVALID_ROW": "CRITICAL",
    "AMOUNT_VARIANCE": "HIGH",
    "STATUS_CONFLICT": "HIGH",
    "AMBIGUOUS_CANDIDATES": "HIGH",
    "MISSING_PAYMENT_ID": "MEDIUM",
    "MISSING_REFERENCE": "MEDIUM",
    "SETTLEMENT_DELAY": "MEDIUM",
    "UNMATCHED": "MEDIUM",
    "DUPLICATE_EVENT": "LOW",
}


def get_category_priority(category: str) -> str:
    """Return deterministic priority for a given exception category."""
    return CATEGORY_PRIORITY_MAP.get(category.upper(), "MEDIUM")


class ReconRepository:
    """Handles persistence for reconciliation results and exceptions."""

    def insert_results_and_exceptions(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        rule_version: str,
        results: List[ReconcileResult],
    ) -> List[Dict[str, Any]]:
        """Insert reconciliation results and create associated exception records."""
        inserted_exceptions = []

        result_sql = """
        INSERT INTO reconciliation_results (
            batch_id, rule_version, payment_id, settlement_id, bank_txn_id, refund_id,
            match_status, exception_type, reason, financial_evidence
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, match_status, exception_type;
        """

        exception_sql = """
        INSERT INTO exceptions (batch_id, reconciliation_result_id, category, priority, status)
        VALUES (%s, %s, %s, %s, 'OPEN')
        RETURNING id, category, priority, status;
        """

        with conn.cursor() as cur:
            for r in results:
                exc_type_val = r.exception_type.value if r.exception_type else None
                cur.execute(
                    result_sql,
                    (
                        batch_id,
                        rule_version,
                        r.payment_id,
                        r.settlement_id,
                        r.bank_txn_id,
                        r.refund_id,
                        r.match_status.value,
                        exc_type_val,
                        r.reason,
                        Jsonb(jsonify(r.details or {})),
                    ),
                )
                res_row = cur.fetchone()
                recon_res_id = res_row["id"]

                # If result is an EXCEPTION, create exception record
                if r.match_status == MatchStatus.EXCEPTION and exc_type_val:
                    priority = get_category_priority(exc_type_val)
                    cur.execute(exception_sql, (batch_id, recon_res_id, exc_type_val, priority))
                    exc_row = cur.fetchone()
                    inserted_exceptions.append({
                        "exception_id": str(exc_row["id"]),
                        "reconciliation_result_id": str(recon_res_id),
                        "category": exc_row["category"],
                        "priority": exc_row["priority"],
                        "status": exc_row["status"],
                        "settlement_id": r.settlement_id,
                        "payment_id": r.payment_id,
                    })

        return inserted_exceptions

    def get_exception_by_id(self, conn: psycopg.Connection, exception_id: str) -> Optional[Dict[str, Any]]:
        """Fetch exception details by ID."""
        sql = """
        SELECT e.*, r.payment_id, r.settlement_id, r.bank_txn_id, r.reason as engine_reason, r.financial_evidence
        FROM exceptions e
        JOIN reconciliation_results r ON e.reconciliation_result_id = r.id
        WHERE e.id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (exception_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_exception_for_update(self, conn: psycopg.Connection, exception_id: str) -> Optional[Dict[str, Any]]:
        """Fetch exception with a row-level lock (SELECT FOR UPDATE) for atomic state transitions."""
        sql = """
        SELECT e.*, r.payment_id, r.settlement_id
        FROM exceptions e
        JOIN reconciliation_results r ON e.reconciliation_result_id = r.id
        WHERE e.id = %s
        FOR UPDATE;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (exception_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def update_exception(
        self,
        conn: psycopg.Connection,
        exception_id: str,
        status: str,
        assigned_to: Optional[str] = None,
        resolution_reason: Optional[str] = None,
        resolved_by: Optional[str] = None,
        resolved_at: Optional[datetime] = None,
    ) -> None:
        """Update exception lifecycle fields."""
        sql = """
        UPDATE exceptions
        SET status = %s,
            assigned_to = %s,
            resolution_reason = %s,
            resolved_by = %s,
            resolved_at = %s,
            updated_at = NOW()
        WHERE id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (status, assigned_to, resolution_reason, resolved_by, resolved_at, exception_id),
            )

    def list_exceptions_by_batch(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List exceptions for a batch with optional filters and pagination."""
        clauses = ["e.batch_id = %s"]
        params: List[Any] = [batch_id]

        if status:
            clauses.append("e.status = %s")
            params.append(status)
        if priority:
            clauses.append("e.priority = %s")
            params.append(priority)
        if category:
            clauses.append("e.category = %s")
            params.append(category)

        where_clause = "WHERE " + " AND ".join(clauses)

        count_sql = f"""
        SELECT COUNT(*) as count
        FROM exceptions e
        JOIN reconciliation_results r ON e.reconciliation_result_id = r.id
        {where_clause};
        """
        with conn.cursor() as cur:
            cur.execute(count_sql, tuple(params))
            total = cur.fetchone()["count"]

        query_sql = f"""
        SELECT e.*, r.payment_id, r.settlement_id, r.bank_txn_id, r.reason, r.financial_evidence
        FROM exceptions e
        JOIN reconciliation_results r ON e.reconciliation_result_id = r.id
        {where_clause}
        ORDER BY e.created_at ASC
        LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])
        with conn.cursor() as cur:
            cur.execute(query_sql, tuple(params))
            items = [dict(row) for row in cur.fetchall()]

        return items, total

    def list_results_by_batch(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        match_status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List reconciliation results for a batch with optional match_status filter and pagination."""
        clauses = ["batch_id = %s"]
        params: List[Any] = [batch_id]

        if match_status:
            clauses.append("match_status = %s")
            params.append(match_status)

        where_clause = "WHERE " + " AND ".join(clauses)

        count_sql = f"SELECT COUNT(*) as count FROM reconciliation_results {where_clause};"
        with conn.cursor() as cur:
            cur.execute(count_sql, tuple(params))
            total = cur.fetchone()["count"]

        query_sql = f"""
        SELECT * FROM reconciliation_results
        {where_clause}
        ORDER BY created_at ASC
        LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])
        with conn.cursor() as cur:
            cur.execute(query_sql, tuple(params))
            items = [dict(row) for row in cur.fetchall()]

        return items, total
