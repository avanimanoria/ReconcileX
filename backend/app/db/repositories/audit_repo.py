"""Append-only repository for immutable audit event ledger.

This repository provides strictly insert and read operations.
No update or delete methods exist by design.
"""

from typing import Any, Dict, List, Optional
import psycopg
from psycopg.types.json import Jsonb

from backend.app.db.connection import jsonify
from backend.app.models import AuditEntry


class AuditRepository:
    """Append-only data access for immutable audit events."""

    def insert_audit_event(
        self,
        conn: psycopg.Connection,
        event_type: str,
        entity_type: str,
        entity_id: str,
        action: str,
        reason: str,
        batch_id: Optional[str] = None,
        exception_id: Optional[str] = None,
        actor: str = "SYSTEM",
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert a single immutable audit event."""
        sql = """
        INSERT INTO audit_events (
            batch_id, exception_id, event_type, entity_type, entity_id,
            actor, action, before_state, after_state, reason, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    batch_id,
                    exception_id,
                    event_type,
                    entity_type,
                    entity_id,
                    actor,
                    action,
                    Jsonb(jsonify(before_state)) if before_state is not None else None,
                    Jsonb(jsonify(after_state)) if after_state is not None else None,
                    reason,
                    Jsonb(jsonify(metadata or {})),
                ),
            )
            row = cur.fetchone()
            return str(row["id"])

    def insert_audit_entries(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        entries: List[AuditEntry],
    ) -> None:
        """Bulk insert audit entries produced by loader / matcher."""
        if not entries:
            return
        sql = """
        INSERT INTO audit_events (
            batch_id, event_type, entity_type, entity_id, actor, action, reason, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        data = [
            (
                batch_id,
                e.event_type,
                "PAYMENT" if "PAY" in e.entity_id or "evt" in e.entity_id else "ROW",
                e.entity_id,
                "SYSTEM",
                e.event_type,
                e.reason,
                Jsonb(jsonify(e.details or {})),
            )
            for e in entries
        ]
        with conn.cursor() as cur:
            cur.executemany(sql, data)

    def list_audit_events_for_batch(
        self,
        conn: psycopg.Connection,
        batch_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve audit history for a batch in chronological sequence."""
        sql = """
        SELECT * FROM audit_events
        WHERE batch_id = %s
        ORDER BY event_sequence ASC;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (batch_id,))
            return [dict(row) for row in cur.fetchall()]

    def list_audit_events_for_exception(
        self,
        conn: psycopg.Connection,
        exception_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve audit history for an exception in chronological sequence."""
        sql = """
        SELECT * FROM audit_events
        WHERE exception_id = %s
        ORDER BY event_sequence ASC;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (exception_id,))
            return [dict(row) for row in cur.fetchall()]

    def list_audit_events_for_entity(
        self,
        conn: psycopg.Connection,
        entity_type: str,
        entity_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve audit events for a specific domain entity."""
        sql = """
        SELECT * FROM audit_events
        WHERE entity_type = %s AND entity_id = %s
        ORDER BY event_sequence ASC;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (entity_type, entity_id))
            return [dict(row) for row in cur.fetchall()]
