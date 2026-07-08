import asyncio
from functools import partial
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.core.cache_utils import invalidate_balance_cache
from app.core.storage import get_presigned_url
from app.db.session import get_db
from app.models.exchange_audit_log import ExchangeAuditLog
from app.models.fraud_resolution import FraudResolution, FraudResolutionType
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.model_metrics import ModelMetrics
from app.models.transaction import Transaction, TransactionStatus
from app.models.transaction_audit_log import TransactionAuditLog
from app.models.user import KYCStatus, User, UserRole
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.admin import (
    ComplianceSummaryResponse,
    ExchangeAuditLogItem,
    ExchangeAuditLogPageResponse,
    FlaggedTransactionItem,
    FlaggedTransactionsResponse,
    ModelMetricItem,
    ResolutionCounts,
    ResolveFlagRequest,
    ResolveFlagResponse,
    ReversedAmountByCurrency,
)
from app.schemas.admin_kyc import (
    AdminKYCDecisionResponse,
    AdminKYCQueueItem,
    AdminKYCRejectRequest,
)
from app.schemas.audit_log import AuditLogEntry, AuditTrailResponse
from app.schemas.user import CurrentUser
from app.services.audit_log import append_audit
from app.services.fraud_scoring import FRAUD_FLAG_THRESHOLD
from app.services.notifications import notify
from app.services.wallet_locking import lock_and_credit_wallet
from app.services.wallet_status import WalletClosedError, WalletFrozenError
from app.utils.transaction_query_utils import compute_total_pages, parse_summary_month

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


# =====================================================================
# NBL-111: compliance review of flagged transactions.
#
# Everything below this line is new. The KYC endpoints and
# get_transaction_audit_trail above are the pre-existing file, byte-for-
# byte unchanged -- only new imports were added to the top-of-file import
# block (UserRole reused from the existing app.models.user import rather
# than re-imported from app.schemas.user, to stay consistent with this
# file's own established convention).
# =====================================================================


@router.get("/flagged-transactions", response_model=FlaggedTransactionsResponse)
async def get_flagged_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    NBL-111: paginated list of flagged transactions for compliance review.

    Filter (reopened decision C -> decision b, since rule_triggered turned
    out to be a real column, not the permanent gap it was believed to be
    earlier in this ticket cluster):
      status == "flagged" OR fraud_score > FRAUD_FLAG_THRESHOLD OR rule_triggered
    All three clauses kept deliberately:
      - status == "flagged" catches the scoring-exception fallback path in
        transaction_tasks.py's score_transaction, where fraud_score may
        still be None/unset if scoring itself raised.
      - fraud_score > FRAUD_FLAG_THRESHOLD and rule_triggered == True catch
        the two real, independent flagging signals per DEVATTECH-84/87 --
        a transaction can be ML-flagged, rule-flagged, both, or neither.
    FRAUD_FLAG_THRESHOLD is imported from app/services/fraud_scoring.py
    (never hardcoded), per ENGINEERING_RULES.md Â§7.
    """
    filter_condition = or_(
        Transaction.status == TransactionStatus.flagged,
        Transaction.fraud_score > FRAUD_FLAG_THRESHOLD,
        Transaction.rule_triggered == True,  # noqa: E712 -- SQLAlchemy boolean column comparison
    )

    count_result = await db.execute(
        select(func.count()).select_from(Transaction).where(filter_condition)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Transaction, User)
        .join(User, User.id == Transaction.sender_id)
        .where(filter_condition)
        .order_by(Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    items = [
        FlaggedTransactionItem(
            id=tx.id,
            sender_id=tx.sender_id,
            sender_name=user.full_name,
            sender_email=user.email,
            amount=tx.amount,
            currency=tx.currency.value,
            fraud_score=tx.fraud_score,
            scoring_model=tx.scoring_model,
            rule_triggered=tx.rule_triggered,
            status=tx.status.value,
            created_at=tx.created_at,
        )
        for tx, user in rows
    ]

    return FlaggedTransactionsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.post("/transactions/{transaction_id}/resolve-flag", response_model=ResolveFlagResponse)
async def resolve_flag(
    transaction_id: int,
    payload: ResolveFlagRequest,
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    NBL-111: resolve a flagged transaction.

    legitimate -> Transaction.status = completed.
    confirmed_fraud -> reversal: credit the sender back under a
    SELECT ... FOR UPDATE lock (lock_and_credit_wallet), then
    Transaction.status = reversed.

    NOTE: intentionally NOT gated behind require_action_token. That
    dependency verifies the REQUESTING user's own passcode for their own
    money movement (send_money, pay_bill) -- it has no meaning for a
    compliance officer acting on someone else's transaction. require_role
    is the correct and sufficient gate for this administrative action.

    One resolution per transaction: fraud_resolutions.transaction_id is
    unique. An advisory pre-check returns a clean 409 in the common case;
    the unique constraint (caught as IntegrityError) is the real safety
    net for the race case, same pattern as send_money's idempotency key.
    """
    reviewer_id = int(current_user.id)

    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()

    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if transaction.status != TransactionStatus.flagged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transaction is not currently flagged (status={transaction.status.value})",
        )

    existing_result = await db.execute(
        select(FraudResolution).where(FraudResolution.transaction_id == transaction_id)
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This transaction has already been resolved",
        )

    if payload.resolution == "confirmed_fraud":
        wallet_result = await db.execute(
            select(Wallet).where(
                Wallet.user_id == transaction.sender_id,
                Wallet.currency == WalletCurrency(transaction.currency.value),
            )
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reversal failed: sender wallet not found. Contact engineering.",
            )

        try:
            await lock_and_credit_wallet(db, wallet.id, transaction.amount)
        except (WalletFrozenError, WalletClosedError) as e:
            reason = "wallet_frozen" if isinstance(e, WalletFrozenError) else "wallet_closed"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": reason},
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reversal failed. Contact engineering.",
            )

        transaction.status = TransactionStatus.reversed
        audit_action = "reversed"
    else:
        transaction.status = TransactionStatus.completed
        audit_action = "resolved_legitimate"

    fraud_resolution = FraudResolution(
        transaction_id=transaction_id,
        resolution=FraudResolutionType(payload.resolution),
        reviewer_id=reviewer_id,
        reviewer_note=payload.reviewer_note,
    )
    db.add(fraud_resolution)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This transaction has already been resolved",
        )

    await db.refresh(transaction)
    await db.refresh(fraud_resolution)

    # Best-effort follow-ups: the resolution (and reversal, if any) already
    # succeeded and is durably committed by this point.
    try:
        await append_audit(
            db,
            transaction_id=transaction_id,
            action=audit_action,
            actor_id=reviewer_id,
            metadata={
                "resolution": payload.resolution,
                "reviewer_note": payload.reviewer_note,
            },
        )
    except Exception:
        pass

    if payload.resolution == "confirmed_fraud":
        try:
            await invalidate_balance_cache(transaction.sender_id)
        except Exception:
            pass

    return ResolveFlagResponse(
        transaction_id=transaction_id,
        resolution=payload.resolution,
        new_status=transaction.status.value,
        reviewer_id=reviewer_id,
        resolved_at=fraud_resolution.resolved_at,
    )


