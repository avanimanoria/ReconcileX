"""FastAPI dependency injection providers."""

from typing import Generator
import psycopg
from fastapi import Depends

from backend.app.db.connection import get_connection
from backend.app.db.repositories.audit_repo import AuditRepository
from backend.app.db.repositories.batch_repo import BatchRepository
from backend.app.db.repositories.recon_repo import ReconRepository
from backend.app.services.batch_service import BatchService
from backend.app.services.exception_service import ExceptionService


def get_db() -> Generator[psycopg.Connection, None, None]:
    """Yield a managed PostgreSQL connection with automatic closure."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_batch_repo() -> BatchRepository:
    return BatchRepository()


def get_recon_repo() -> ReconRepository:
    return ReconRepository()


def get_audit_repo() -> AuditRepository:
    return AuditRepository()


def get_batch_service(
    batch_repo: BatchRepository = Depends(get_batch_repo),
    recon_repo: ReconRepository = Depends(get_recon_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> BatchService:
    return BatchService(batch_repo=batch_repo, recon_repo=recon_repo, audit_repo=audit_repo)


def get_exception_service(
    recon_repo: ReconRepository = Depends(get_recon_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> ExceptionService:
    return ExceptionService(recon_repo=recon_repo, audit_repo=audit_repo)


def get_ai_explainer_service(
    recon_repo: ReconRepository = Depends(get_recon_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> "GroundedExceptionExplainerService":
    from backend.app.ai.service import GroundedExceptionExplainerService
    return GroundedExceptionExplainerService(recon_repo=recon_repo, audit_repo=audit_repo)


def get_advisory_narration_service(
    recon_repo: ReconRepository = Depends(get_recon_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> "AdvisoryNarrationService":
    from backend.app.ai.narration_extractor import AdvisoryNarrationService
    return AdvisoryNarrationService(recon_repo=recon_repo, audit_repo=audit_repo)


def get_metrics_service() -> "MetricsService":
    from backend.app.services.metrics_service import MetricsService
    return MetricsService()


