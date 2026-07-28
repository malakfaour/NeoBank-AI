import asyncio
from datetime import datetime, timezone
from functools import partial
from time import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_role
from app.core.storage import get_presigned_url, upload_file
from app.db.session import get_async_db
from app.models.kyc_record import KYCDocumentType, KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User, UserRole
from app.schemas.kyc import (
    KYCDocumentAccessResponse,
    KYCConsentRequest,
    KYCDraftUpdateRequest,
    KYCProfileData,
    KYCProfileResponse,
    KYCStatusResponse,
    KYCStatusUpdateRequest,
    KYCUploadResponse,
)
from app.schemas.auth import CurrentUser
from app.services.audit_log import append_kyc_audit
from app.tasks.kyc_tasks import process_kyc

router = APIRouter()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/jpg"}


async def _latest_kyc_record(db: AsyncSession, user_id: int) -> KYCRecord | None:
    return await db.scalar(
        select(KYCRecord)
        .where(KYCRecord.user_id == user_id)
        .order_by(KYCRecord.id.desc())
    )


def _workflow_status(record: KYCRecord) -> str:
    if record.status == KYCRecordStatus.approved:
        return "approved"
    if record.status == KYCRecordStatus.rejected:
        return "rejected"
    if record.is_submitted:
        return "pending"
    return "in_progress"


def _profile_response(user: User, record: KYCRecord) -> KYCProfileResponse:
    profile_data = dict(record.profile_data or {})
    if record.is_submitted and profile_data.get("identification_number"):
        value = str(profile_data["identification_number"])
        profile_data["identification_number"] = (
            f"{'*' * max(len(value) - 4, 0)}{value[-4:]}"
        )
    return KYCProfileResponse(
        kyc_record_id=record.id,
        kyc_status=user.kyc_status,
        workflow_status=_workflow_status(record),
        current_step=record.current_step,
        profile_data=KYCProfileData(**profile_data),
        has_front_id=bool(record.id_photo_url),
        has_back_id=bool(record.back_id_photo_url),
        has_selfie=bool(record.selfie_url),
        rejection_reason=record.rejection_reason,
        submitted_at=record.submitted_at,
    )


