"""Reconciliation batch management API routes."""

from pathlib import Path
import tempfile
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
import psycopg

from backend.app.api.deps import get_batch_repo, get_batch_service, get_db, get_recon_repo
from backend.app.api.schemas import (
    BatchResponse,
    ExceptionResponse,
    PaginatedResponse,
    ReconcileResultResponse,
)
from backend.app.db.repositories.batch_repo import BatchRepository
from backend.app.db.repositories.recon_repo import ReconRepository
from backend.app.services.batch_service import (
    BatchAlreadyInProgressError,
    BatchDisposition,
    BatchService,
)

router = APIRouter(prefix="/batches", tags=["Batches"])

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
VALID_BATCH_STATUSES = {"CREATED", "INGESTING", "PROCESSING", "COMPLETED", "FAILED"}
VALID_MATCH_STATUSES = {"AUTO_MATCH", "EXCEPTION"}


def validate_and_read_csv(upload_file: UploadFile, field_name: str) -> bytes:
    """Validate upload filename, extension, non-emptiness, and size constraint."""
    if not upload_file or not upload_file.filename:
        raise HTTPException(
            status_code=422,
            detail=f"Field '{field_name}' must be provided with a non-empty filename.",
        )

    filename = upload_file.filename.lower()
    if not filename.endswith(".csv"):
        raise HTTPException(
            status_code=422,
            detail=f"Field '{field_name}' must be a CSV file with .csv extension (received '{upload_file.filename}').",
        )

    content = upload_file.file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=422,
            detail=f"File '{field_name}' cannot be empty.",
        )

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"File '{field_name}' exceeds maximum allowed size of 10 MB.",
        )

    return content


@router.get("", response_model=PaginatedResponse[BatchResponse], status_code=status.HTTP_200_OK)
def list_batches(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by batch status"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset items"),
    db: psycopg.Connection = Depends(get_db),
    batch_repo: BatchRepository = Depends(get_batch_repo),
) -> PaginatedResponse[BatchResponse]:
    """Retrieve paginated list of batches ordered newest first."""
    if status_filter:
        status_upper = status_filter.upper()
        if status_upper not in VALID_BATCH_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid batch status filter '{status_filter}'. Allowed: {sorted(list(VALID_BATCH_STATUSES))}",
            )
        status_filter = status_upper

    items, total = batch_repo.list_batches(db, status=status_filter, limit=limit, offset=offset)
    return PaginatedResponse[BatchResponse](
        items=[BatchResponse.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_batch(
    payments_file: UploadFile = File(..., description="Payments CSV file"),
    settlements_file: UploadFile = File(..., description="Settlements CSV file"),
    bank_credits_file: UploadFile = File(..., description="Bank credits CSV file"),
    refunds_file: UploadFile = File(..., description="Refunds CSV file"),
    batch_number: Optional[str] = Form(None, description="Optional custom batch number"),
    db: psycopg.Connection = Depends(get_db),
    batch_service: BatchService = Depends(get_batch_service),
    batch_repo: BatchRepository = Depends(get_batch_repo),
):
    """Upload four required CSV files, reconcile, and persist batch."""
    p_bytes = validate_and_read_csv(payments_file, "payments_file")
    s_bytes = validate_and_read_csv(settlements_file, "settlements_file")
    b_bytes = validate_and_read_csv(bank_credits_file, "bank_credits_file")
    r_bytes = validate_and_read_csv(refunds_file, "refunds_file")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "payments.csv").write_bytes(p_bytes)
        (tmp_path / "settlements.csv").write_bytes(s_bytes)
        (tmp_path / "bank_credits.csv").write_bytes(b_bytes)
        (tmp_path / "refunds.csv").write_bytes(r_bytes)

        try:
            summary = batch_service.process_batch(
                conn=db,
                data_dir=tmp_path,
                payments_bytes=p_bytes,
                settlements_bytes=s_bytes,
                bank_credits_bytes=b_bytes,
                refunds_bytes=r_bytes,
                batch_number=batch_number,
            )
        except BatchAlreadyInProgressError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    batch_data = batch_repo.find_by_id(db, summary.batch_id)
    if not batch_data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load created batch.")

    batch_data["disposition"] = summary.disposition.value
    response_model = BatchResponse.model_validate(batch_data)

    if summary.disposition == BatchDisposition.PROCESSED_NEW:
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=response_model.model_dump(mode="json"))
    elif summary.disposition == BatchDisposition.ALREADY_COMPLETED:
        return JSONResponse(status_code=status.HTTP_200_OK, content=response_model.model_dump(mode="json"))
    elif summary.disposition == BatchDisposition.PREVIOUSLY_FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "A batch with this exact content hash previously failed and cannot be reprocessed.",
                "batch": response_model.model_dump(mode="json"),
            },
        )


@router.get("/{batch_id}", response_model=BatchResponse, status_code=status.HTTP_200_OK)
def get_batch(
    batch_id: UUID,
    db: psycopg.Connection = Depends(get_db),
    batch_repo: BatchRepository = Depends(get_batch_repo),
) -> BatchResponse:
    """Retrieve details of a single reconciliation batch."""
    batch = batch_repo.find_by_id(db, str(batch_id))
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch '{batch_id}' not found.")
    return BatchResponse.model_validate(batch)


@router.get(
    "/{batch_id}/results",
    response_model=PaginatedResponse[ReconcileResultResponse],
    status_code=status.HTTP_200_OK,
)
def list_batch_results(
    batch_id: UUID,
    match_status: Optional[str] = Query(None, description="Filter by AUTO_MATCH or EXCEPTION"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset items"),
    db: psycopg.Connection = Depends(get_db),
    batch_repo: BatchRepository = Depends(get_batch_repo),
    recon_repo: ReconRepository = Depends(get_recon_repo),
) -> PaginatedResponse[ReconcileResultResponse]:
    """Retrieve paginated reconciliation results for a batch."""
    batch = batch_repo.find_by_id(db, str(batch_id))
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch '{batch_id}' not found.")

    if match_status:
        ms_upper = match_status.upper()
        if ms_upper not in VALID_MATCH_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid match_status filter '{match_status}'. Allowed: {sorted(list(VALID_MATCH_STATUSES))}",
            )
        match_status = ms_upper

    items, total = recon_repo.list_results_by_batch(
        db, batch_id=str(batch_id), match_status=match_status, limit=limit, offset=offset
    )

    return PaginatedResponse[ReconcileResultResponse](
        items=[ReconcileResultResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{batch_id}/exceptions",
    response_model=PaginatedResponse[ExceptionResponse],
    status_code=status.HTTP_200_OK,
)
def list_batch_exceptions(
    batch_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by exception status"),
    priority: Optional[str] = Query(None, description="Filter by priority (CRITICAL, HIGH, MEDIUM, LOW)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset items"),
    db: psycopg.Connection = Depends(get_db),
    batch_repo: BatchRepository = Depends(get_batch_repo),
    recon_repo: ReconRepository = Depends(get_recon_repo),
) -> PaginatedResponse[ExceptionResponse]:
    """Retrieve paginated exceptions for a batch with optional status, priority, and category filters."""
    batch = batch_repo.find_by_id(db, str(batch_id))
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch '{batch_id}' not found.")

    items, total = recon_repo.list_exceptions_by_batch(
        db,
        batch_id=str(batch_id),
        status=status_filter.upper() if status_filter else None,
        priority=priority.upper() if priority else None,
        category=category.upper() if category else None,
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse[ExceptionResponse](
        items=[ExceptionResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
