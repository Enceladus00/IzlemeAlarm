from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import get_analysis_service, get_demo_service
from backend.services.demo_service import DemoService
from backend.services.analysis_service import AnalysisService


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
    service: AnalysisService = Depends(get_analysis_service),
) -> dict[str, Any]:
    try:
        return service.dashboard_summary()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load dashboard.") from exc


@router.post("/demo/seed")
def seed_demo(
    service: DemoService = Depends(get_demo_service),
) -> dict[str, Any]:
    try:
        return service.seed()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not seed demo data.") from exc
