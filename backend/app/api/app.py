"""FastAPI application factory and middleware configuration."""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.routes import audit, batches, exceptions, health, metrics
from backend.app.db.connection import get_safe_database_name
from backend.app.services.batch_service import BatchAlreadyInProgressError
from backend.app.services.exception_service import (
    ExceptionNotFoundError,
    InvalidStateTransitionError,
)

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan context."""
    db_name = get_safe_database_name()
    logger.info("Database target selected: %s", db_name)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="ReconcileX Financial Reconciliation Engine API",
        description="Deterministic financial reconciliation persistence and immutable audit workflow API.",
        version="1.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # In production, configure allowed origins via environment or deployment configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    # Register API Routers
    application.include_router(health.router)
    application.include_router(batches.router)
    application.include_router(exceptions.router)
    application.include_router(audit.router)
    application.include_router(metrics.router)


    # Register Domain Exception Handlers
    @application.exception_handler(InvalidStateTransitionError)
    async def invalid_state_transition_handler(request: Request, exc: InvalidStateTransitionError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @application.exception_handler(BatchAlreadyInProgressError)
    async def batch_already_in_progress_handler(request: Request, exc: BatchAlreadyInProgressError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @application.exception_handler(ExceptionNotFoundError)
    async def exception_not_found_handler(request: Request, exc: ExceptionNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    return application


app = create_app()
