"""Batch ingestion and reconciliation persistence service for ReconcileX."""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import psycopg

from backend.app.db.repositories.audit_repo import AuditRepository
from backend.app.db.repositories.batch_repo import BatchRepository
from backend.app.db.repositories.recon_repo import ReconRepository
from backend.app.improved_matcher import run_improved_reconciliation
from backend.app.loader import load_dataset
from backend.app.models import MatchStatus


class BatchDisposition(str, Enum):
    PROCESSED_NEW = "PROCESSED_NEW"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    PREVIOUSLY_FAILED = "PREVIOUSLY_FAILED"


class BatchAlreadyInProgressError(Exception):
    """Raised when a batch with the same input content hash is currently being processed."""


@dataclass
class BatchResultSummary:
    batch_id: str
    batch_number: str
    disposition: BatchDisposition
    status: str
    total_payments: int
    total_settlements: int
    total_bank_credits: int
    total_refunds: int
    auto_match_count: int
    exception_count: int
    exceptions: List[Dict[str, Any]]


def compute_canonical_content_hash(
    payments_bytes: bytes,
    settlements_bytes: bytes,
    bank_credits_bytes: bytes,
    refunds_bytes: bytes,
) -> str:
    """Compute canonical boundary-safe SHA-256 hash across input files."""
    hasher = hashlib.sha256()
    hasher.update(b"payments.csv\x00" + payments_bytes)
    hasher.update(b"settlements.csv\x00" + settlements_bytes)
    hasher.update(b"bank_credits.csv\x00" + bank_credits_bytes)
    hasher.update(b"refunds.csv\x00" + refunds_bytes)
    return hasher.hexdigest()


def extract_raw_csv_records(file_name: str, content_str: str) -> List[Dict[str, Any]]:
    """Parse raw string dictionary per line for audit staging."""
    raw_records = []
    reader = csv.DictReader(StringIO(content_str))
    for idx, row in enumerate(reader, start=1):
        raw_records.append({
            "source_file": file_name,
            "row_index": idx,
            "raw_payload": dict(row),
            "is_quarantined": False,
            "quarantine_reason": None,
        })
    return raw_records


