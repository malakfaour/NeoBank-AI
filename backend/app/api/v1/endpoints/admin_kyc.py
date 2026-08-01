from datetime import datetime, timezone
import asyncio
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.core.storage import get_presigned_url
from app.db.session import get_db
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User, UserRole
from app.schemas.admin_kyc import (
    AdminKYCDecisionResponse,
    AdminKYCQueueItem,
    AdminKYCQueueResponse,
    AdminKYCRejectRequest,
)
from app.schemas import CurrentUser
from app.services.audit_log import append_kyc_audit
from app.services.notifications import notify
from app.utils.transaction_query_utils import compute_total_pages

router = APIRouter(prefix="/admin", tags=["admin"])
async def _get_kyc_record_or_404(db: AsyncSession, kyc_record_id: int) -> KYCRecord:
    record = await db.scalar(select(KYCRecord).where(KYCRecord.id == kyc_record_id))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KYC record not found")
    return record


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _build_decision_response(
    db: AsyncSession,
    *,
    record: KYCRecord,
    user: User,
    notification_type: str,
) -> AdminKYCDecisionResponse:
    await db.commit()
    await db.refresh(record)
    await db.refresh(user)
    await notify(
        user_id=user.id,
        notification_type=notification_type,
        metadata={
            "reason": record.rejection_reason,
            "match_score": record.match_score,
            "liveness_score": record.liveness_score,
            "full_name": user.full_name,
        },
    )
    return AdminKYCDecisionResponse(
        kyc_record_id=record.id,
        user_id=user.id,
        status=record.status,
        user_kyc_status=user.kyc_status,
        rejection_reason=record.rejection_reason,
        reviewed_at=record.reviewed_at,
        reviewed_by=record.reviewed_by,
    )


@router.get("/kyc/queue", response_model=AdminKYCQueueResponse)
async def get_kyc_queue(
    status_filter: str = Query(default=KYCRecordStatus.flagged.value, alias="status"),
    date_from: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    if status_filter == "needs_review":
        filters = [
            KYCRecord.is_submitted.is_(True),
            KYCRecord.status.in_([KYCRecordStatus.flagged, KYCRecordStatus.rejected]),
            KYCRecord.reviewed_by.is_(None),
        ]
    else:
        try:
            status_value = KYCRecordStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid KYC status filter") from exc
        filters = [
            KYCRecord.is_submitted.is_(True),
            KYCRecord.status == status_value,
        ]
    if date_from is not None:
        filters.append(KYCRecord.created_at >= date_from)

    total = await db.scalar(
        select(func.count()).select_from(KYCRecord).where(*filters)
    )
    result = await db.execute(
        select(KYCRecord, User)
        .join(User, User.id == KYCRecord.user_id)
        .where(*filters)
        .order_by(KYCRecord.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    loop = asyncio.get_running_loop()
    items: list[AdminKYCQueueItem] = []
    for record, user in rows:
        selfie_presigned_url = None
        id_photo_presigned_url = None
        back_id_photo_presigned_url = None
        if record.selfie_url:
            selfie_presigned_url = await loop.run_in_executor(
                None,
                partial(get_presigned_url, record.selfie_url),
            )
        if record.id_photo_url:
            id_photo_presigned_url = await loop.run_in_executor(
                None,
                partial(get_presigned_url, record.id_photo_url),
            )
        if record.back_id_photo_url:
            back_id_photo_presigned_url = await loop.run_in_executor(
                None,
                partial(get_presigned_url, record.back_id_photo_url),
            )
        profile_data = dict(record.profile_data or {})
        if profile_data.get("identification_number"):
            number = str(profile_data["identification_number"])
            profile_data["identification_number"] = f"{'*' * max(len(number) - 4, 0)}{number[-4:]}"
        items.append(
            AdminKYCQueueItem(
                id=record.id,
                user_id=user.id,
                full_name=user.full_name,
                status=record.status,
                created_at=record.created_at,
                match_score=record.match_score,
                liveness_score=record.liveness_score,
                rejection_reason=record.rejection_reason,
                reviewed_at=record.reviewed_at,
                reviewed_by=record.reviewed_by,
                selfie_url=record.selfie_url,
                id_photo_url=record.id_photo_url,
                document_type=record.document_type,
                selfie_presigned_url=selfie_presigned_url,
                id_photo_presigned_url=id_photo_presigned_url,
                back_id_photo_presigned_url=back_id_photo_presigned_url,
                profile_data=profile_data,
            )
        )
    return AdminKYCQueueResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total or 0,
        total_pages=compute_total_pages(total or 0, page_size),
    )


@router.patch("/kyc/{kyc_record_id}/approve", response_model=AdminKYCDecisionResponse)
async def approve_kyc(
    kyc_record_id: int,
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    record = await _get_kyc_record_or_404(db, kyc_record_id)
    user = await _get_user_or_404(db, record.user_id)
    record.status = KYCRecordStatus.approved
    record.rejection_reason = None
    record.reviewed_at = datetime.now(timezone.utc)
    record.reviewed_by = int(current_user.id)
    user.kyc_status = KYCStatus.approved
    await append_kyc_audit(
        db,
        kyc_record_id=record.id,
        action="kyc_approved",
        actor_id=int(current_user.id),
    )
    return await _build_decision_response(
        db,
        record=record,
        user=user,
        notification_type="KYC_APPROVED",
    )


@router.patch("/kyc/{kyc_record_id}/reject", response_model=AdminKYCDecisionResponse)
async def reject_kyc(
    kyc_record_id: int,
    body: AdminKYCRejectRequest,
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    record = await _get_kyc_record_or_404(db, kyc_record_id)
    user = await _get_user_or_404(db, record.user_id)
    record.status = KYCRecordStatus.rejected
    record.rejection_reason = body.rejection_reason
    record.reviewed_at = datetime.now(timezone.utc)
    record.reviewed_by = int(current_user.id)
    user.kyc_status = KYCStatus.rejected
    await append_kyc_audit(
        db,
        kyc_record_id=record.id,
        action="kyc_rejected",
        actor_id=int(current_user.id),
        metadata={"rejection_reason": body.rejection_reason},
    )
    return await _build_decision_response(
        db,
        record=record,
        user=user,
        notification_type="KYC_REJECTED",
    )


@router.post("/kyc/{kyc_record_id}/request-resubmit", response_model=AdminKYCDecisionResponse)
async def request_kyc_resubmit(
    kyc_record_id: int,
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    record = await _get_kyc_record_or_404(db, kyc_record_id)
    user = await _get_user_or_404(db, record.user_id)
    record.status = KYCRecordStatus.rejected
    record.rejection_reason = "resubmit_requested"
    record.reviewed_at = datetime.now(timezone.utc)
    record.reviewed_by = int(current_user.id)
    user.kyc_status = KYCStatus.rejected
    await append_kyc_audit(
        db,
        kyc_record_id=record.id,
        action="kyc_resubmit_requested",
        actor_id=int(current_user.id),
    )
    return await _build_decision_response(
        db,
        record=record,
        user=user,
        notification_type="KYC_REJECTED",
    )
