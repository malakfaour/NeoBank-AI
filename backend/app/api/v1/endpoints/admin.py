import asyncio
from functools import partial
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.core.storage import get_presigned_url
from app.db.session import get_db
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.transaction import Transaction
from app.models.transaction_audit_log import TransactionAuditLog
from app.models.user import KYCStatus, User, UserRole
from app.schemas.admin_kyc import (
    AdminKYCDecisionResponse,
    AdminKYCQueueItem,
    AdminKYCRejectRequest,
)
from app.schemas.audit_log import AuditLogEntry, AuditTrailResponse
from app.schemas.user import CurrentUser
from app.services.notifications import notify

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


@router.get("/kyc/queue", response_model=list[AdminKYCQueueItem])
async def get_kyc_queue(
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KYCRecord, User)
        .join(User, User.id == KYCRecord.user_id)
        .where(KYCRecord.status == KYCRecordStatus.flagged)
        .order_by(KYCRecord.id.asc())
    )
    rows = result.all()
    loop = asyncio.get_running_loop()
    items: list[AdminKYCQueueItem] = []
    for record, user in rows:
        selfie_presigned_url = None
        id_photo_presigned_url = None
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
        items.append(
            AdminKYCQueueItem(
                id=record.id,
                user_id=user.id,
                full_name=user.full_name,
                status=record.status,
                match_score=record.match_score,
                liveness_score=record.liveness_score,
                rejection_reason=record.rejection_reason,
                reviewed_at=record.reviewed_at,
                reviewed_by=record.reviewed_by,
                selfie_url=record.selfie_url,
                id_photo_url=record.id_photo_url,
                selfie_presigned_url=selfie_presigned_url,
                id_photo_presigned_url=id_photo_presigned_url,
            )
        )
    return items


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
    return await _build_decision_response(
        db,
        record=record,
        user=user,
        notification_type="KYC_REJECTED",
    )


@router.get("/transactions/{transaction_id}/audit-trail", response_model=AuditTrailResponse)
async def get_transaction_audit_trail(
    transaction_id: int,
    current_user: CurrentUser = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    transaction_result = await db.execute(
        select(Transaction.id).where(Transaction.id == transaction_id)
    )
    if transaction_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    audit_result = await db.execute(
        select(TransactionAuditLog)
        .where(TransactionAuditLog.transaction_id == transaction_id)
        .order_by(TransactionAuditLog.timestamp.asc())
    )
    entries = audit_result.scalars().all()

    return AuditTrailResponse(
        transaction_id=transaction_id,
        entries=[
            AuditLogEntry(
                id=entry.id,
                action=entry.action,
                actor_id=entry.actor_id,
                timestamp=entry.timestamp,
                metadata=entry.event_metadata,
            )
            for entry in entries
        ],
    )
