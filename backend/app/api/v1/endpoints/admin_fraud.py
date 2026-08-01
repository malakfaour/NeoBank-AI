from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.dependencies import require_role
from app.core.cache_utils import invalidate_balance_cache
from app.db.session import get_db
from app.models.exchange_audit_log import ExchangeAuditLog
from app.models.fraud_resolution import FraudResolution, FraudResolutionType
from app.models.model_metrics import ModelMetrics
from app.models.transaction import (
    LedgerDirection,
    Transaction,
    TransactionStatus,
)
from app.models.transaction_audit_log import TransactionAuditLog
from app.models.user import User, UserRole
from app.models.wallet import Wallet, WalletCurrency

from app.schemas.admin import (
    AdminTransactionItem,
    AdminTransactionsResponse,
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

from app.schemas.audit_log import AuditLogEntry, AuditTrailResponse
from app.schemas import CurrentUser

from app.services.audit_log import append_audit
from app.services.fraud_scoring import FRAUD_FLAG_THRESHOLD
from app.services.wallet_locking import lock_and_credit_wallet

from app.utils.transaction_query_utils import (
    compute_total_pages,
    parse_summary_month,
)


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/transactions", response_model=AdminTransactionsResponse)
async def list_all_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: TransactionStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, min_length=1, description="Match sender/receiver name or email"),
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """General-purpose admin transaction browser, not just flagged ones."""
    sender = aliased(User)
    receiver = aliased(User)
    filters = []
    if status_filter is not None:
        filters.append(Transaction.status == status_filter)
    if q:
        like_pattern = f"%{q}%"
        filters.append(
            or_(
                sender.full_name.ilike(like_pattern),
                sender.email.ilike(like_pattern),
                receiver.full_name.ilike(like_pattern),
                receiver.email.ilike(like_pattern),
            )
        )
    base_query = (
        select(Transaction, sender, receiver)
        .join(sender, sender.id == Transaction.sender_id)
        .join(receiver, receiver.id == Transaction.receiver_id)
        .where(*filters)
    )

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.order_by(Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    items = [
        AdminTransactionItem(
            id=tx.id,
            sender_id=tx.sender_id,
            sender_name=sender_user.full_name,
            receiver_id=tx.receiver_id,
            receiver_name=receiver_user.full_name,
            amount=tx.amount,
            currency=tx.currency.value,
            category=tx.category,
            status=tx.status.value,
            created_at=tx.created_at,
        )
        for tx, sender_user, receiver_user in rows
    ]

    return AdminTransactionsResponse(
        items=items, page=page, page_size=page_size, total=total,
        total_pages=compute_total_pages(total, page_size),
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

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


@router.get("/flagged-transactions", response_model=FlaggedTransactionsResponse)
async def get_flagged_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    filter_condition = or_(
        Transaction.status == TransactionStatus.flagged,
        Transaction.fraud_score > FRAUD_FLAG_THRESHOLD,
        Transaction.rule_triggered == True,  # noqa: E712
    )

    count_result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(filter_condition)
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
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    reviewer_id = int(current_user.id)

    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    if transaction.status != TransactionStatus.flagged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transaction is not currently flagged (status={transaction.status.value})",
        )

    existing_result = await db.execute(
        select(FraudResolution).where(
            FraudResolution.transaction_id == transaction_id
        )
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

        await lock_and_credit_wallet(
            db,
            wallet.id,
            transaction.amount,
        )

        transaction.status = TransactionStatus.reversed
        audit_action = "reversed"

        compensating_transaction = Transaction(
            sender_id=transaction.sender_id,
            receiver_id=transaction.sender_id,
            amount=transaction.amount,
            currency=transaction.currency,
            category="Reversal",
            status=TransactionStatus.completed,
            ledger_direction=LedgerDirection.credit,
            idempotency_key=f"reversal:{transaction.id}",
        )

        db.add(compensating_transaction)

    else:
        transaction.status = TransactionStatus.completed
        audit_action = "resolved_legitimate"
        compensating_transaction = None

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

    if compensating_transaction is not None:
        await db.refresh(compensating_transaction)

    try:
        await append_audit(
            db,
            transaction_id=transaction_id,
            action=audit_action,
            actor_id=reviewer_id,
            metadata={
                "resolution": payload.resolution,
                "reviewer_note": payload.reviewer_note,
                **(
                    {
                        "compensating_transaction_id": compensating_transaction.id
                    }
                    if compensating_transaction is not None
                    else {}
                ),
            },
        )
    except Exception:
        pass

    if compensating_transaction is not None:
        try:
            await append_audit(
                db,
                transaction_id=compensating_transaction.id,
                action="reversal_credit",
                actor_id=reviewer_id,
                metadata={
                    "related_transaction_id": transaction_id,
                    "resolution": payload.resolution,
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
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(
        select(func.count()).select_from(ExchangeAuditLog)
    ) or 0

    result = await db.execute(
        select(ExchangeAuditLog, User)
        .outerjoin(User, User.id == ExchangeAuditLog.user_id)
        .order_by(
            ExchangeAuditLog.created_at.desc(),
            ExchangeAuditLog.id.desc()
        )
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
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
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
            & (
                ModelMetrics.trained_at
                == latest_per_model.c.latest_trained_at
            ),
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
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
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

    month_end = (
        date(year + 1, 1, 1)
        if month_num == 12
        else date(year, month_num + 1, 1)
    )

    total_result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.created_at >= month_start,
            Transaction.created_at < month_end,
        )
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

    flagged_rate = (
        currently_flagged_from_month / total_transactions_created
        if total_transactions_created
        else 0.0
    )

    resolutions_result = await db.execute(
        select(
            FraudResolution.resolution,
            func.count()
        )
        .where(
            FraudResolution.resolved_at >= month_start,
            FraudResolution.resolved_at < month_end,
        )
        .group_by(FraudResolution.resolution)
    )

    resolution_counts = {
        "legitimate": 0,
        "confirmed_fraud": 0,
    }

    for resolution, count in resolutions_result.all():
        resolution_counts[resolution.value] = count

    reversed_result = await db.execute(
        select(
            Transaction.currency,
            func.sum(Transaction.amount).label("total_amount"),
            func.count().label("count"),
        )
        .select_from(FraudResolution)
        .join(
            Transaction,
            Transaction.id == FraudResolution.transaction_id,
        )
        .where(
            FraudResolution.resolution
            == FraudResolutionType.confirmed_fraud,
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
        flagged_rate=round(flagged_rate, 4),
        resolutions_this_month=ResolutionCounts(**resolution_counts),
        reversed_amount_by_currency=reversed_amount_by_currency,
    )

