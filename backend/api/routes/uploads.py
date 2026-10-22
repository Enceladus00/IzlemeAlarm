from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile

from backend.api.dependencies import get_upload_service
from backend.services.upload_service import UploadService


router = APIRouter()


@router.post("/uploads")
async def upload_csv(
    entity: str = Query(pattern="^(customer|account|transaction)$"),
    file: UploadFile = File(...),
    service: UploadService = Depends(get_upload_service),
) -> dict[str, Any]:
    return await service.upload(entity, file)


@router.get("/uploads/{batch_id}")
def get_upload(
    batch_id: int,
    service: UploadService = Depends(get_upload_service),
) -> dict[str, Any]:
    return service.get_batch(batch_id)
