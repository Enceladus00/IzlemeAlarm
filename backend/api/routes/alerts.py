from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import get_alert_service
from backend.api_schemas import AlertStatusUpdate
from backend.services.alert_service import (
    AlertNotFound,
    AlertService,
    InvalidAlertUpdate,
)


router = APIRouter()


@router.get("/alerts")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    rule_code: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service: AlertService = Depends(get_alert_service),
) -> dict[str, Any]:
    try:
        return service.list_alerts(
            status=status,
            severity=severity,
            rule_code=rule_code,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        )
    except InvalidAlertUpdate as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load alerts.") from exc


@router.get("/alerts/{alert_id}")
def get_alert(
    alert_id: int,
    service: AlertService = Depends(get_alert_service),
) -> dict[str, Any]:
    try:
        return service.get_alert(alert_id)
    except AlertNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load alert.") from exc


@router.patch("/alerts/{alert_id}/status")
def update_alert_status(
    alert_id: int,
    update: AlertStatusUpdate,
    service: AlertService = Depends(get_alert_service),
) -> dict[str, Any]:
    try:
        return service.update_status(alert_id, update.status, update.note)
    except AlertNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAlertUpdate as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not update alert.") from exc
