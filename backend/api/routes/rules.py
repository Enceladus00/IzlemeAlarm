from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import (
    get_detection_service,
    get_rule_service,
    require_permission,
)
from backend.api.responses import RuleHistoryEntry, RuleView
from backend.api_schemas import RuleUpdate
from backend.services.detection_service import DetectionService
from backend.services.rule_service import (
    InvalidRuleThresholds,
    RuleNotFound,
    RuleService,
)
from backend.services.auth_service import AuthenticatedUser


router = APIRouter()


@router.get("/rules")
def list_rules(
    _user: AuthenticatedUser = Depends(require_permission("rule:view")),
    service: RuleService = Depends(get_rule_service),
) -> list[dict[str, Any]]:
    try:
        return service.list_rules()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load rules.") from exc


@router.get("/rules/{rule_code}/history", response_model=list[RuleHistoryEntry])
def rule_history(
    rule_code: str,
    limit: int = Query(default=50, ge=1, le=200),
    _user: AuthenticatedUser = Depends(require_permission("rule:view")),
    service: RuleService = Depends(get_rule_service),
) -> Any:
    try:
        return service.rule_history(rule_code, limit)
    except RuleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load rule history.") from exc


@router.put("/rules/{rule_code}", response_model=RuleView)
def update_rule(
    rule_code: str,
    update: RuleUpdate,
    user: AuthenticatedUser = Depends(require_permission("rule:edit")),
    service: RuleService = Depends(get_rule_service),
) -> Any:
    try:
        return service.update_rule(
            rule_code,
            update.thresholds,
            update.is_active,
            user.user_id,
            update.weight,
            update.reason,
        )
    except RuleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidRuleThresholds as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not save rule.") from exc


@router.post("/rules/evaluate")
def run_rules(
    user: AuthenticatedUser = Depends(require_permission("rule:edit")),
    service: DetectionService = Depends(get_detection_service),
) -> dict[str, int]:
    try:
        return {"created_alerts": service.evaluate(actor_id=user.user_id)}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Rule evaluation failed.") from exc
