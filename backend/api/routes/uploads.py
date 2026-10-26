from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile

from backend.api.dependencies import get_upload_service, require_permission
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


@router.get("/uploads/{batch_id}")
def get_upload(
    batch_id: int,
    _user: AuthenticatedUser = Depends(require_permission("upload:view")),
    service: UploadService = Depends(get_upload_service),
) -> dict[str, Any]:
    return service.get_batch(batch_id)
