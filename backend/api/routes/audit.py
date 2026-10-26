from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import get_audit_service, require_permission
from backend.services.audit_service import AuditService
from backend.services.auth_service import AuthenticatedUser


router = APIRouter(tags=["audit"])


@router.get("/audit-log")
def list_audit_log(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _actor: AuthenticatedUser = Depends(require_permission("audit:view")),
    service: AuditService = Depends(get_audit_service),
) -> dict[str, Any]:
    try:
        return service.list_events(offset, limit)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load audit log.") from exc
