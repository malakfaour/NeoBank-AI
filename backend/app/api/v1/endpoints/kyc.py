import asyncio
from functools import partial
from time import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_role
from app.core.storage import get_presigned_url, upload_file
from app.db.session import get_async_db
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import User, UserRole
from app.schemas.kyc import (
    KYCDocumentAccessResponse,
    KYCStatusResponse,
    KYCStatusUpdateRequest,
    KYCUploadResponse,
)
from app.schemas.user import CurrentUser

router = APIRouter()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/jpg"}
KYC_BUCKET_NAME = "neobank-kyc"
SSE_S3_EXTRA_ARGS = {"ServerSideEncryption": "AES256"}


def _validate_image_upload(upload: UploadFile, field_name: str) -> None:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a JPEG or PNG image",
        )


def _build_kyc_key(user_id: int, prefix: str, timestamp: int) -> str:
    return f"{user_id}/{prefix}_{timestamp}.jpg"


@router.get("/status", response_model=KYCStatusResponse, summary="Get the current user's KYC status")
async def get_kyc_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return KYCStatusResponse(user_id=user.id, kyc_status=user.kyc_status)


@router.post(
    "/upload",
    response_model=KYCUploadResponse,
    summary="Upload KYC verification documents",
)
async def upload_kyc_documents(
    selfie: UploadFile = File(...),
    id_photo: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    _validate_image_upload(selfie, "selfie")
    _validate_image_upload(id_photo, "id_photo")

    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    timestamp = int(time())
    selfie_key = _build_kyc_key(user.id, "selfie", timestamp)
    id_photo_key = _build_kyc_key(user.id, "id", timestamp)
    selfie_bytes = await selfie.read()
    id_photo_bytes = await id_photo.read()
    await selfie.close()
    await id_photo.close()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(
            upload_file,
            selfie_bytes,
            selfie_key,
            bucket_name=KYC_BUCKET_NAME,
            extra_args={**SSE_S3_EXTRA_ARGS, "ContentType": selfie.content_type},
        ),
    )
    await loop.run_in_executor(
        None,
        partial(
            upload_file,
            id_photo_bytes,
            id_photo_key,
            bucket_name=KYC_BUCKET_NAME,
            extra_args={**SSE_S3_EXTRA_ARGS, "ContentType": id_photo.content_type},
        ),
    )

    kyc_record = await db.scalar(select(KYCRecord).where(KYCRecord.user_id == user.id))
    if not kyc_record:
        kyc_record = KYCRecord(user_id=user.id)
        db.add(kyc_record)

    kyc_record.selfie_url = selfie_key
    kyc_record.id_photo_url = id_photo_key
    kyc_record.match_score = None
    kyc_record.status = KYCRecordStatus.pending
    kyc_record.reviewed_at = None

    await db.commit()
    await db.refresh(kyc_record)

    return KYCUploadResponse(
        kyc_record_id=kyc_record.id,
        selfie_url=kyc_record.selfie_url,
        id_photo_url=kyc_record.id_photo_url,
        status=kyc_record.status,
    )


@router.get(
    "/{kyc_record_id}/documents",
    response_model=KYCDocumentAccessResponse,
    summary="Get presigned KYC document URLs for a record",
)
async def get_kyc_document_urls(
    kyc_record_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    kyc_record = await db.scalar(select(KYCRecord).where(KYCRecord.id == kyc_record_id))
    if not kyc_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC record not found",
        )

    allowed_roles = {UserRole.admin, UserRole.compliance_officer}
    if kyc_record.user_id != int(current_user.id) and current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    loop = asyncio.get_running_loop()
    selfie_presigned_url = None
    id_photo_presigned_url = None
    if kyc_record.selfie_url:
        selfie_presigned_url = await loop.run_in_executor(
            None,
            partial(get_presigned_url, kyc_record.selfie_url),
        )
    if kyc_record.id_photo_url:
        id_photo_presigned_url = await loop.run_in_executor(
            None,
            partial(get_presigned_url, kyc_record.id_photo_url),
        )

    return KYCDocumentAccessResponse(
        kyc_record_id=kyc_record.id,
        selfie_key=kyc_record.selfie_url,
        id_photo_key=kyc_record.id_photo_url,
        selfie_presigned_url=selfie_presigned_url,
        id_photo_presigned_url=id_photo_presigned_url,
    )


@router.patch("/status", response_model=KYCStatusResponse, summary="Update a user's KYC status")
async def update_kyc_status(
    body: KYCStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.compliance_officer)
    ),
):
    user = await db.scalar(select(User).where(User.id == body.user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.kyc_status = body.status
    await db.commit()
    await db.refresh(user)

    return KYCStatusResponse(user_id=user.id, kyc_status=user.kyc_status)
