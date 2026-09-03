"""API Route for Truthful Metrics & Evaluation Report."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_metrics_service
from backend.app.services.metrics_service import MetricsService

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "/evaluation-report",
    summary="Get truthful system evaluation report",
    description="Returns live or cached evaluation metrics for deterministic reconciliation, AI narration extraction, and human workflow.",
)
def get_evaluation_report(
    force_refresh: bool = Query(False, description="Force on-demand benchmark re-computation"),
    metrics_service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    return metrics_service.get_evaluation_report(force_refresh=force_refresh)