class BatchService:
    """Orchestrates CSV ingestion, deterministic matching, and relational persistence."""

    def __init__(
        self,
        batch_repo: Optional[BatchRepository] = None,
        recon_repo: Optional[ReconRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        engine_version: str = "v1.1-deterministic",
    ) -> None:
        self.batch_repo = batch_repo or BatchRepository()
        self.recon_repo = recon_repo or ReconRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.engine_version = engine_version

    def process_csv_directory(
        self,
        conn: psycopg.Connection,
        data_dir: Path,
        batch_number: Optional[str] = None,
    ) -> BatchResultSummary:
        """Read CSV files from a directory and process the batch transactionally."""
        p_path = data_dir / "payments.csv"
        s_path = data_dir / "settlements.csv"
        b_path = data_dir / "bank_credits.csv"
        r_path = data_dir / "refunds.csv"

        p_bytes = p_path.read_bytes() if p_path.exists() else b""
        s_bytes = s_path.read_bytes() if s_path.exists() else b""
        b_bytes = b_path.read_bytes() if b_path.exists() else b""
        r_bytes = r_path.read_bytes() if r_path.exists() else b""

        return self.process_batch(
            conn=conn,
            data_dir=data_dir,
            payments_bytes=p_bytes,
            settlements_bytes=s_bytes,
            bank_credits_bytes=b_bytes,
            refunds_bytes=r_bytes,
            batch_number=batch_number,
        )

    def process_batch(
        self,
        conn: psycopg.Connection,
        data_dir: Path,
        payments_bytes: bytes,
        settlements_bytes: bytes,
        bank_credits_bytes: bytes,
        refunds_bytes: bytes,
        batch_number: Optional[str] = None,
    ) -> BatchResultSummary:
        """Execute full idempotent batch workflow."""
        content_hash = compute_canonical_content_hash(
            payments_bytes, settlements_bytes, bank_credits_bytes, refunds_bytes
        )

        # 1. Check Idempotency via content hash
        existing = self.batch_repo.find_by_content_hash(conn, content_hash)
        if existing:
            batch_id = str(existing["id"])
            existing_status = existing["status"]

            if existing_status == "COMPLETED":
                # Return existing completed batch without duplicating records or audit events
                exceptions = self.recon_repo.list_exceptions_by_batch(conn, batch_id)
                return BatchResultSummary(
                    batch_id=batch_id,
                    batch_number=existing["batch_number"],
                    disposition=BatchDisposition.ALREADY_COMPLETED,
                    status=existing_status,
                    total_payments=existing["total_payments"],
                    total_settlements=existing["total_settlements"],
                    total_bank_credits=existing["total_bank_credits"],
                    total_refunds=existing["total_refunds"],
                    auto_match_count=existing["auto_match_count"],
                    exception_count=existing["exception_count"],
                    exceptions=exceptions,
                )
            elif existing_status in ("CREATED", "INGESTING", "PROCESSING"):
                raise BatchAlreadyInProgressError(
                    f"Batch '{existing['batch_number']}' with identical content hash is already in progress ({existing_status})."
                )
            elif existing_status == "FAILED":
                exceptions = self.recon_repo.list_exceptions_by_batch(conn, batch_id)
                return BatchResultSummary(
                    batch_id=batch_id,
                    batch_number=existing["batch_number"],
                    disposition=BatchDisposition.PREVIOUSLY_FAILED,
                    status=existing_status,
                    total_payments=existing["total_payments"],
                    total_settlements=existing["total_settlements"],
                    total_bank_credits=existing["total_bank_credits"],
                    total_refunds=existing["total_refunds"],
                    auto_match_count=existing["auto_match_count"],
                    exception_count=existing["exception_count"],
                    exceptions=exceptions,
                )

        # Generate unique batch number if not provided
        if not batch_number:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            batch_number = f"BATCH-{now_str}-{content_hash[:8]}"

        # 2. Ingestion & Normalization Staging
        # Load in-memory dataset using existing authoritative loader
        dataset = load_dataset(data_dir=data_dir)

        # Extract raw source records for full audit trail
        raw_records: List[Dict[str, Any]] = []
        raw_records.extend(extract_raw_csv_records("payments.csv", payments_bytes.decode("utf-8", errors="replace")))
        raw_records.extend(extract_raw_csv_records("settlements.csv", settlements_bytes.decode("utf-8", errors="replace")))
        raw_records.extend(extract_raw_csv_records("bank_credits.csv", bank_credits_bytes.decode("utf-8", errors="replace")))
        raw_records.extend(extract_raw_csv_records("refunds.csv", refunds_bytes.decode("utf-8", errors="replace")))

        # Mark quarantined rows in raw records
        quarantined_record_ids = {q.record_id for q in dataset.quarantined_rows if q.record_id}
        for r in raw_records:
            rec_id = r["raw_payload"].get("bank_txn_id") or r["raw_payload"].get("payment_id") or r["raw_payload"].get("settlement_id")
            if rec_id and rec_id in quarantined_record_ids:
                r["is_quarantined"] = True
                matched_q = next((q for q in dataset.quarantined_rows if q.record_id == rec_id), None)
                if matched_q:
                    r["quarantine_reason"] = matched_q.error_reason

        # Transaction 1: Create batch and stage raw + normalized entities
        with conn.transaction():
            batch_id = self.batch_repo.create_batch(
                conn,
                batch_number=batch_number,
                content_hash=content_hash,
                engine_version=self.engine_version,
                metadata={"source_dir": str(data_dir)},
            )

            now_utc = datetime.now(timezone.utc)
            self.batch_repo.update_batch_status(conn, batch_id, status="INGESTING", started_at=now_utc)

            # Insert audit event for batch creation
            self.audit_repo.insert_audit_event(
                conn,
                batch_id=batch_id,
                event_type="BATCH_CREATED",
                entity_type="BATCH",
                entity_id=batch_id,
                action="CREATE_BATCH",
                reason=f"Initialized reconciliation batch '{batch_number}'.",
                metadata={"content_hash": content_hash, "source_dir": str(data_dir)},
            )

            # Insert raw records
            self.batch_repo.insert_raw_records(conn, batch_id, raw_records)

            # Insert normalized entities
            self.batch_repo.insert_payments(conn, batch_id, dataset.payments)
            self.batch_repo.insert_settlements(conn, batch_id, dataset.settlements)
            self.batch_repo.insert_bank_credits(conn, batch_id, dataset.bank_credits)
            self.batch_repo.insert_refunds(conn, batch_id, dataset.refunds)

            # Record audit entries from loader (e.g. duplicate event audits)
            self.audit_repo.insert_audit_entries(conn, batch_id, dataset.audit_logs)

            # Transition to PROCESSING
            self.batch_repo.update_batch_status(
                conn, batch_id, status="PROCESSING", processing_started_at=datetime.now(timezone.utc)
            )

        # 3. Deterministic Matching Execution (in-memory)
        try:
            batch_result = run_improved_reconciliation(dataset)
        except Exception as e:
            with conn.transaction():
                self.batch_repo.update_batch_status(
                    conn, batch_id, status="FAILED", error_message=str(e), completed_at=datetime.now(timezone.utc)
                )
                self.audit_repo.insert_audit_event(
                    conn,
                    batch_id=batch_id,
                    event_type="BATCH_FAILED",
                    entity_type="BATCH",
                    entity_id=batch_id,
                    action="FAIL_BATCH",
                    reason=f"Batch execution failed with unhandled exception: {e}",
                )
            raise

        # Transaction 2: Persist reconciliation results, exceptions, and finalize batch
        with conn.transaction():
            inserted_exceptions = self.recon_repo.insert_results_and_exceptions(
                conn,
                batch_id=batch_id,
                rule_version=self.engine_version,
                results=batch_result.results,
            )

            # Insert audit events for initial exception creation
            for exc in inserted_exceptions:
                self.audit_repo.insert_audit_event(
                    conn,
                    batch_id=batch_id,
                    exception_id=exc["exception_id"],
                    event_type="EXCEPTION_CREATED",
                    entity_type="EXCEPTION",
                    entity_id=exc["exception_id"],
                    action="CREATE_EXCEPTION",
                    reason=f"Engine created {exc['category']} exception with {exc['priority']} priority.",
                    metadata={"settlement_id": exc["settlement_id"], "payment_id": exc["payment_id"]},
                )

            # Calculate counts
            auto_matches = sum(1 for r in batch_result.results if r.match_status == MatchStatus.AUTO_MATCH)
            exceptions_count = len(inserted_exceptions)
            completed_time = datetime.now(timezone.utc)

            counts = {
                "total_payments": len(dataset.payments),
                "total_settlements": len(dataset.settlements),
                "total_bank_credits": len(dataset.bank_credits),
                "total_refunds": len(dataset.refunds),
                "auto_match_count": auto_matches,
                "exception_count": exceptions_count,
            }

            self.batch_repo.update_batch_status(
                conn,
                batch_id=batch_id,
                status="COMPLETED",
                completed_at=completed_time,
                counts=counts,
            )

            self.audit_repo.insert_audit_event(
                conn,
                batch_id=batch_id,
                event_type="BATCH_COMPLETED",
                entity_type="BATCH",
                entity_id=batch_id,
                action="COMPLETE_BATCH",
                reason=f"Reconciliation completed successfully ({auto_matches} auto-matches, {exceptions_count} exceptions).",
                metadata=counts,
            )

        return BatchResultSummary(
            batch_id=batch_id,
            batch_number=batch_number,
            disposition=BatchDisposition.PROCESSED_NEW,
            status="COMPLETED",
            total_payments=len(dataset.payments),
            total_settlements=len(dataset.settlements),
            total_bank_credits=len(dataset.bank_credits),
            total_refunds=len(dataset.refunds),
            auto_match_count=auto_matches,
            exception_count=exceptions_count,
            exceptions=inserted_exceptions,
        )
