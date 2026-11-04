from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import get_audit_service, require_permission
from backend.api.responses import AuditLogPage
from backend.repositories.audit_query_repository import AuditFilters
from backend.services.audit_service import AuditService
from backend.services.auth_service import AuthenticatedUser


router = APIRouter(tags=["audit"])


@router.get("/audit-log", response_model=AuditLogPage)
def list_audit_log(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    actor_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None, max_length=100),
    exclude_action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=50),
    entity_id: str | None = Query(default=None, max_length=50),
    date_from: date | None = None,
    date_to: date | None = None,
    actor: AuthenticatedUser = Depends(require_permission("audit:view")),
    service: AuditService = Depends(get_audit_service),
) -> Any:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to.")
    filters = AuditFilters(
        actor_id=actor_id,
        action=action,
        exclude_action=exclude_action,
        entity_type=entity_type,
        entity_id=entity_id.strip() if entity_id else None,
        date_from=date_from,
        date_to=date_to,
    )
    try:
        return service.list_events(offset, limit, filters, actor.permissions)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load audit log.") from exc