@router.get("/profile", response_model=KYCProfileResponse)
async def get_kyc_profile(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    record = await _latest_kyc_record(db, user.id)
    if record is None:
        name_parts = user.full_name.split()
        record = KYCRecord(
            user_id=user.id,
            profile_data={
                "first_name": name_parts[0] if name_parts else user.full_name,
                "last_name": name_parts[-1] if len(name_parts) > 1 else None,
            },
            current_step=1,
            is_submitted=False,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
    return _profile_response(user, record)


@router.put("/profile", response_model=KYCProfileResponse)
async def save_kyc_profile(
    body: KYCDraftUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    record = await _latest_kyc_record(db, user.id)
    if record is None:
        record = KYCRecord(user_id=user.id)
        db.add(record)
    if record.is_submitted and record.status != KYCRecordStatus.rejected:
        raise HTTPException(status_code=409, detail="Submitted KYC cannot be edited")
    record.profile_data = body.profile_data.model_dump(mode="json", exclude_none=True)
    record.current_step = body.current_step
    record.is_submitted = False
    await db.commit()
    await db.refresh(record)
    return _profile_response(user, record)


@router.post("/submit", response_model=KYCProfileResponse)
async def submit_kyc_profile(
    body: KYCConsentRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    record = await _latest_kyc_record(db, int(current_user.id))
    if user is None or record is None:
        raise HTTPException(status_code=400, detail="Complete your KYC profile first")
    data = record.profile_data or {}
    required = (
        "first_name", "last_name", "date_of_birth", "place_of_birth",
        "gender", "marital_status", "nationality", "identification_type",
        "identification_number", "id_expiry_date", "country_of_residence",
        "city", "residential_address", "occupation", "source_of_funds",
        "annual_income_usd",
    )
    missing = [field for field in required if data.get(field) in (None, "")]
    if data.get("occupation") == "employee":
        missing.extend(
            field for field in (
                "employer_name", "position", "employment_address", "employer_phone"
            ) if not data.get(field)
        )
    if not (record.id_photo_url and record.back_id_photo_url and record.selfie_url):
        missing.append("identity_documents")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "kyc_required_fields_missing", "fields": sorted(set(missing))},
        )
    if not all(
        (body.terms_accepted, body.information_confirmed, body.privacy_consent)
    ):
        raise HTTPException(
            status_code=422,
            detail={"error": "kyc_consent_required"},
        )
    record.terms_accepted = body.terms_accepted
    record.information_confirmed = body.information_confirmed
    record.privacy_consent = body.privacy_consent
    record.is_submitted = True
    record.submitted_at = datetime.now(timezone.utc)
    record.status = KYCRecordStatus.pending
    record.rejection_reason = None
    record.reviewed_at = None
    record.reviewed_by = None
    user.kyc_status = KYCStatus.pending
    await db.commit()
    await db.refresh(record)
    return _profile_response(user, record)


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
    "/request-manual-review",
    response_model=KYCStatusResponse,
    summary="Escalate a rejected KYC record for manual compliance review",
)
async def request_manual_review(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    kyc_record = await db.scalar(
        select(KYCRecord)
        .where(KYCRecord.user_id == user.id)
        .order_by(KYCRecord.id.desc())
    )
    if not kyc_record or kyc_record.status != KYCRecordStatus.rejected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manual review can only be requested for a rejected verification",
        )

    kyc_record.status = KYCRecordStatus.flagged
    kyc_record.reviewed_at = None
    kyc_record.reviewed_by = None
    user.kyc_status = KYCStatus.flagged
    await append_kyc_audit(
        db,
        kyc_record_id=kyc_record.id,
        action="kyc_manual_review_requested",
        actor_id=user.id,
    )
    await db.refresh(user)

    return KYCStatusResponse(user_id=user.id, kyc_status=user.kyc_status)


@router.post(
    "/upload",
    response_model=KYCUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload KYC verification documents",
)
async def upload_kyc_documents(
    selfie: UploadFile = File(...),
    id_photo: UploadFile = File(...),
    back_id_photo: UploadFile | None = File(default=None),
    document_type: KYCDocumentType = Form(...),
    submit_for_review: bool = Form(default=True),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    _validate_image_upload(selfie, "selfie")
    _validate_image_upload(id_photo, "id_photo")
    if back_id_photo is not None:
        _validate_image_upload(back_id_photo, "back_id_photo")

    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    kyc_record = await db.scalar(select(KYCRecord).where(KYCRecord.user_id == user.id))
    if (
        kyc_record
        and kyc_record.status == KYCRecordStatus.pending
        and kyc_record.is_submitted
        and kyc_record.selfie_url
        and kyc_record.id_photo_url
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="KYC verification is already processing",
        )

    timestamp = int(time())
    selfie_key = _build_kyc_key(user.id, "selfie", timestamp)
    id_photo_key = _build_kyc_key(user.id, "id", timestamp)
    back_id_photo_key = (
        _build_kyc_key(user.id, "id_back", timestamp)
        if back_id_photo is not None else None
    )
    selfie_bytes = await selfie.read()
    id_photo_bytes = await id_photo.read()
    await selfie.close()
    await id_photo.close()
    back_id_photo_bytes = None
    if back_id_photo is not None:
        back_id_photo_bytes = await back_id_photo.read()
        await back_id_photo.close()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(
            upload_file,
            selfie_bytes,
            selfie_key,
            extra_args={"ContentType": selfie.content_type},
        ),
    )
    if back_id_photo_key and back_id_photo_bytes is not None:
        await loop.run_in_executor(
            None,
            partial(
                upload_file,
                back_id_photo_bytes,
                back_id_photo_key,
                extra_args={"ContentType": back_id_photo.content_type},
            ),
        )
    await loop.run_in_executor(
        None,
        partial(
            upload_file,
            id_photo_bytes,
            id_photo_key,
            extra_args={"ContentType": id_photo.content_type},
        ),
    )

    if not kyc_record:
        kyc_record = KYCRecord(user_id=user.id)
        db.add(kyc_record)

    kyc_record.selfie_url = selfie_key
    kyc_record.id_photo_url = id_photo_key
    if back_id_photo_key:
        kyc_record.back_id_photo_url = back_id_photo_key
    kyc_record.document_type = document_type
    kyc_record.match_score = None
    kyc_record.liveness_score = None
    kyc_record.status = KYCRecordStatus.pending
    kyc_record.is_submitted = submit_for_review
    kyc_record.submitted_at = datetime.now(timezone.utc) if submit_for_review else None
    kyc_record.rejection_reason = None
    kyc_record.reviewed_at = None
    kyc_record.reviewed_by = None
    user.kyc_status = KYCStatus.pending
    await db.commit()
    await db.refresh(kyc_record)
    if submit_for_review:
        process_kyc.delay(kyc_record.id)

    return KYCUploadResponse(
        kyc_record_id=kyc_record.id,
        selfie_url=kyc_record.selfie_url,
        id_photo_url=kyc_record.id_photo_url,
        document_type=kyc_record.document_type,
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
    back_id_photo_presigned_url = None
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
    if kyc_record.back_id_photo_url:
        back_id_photo_presigned_url = await loop.run_in_executor(
            None,
            partial(get_presigned_url, kyc_record.back_id_photo_url),
        )

    return KYCDocumentAccessResponse(
        kyc_record_id=kyc_record.id,
        selfie_key=kyc_record.selfie_url,
        id_photo_key=kyc_record.id_photo_url,
        back_id_photo_key=kyc_record.back_id_photo_url,
        selfie_presigned_url=selfie_presigned_url,
        id_photo_presigned_url=id_photo_presigned_url,
        back_id_photo_presigned_url=back_id_photo_presigned_url,
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