@router.get("/exchange/audit", response_model=ExchangeAuditLogPageResponse)
async def get_exchange_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count()).select_from(ExchangeAuditLog)) or 0

    result = await db.execute(
        select(ExchangeAuditLog, User)
        .outerjoin(User, User.id == ExchangeAuditLog.user_id)
        .order_by(ExchangeAuditLog.created_at.desc(), ExchangeAuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    return ExchangeAuditLogPageResponse(
        items=[
            ExchangeAuditLogItem(
                id=audit_log.id,
                exchange_id=audit_log.exchange_id,
                user_id=audit_log.user_id,
                user_full_name=user.full_name if user else None,
                user_email=user.email if user else None,
                from_currency=audit_log.from_currency,
                to_currency=audit_log.to_currency,
                amount=audit_log.amount,
                rate=audit_log.rate,
                converted_amount=audit_log.converted_amount,
                status=audit_log.status,
                provider=audit_log.provider,
                created_at=audit_log.created_at,
            )
            for audit_log, user in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.get("/ml/metrics", response_model=list[ModelMetricItem])
async def get_latest_model_metrics(
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    latest_per_model = (
        select(
            ModelMetrics.model_name.label("model_name"),
            func.max(ModelMetrics.trained_at).label("latest_trained_at"),
        )
        .group_by(ModelMetrics.model_name)
        .subquery()
    )

    result = await db.execute(
        select(ModelMetrics)
        .join(
            latest_per_model,
            (ModelMetrics.model_name == latest_per_model.c.model_name)
            & (ModelMetrics.trained_at == latest_per_model.c.latest_trained_at),
        )
        .order_by(ModelMetrics.model_name.asc())
    )

    return [
        ModelMetricItem(
            model_name=row.model_name,
            mae=row.mae,
            trained_at=row.trained_at,
        )
        for row in result.scalars().all()
    ]


@router.get("/reports/summary", response_model=ComplianceSummaryResponse)
async def get_compliance_summary(
    month: str = Query(..., description="Format YYYY-MM, e.g. 2026-07"),
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    try:
        year, month_num = parse_summary_month(month)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month must be in YYYY-MM format",
        )

    month_start = date(year, month_num, 1)
    month_end = date(year + 1, 1, 1) if month_num == 12 else date(year, month_num + 1, 1)

    total_result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.created_at >= month_start, Transaction.created_at < month_end)
    )
    total_transactions_created = total_result.scalar_one()

    flagged_result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.created_at >= month_start,
            Transaction.created_at < month_end,
            Transaction.status == TransactionStatus.flagged,
        )
    )
    currently_flagged_from_month = flagged_result.scalar_one()

    resolutions_result = await db.execute(
        select(FraudResolution.resolution, func.count())
        .where(FraudResolution.resolved_at >= month_start, FraudResolution.resolved_at < month_end)
        .group_by(FraudResolution.resolution)
    )
    resolution_counts = {"legitimate": 0, "confirmed_fraud": 0}
    for resolution, count in resolutions_result.all():
        resolution_counts[resolution.value] = count

    reversed_result = await db.execute(
        select(
            Transaction.currency,
            func.sum(Transaction.amount).label("total_amount"),
            func.count().label("count"),
        )
        .select_from(FraudResolution)
        .join(Transaction, Transaction.id == FraudResolution.transaction_id)
        .where(
            FraudResolution.resolution == FraudResolutionType.confirmed_fraud,
            FraudResolution.resolved_at >= month_start,
            FraudResolution.resolved_at < month_end,
        )
        .group_by(Transaction.currency)
    )
    reversed_amount_by_currency = [
        ReversedAmountByCurrency(
            currency=row.currency.value,
            total_amount=row.total_amount,
            count=row.count,
        )
        for row in reversed_result.all()
    ]

    return ComplianceSummaryResponse(
        month=month,
        total_transactions_created=total_transactions_created,
        currently_flagged_from_month=currently_flagged_from_month,
        resolutions_this_month=ResolutionCounts(**resolution_counts),
        reversed_amount_by_currency=reversed_amount_by_currency,
    )

