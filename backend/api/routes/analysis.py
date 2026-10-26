import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import (
    get_analysis_service,
    get_demo_service,
    require_permission,
)
from backend.services.demo_service import DemoService
from backend.services.analysis_service import AnalysisService
from backend.services.auth_service import AuthenticatedUser


router = APIRouter()


@router.get("/health")
def health_check(
    service: AnalysisService = Depends(get_analysis_service),
) -> dict[str, str]:
    try:
        return service.check_health()
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc


@router.get("/dashboard/summary")
def dashboard_summary(
    _user: AuthenticatedUser = Depends(require_permission("dashboard:view")),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict[str, Any]:
    try:
        return service.dashboard_summary()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load dashboard.") from exc


@router.post("/demo/seed")
def seed_demo(
    user: AuthenticatedUser = Depends(require_permission("upload:create")),
    service: DemoService = Depends(get_demo_service),
) -> dict[str, Any]:
    if os.getenv("ENABLE_DEMO_ENDPOINTS", "").lower() != "true":
        raise HTTPException(status_code=404, detail="Demo endpoints are disabled.")
    try:
        return service.seed(user.user_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not seed demo data.") from exc
