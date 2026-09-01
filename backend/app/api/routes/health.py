"""Health check endpoint."""

from fastapi import APIRouter, Depends, status
import psycopg

from backend.app.api.deps import get_db
from backend.app.api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def health_check(db: psycopg.Connection = Depends(get_db)) -> HealthResponse:
    """Check service health and database connectivity."""
    db_status = "connected"
    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1;")
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="healthy",
        engine_version="v1.1-deterministic",
        database=db_status,
    )
