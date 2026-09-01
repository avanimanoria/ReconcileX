"""Reconciliation exceptions workflow and management API routes."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
import psycopg

from backend.app.api.deps import get_db, get_exception_service
from backend.app.api.schemas import ExceptionDetailResponse, ExceptionPatchRequest
from backend.app.services.exception_service import (
    ExceptionNotFoundError,
    ExceptionService,
    InvalidStateTransitionError,
)

router = APIRouter(prefix="/exceptions", tags=["Exceptions"])


@router.get("/{exception_id}", response_model=ExceptionDetailResponse, status_code=status.HTTP_200_OK)
def get_exception(
    exception_id: UUID,
    db: psycopg.Connection = Depends(get_db),
    exc_service: ExceptionService = Depends(get_exception_service),
) -> ExceptionDetailResponse:
    """Retrieve detailed information and financial evidence for a specific exception."""
    try:
        exc = exc_service.get_exception(db, str(exception_id))
    except ExceptionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return ExceptionDetailResponse.model_validate(exc)


@router.patch("/{exception_id}", response_model=ExceptionDetailResponse, status_code=status.HTTP_200_OK)
def update_exception(
    exception_id: UUID,
    patch_req: ExceptionPatchRequest,
    db: psycopg.Connection = Depends(get_db),
    exc_service: ExceptionService = Depends(get_exception_service),
) -> ExceptionDetailResponse:
    """Perform human-directed assignment or lifecycle state transition on an exception."""
    exc_id_str = str(exception_id)

    # 1. Handle assignment update if requested
    if patch_req.assigned_to is not None:
        try:
            exc_service.assign_exception(
                conn=db,
                exception_id=exc_id_str,
                assigned_to=patch_req.assigned_to,
                actor=patch_req.actor,
            )
        except ExceptionNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # 2. Handle lifecycle status transition if requested
    if patch_req.status is not None:
        try:
            exc_service.transition_status(
                conn=db,
                exception_id=exc_id_str,
                target_status=patch_req.status,
                actor=patch_req.actor,
                reason=patch_req.resolution_reason,
            )
        except ExceptionNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except InvalidStateTransitionError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    # Fetch final updated state
    updated_exc = exc_service.get_exception(db, exc_id_str)
    return ExceptionDetailResponse.model_validate(updated_exc)
