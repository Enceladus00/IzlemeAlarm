import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import (
    get_analysis_service,
    get_demo_service,
    rate_limited,
    require_permission,
)
from backend.api.responses import (
    DashboardFunnel,
    DashboardSummary,
    RulePerformance,
    SystemOverview,
)
from backend.rate_limit import DEMO_SEED_RATE
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


DASHBOARD_PERIODS = (7, 30, 90)


def dashboard_days(days: int = Query(default=30)) -> int:
    """K3 period selector: 7, 30 or 90 days."""
    if days not in DASHBOARD_PERIODS:
        raise HTTPException(status_code=422, detail="days must be 7, 30 or 90.")
    return days


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    days: int = Depends(dashboard_days),
    _user: AuthenticatedUser = Depends(require_permission("dashboard:view")),
    service: AnalysisService = Depends(get_analysis_service),
) -> Any:
    try:
        return service.dashboard_summary(days)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load dashboard.") from exc


@router.get("/dashboard/funnel", response_model=DashboardFunnel)
def dashboard_funnel(
    days: int = Depends(dashboard_days),
    _user: AuthenticatedUser = Depends(require_permission("dashboard:view")),
    service: AnalysisService = Depends(get_analysis_service),
) -> Any:
    try:
        return service.funnel(days)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load dashboard.") from exc


@router.get("/dashboard/rule-performance", response_model=list[RulePerformance])
def dashboard_rule_performance(
    days: int = Depends(dashboard_days),
    _user: AuthenticatedUser = Depends(require_permission("dashboard:view")),
    service: AnalysisService = Depends(get_analysis_service),
) -> Any:
    try:
        return service.rule_performance(days)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load dashboard.") from exc


@router.get("/admin/system-overview", response_model=SystemOverview)
def system_overview(
    _user: AuthenticatedUser = Depends(require_permission("user:manage")),
    service: AnalysisService = Depends(get_analysis_service),
) -> Any:
    try:
        return service.system_overview()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail="Could not load system overview."
        ) from exc


@router.post("/demo/seed")
def seed_demo(
    use_saved_rules: bool = False,
    user: AuthenticatedUser = Depends(require_permission("upload:create")),
    _rate: None = Depends(rate_limited("demo-seed", DEMO_SEED_RATE)),
    service: DemoService = Depends(get_demo_service),
) -> dict[str, Any]:
    if os.getenv("ENABLE_DEMO_ENDPOINTS", "").lower() != "true":
        raise HTTPException(status_code=404, detail="Demo endpoints are disabled.")
    try:
        return service.seed(user.user_id, use_saved_rules=use_saved_rules)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not seed demo data.") from exc


@router.get("/demo/status")
def demo_status(
    _user: AuthenticatedUser = Depends(require_permission("dashboard:view")),
    service: DemoService = Depends(get_demo_service),
) -> dict[str, Any]:
    try:
        return {
            **service.status(),
            "seed_enabled": os.getenv("ENABLE_DEMO_ENDPOINTS", "").lower() == "true",
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load demo data.") from exc
