from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import get_alert_service, require_permission
from backend.api.responses import (
    AlertDetail,
    CustomerContext,
    AlertQueuePage,
    AlertStatusResult,
    DecisionResult,
    MySummary,
)
from backend.api_schemas import AlertDecisionRequest, AlertStatusUpdate
from backend.repositories.audit_repository import AuditLogRepository
from backend.repositories.customer_view_log import CustomerViewLogFailed
from backend.services.alert_workflow import WorkflowError
from backend.services.alert_service import (
    AlertNotFound,
    AlertService,
    CustomerContextForbidden,
    InvalidAlertUpdate,
)
from backend.services.auth_service import AuthenticatedUser


router = APIRouter()


@router.get("/alerts/rule-codes")
def list_alert_rule_codes(
    _user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> list[str]:
    try:
        return service.list_rule_codes()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load alert filters.") from exc


@router.get("/alerts/queue", response_model=AlertQueuePage)
def alert_queue(
    status: Literal["new", "in_review"] = "new",
    severity: Literal["low", "medium", "high"] | None = None,
    rule_code: str | None = Query(default=None, max_length=10),
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, max_length=100),
    sort: Literal["severity_age", "waiting"] = "severity_age",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> Any:
    try:
        return service.alert_queue(
            status=status,
            severity=severity,
            rule_code=rule_code,
            date_from=date_from,
            date_to=date_to,
            q=q,
            sort=sort,
            offset=offset,
            limit=limit,
        )
    except InvalidAlertUpdate as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load the alert queue.") from exc


@router.get("/dashboard/my-summary", response_model=MySummary)
def my_summary(
    user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> Any:
    try:
        return service.my_summary(user.user_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load your summary.") from exc


@router.get("/alerts")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    rule_code: str | None = None,
    customer_no: str | None = Query(default=None, min_length=1, max_length=20),
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    include_counts: bool = False,
    _user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> dict[str, Any]:
    try:
        return service.list_alerts(
            status=status,
            severity=severity,
            rule_code=rule_code,
            customer_no=customer_no,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
            include_counts=include_counts,
        )
    except InvalidAlertUpdate as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load alerts.") from exc


@router.get("/alerts/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: int,
    user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> Any:
    try:
        return service.get_alert(alert_id, user.permissions)
    except AlertNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load alert.") from exc


@router.get("/alerts/{alert_id}/customer-context", response_model=CustomerContext)
def alert_customer_context(
    alert_id: int,
    user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> Any:
    try:
        return service.customer_context(alert_id, user)
    except AlertNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CustomerContextForbidden as exc:
        AuditLogRepository().write_event(
            action="ACCESS_DENIED",
            entity_type="alert_customer_context",
            entity_id=str(alert_id),
            actor_id=user.user_id,
            details={"username": user.username},
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CustomerViewLogFailed as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail="Could not load the customer information."
        ) from exc


def _workflow_error(
    exc: WorkflowError, user: AuthenticatedUser, target: str, *, include_alert_id: bool
) -> JSONResponse:
    if exc.access_denied:
        AuditLogRepository().write_event(
            action="ACCESS_DENIED",
            entity_type="alert_status",
            entity_id=target,
            actor_id=user.user_id,
            details={"username": user.username, "target_status": target},
        )
    content: dict[str, Any] = {"detail": exc.detail}
    if include_alert_id and exc.alert_id is not None:
        content["alert_id"] = exc.alert_id
    return JSONResponse(status_code=exc.status_code, content=content)


@router.post("/alerts/decisions", response_model=DecisionResult)
def decide_alerts(
    request: AlertDecisionRequest,
    user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> Any:
    try:
        return service.decide(request.alert_ids, request.status, request.note, user)
    except WorkflowError as exc:
        return _workflow_error(exc, user, request.status, include_alert_id=True)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not save the decision.") from exc


@router.patch("/alerts/{alert_id}/status", response_model=AlertStatusResult)
def update_alert_status(
    alert_id: int,
    update: AlertStatusUpdate,
    user: AuthenticatedUser = Depends(require_permission("alert:view")),
    service: AlertService = Depends(get_alert_service),
) -> Any:
    try:
        return service.update_status(alert_id, update.status, update.note, user)
    except WorkflowError as exc:
        return _workflow_error(exc, user, update.status, include_alert_id=False)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not update alert.") from exc
