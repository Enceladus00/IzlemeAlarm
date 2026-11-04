from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile

from backend.api.dependencies import get_upload_service, require_permission
from backend.api.responses import UploadReport, UploadSummary
from backend.services.upload_service import UploadService
from backend.services.auth_service import AuthenticatedUser


router = APIRouter()


@router.post("/uploads")
async def upload_csv(
    entity: str = Query(pattern="^(customer|account|transaction)$"),
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(require_permission("upload:create")),
    service: UploadService = Depends(get_upload_service),
) -> dict[str, Any]:
    return await service.upload(entity, file, user.user_id)


@router.get("/uploads", response_model=list[UploadSummary])
def list_uploads(
    entity: str | None = Query(default=None, pattern="^(customer|account|transaction)$"),
    limit: int = Query(default=20, ge=1, le=100),
    _user: AuthenticatedUser = Depends(require_permission("upload:view")),
    service: UploadService = Depends(get_upload_service),
) -> Any:
    return service.list_batches(entity, limit)


@router.get("/uploads/{batch_id}", response_model=UploadReport)
def get_upload(
    batch_id: int,
    user: AuthenticatedUser = Depends(require_permission("upload:view")),
    service: UploadService = Depends(get_upload_service),
) -> Any:
    return service.get_batch(batch_id, user.user_id)
