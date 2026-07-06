import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.core.cache_utils import invalidate_balance_cache
from app.db.session import get_db
from app.models.fraud_resolution import FraudResolution, FraudResolutionType
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.admin import (
    ComplianceSummaryResponse,
    FlaggedTransactionItem,
    FlaggedTransactionsResponse,
    ResolutionCounts,
    ResolveFlagRequest,
    ResolveFlagResponse,
    ReversedAmountByCurrency,
)
from app.schemas.user import CurrentUser, UserRole
from app.services.audit_log import append_audit
from app.services.wallet_locking import lock_and_credit_wallet
from app.utils.transaction_query_utils import compute_total_pages, parse_summary_month

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.get("/flagged-transactions", response_model=FlaggedTransactionsResponse)
async def get_flagged_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    NBL-111: paginated list of flagged transactions for compliance review.

    Filter is Transaction.status == "flagged" only (confirmed decision C).
    This correctly captures transactions flagged via the scoring-exception
    fallback path in send_money/bills.py, where fraud_score stays None --
    a fraud_score-based filter alone would miss those.

    rule_triggered is not filterable/returned -- no such column exists
    anywhere in this schema (same documented gap as DEVATTECH-73's
    transaction history/detail endpoints).
    """
    filter_condition = Transaction.status == TransactionStatus.flagged

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

    legitimate -> Transaction.status = completed (per approved decision B).
    confirmed_fraud -> reversal: credit the sender back under a
    SELECT ... FOR UPDATE lock (lock_and_credit_wallet, mirroring bills.py's
    lock_and_debit_wallet usage), then Transaction.status = reversed.

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
        # --- reversal: credit sender back, under lock ---
        wallet_result = await db.execute(
            select(Wallet).where(
                Wallet.user_id == transaction.sender_id,
                Wallet.currency == WalletCurrency(transaction.currency.value),
            )
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet is None:
            # Should not happen in practice -- the original transaction
            # required this exact wallet to exist. Hard failure, not a
            # silent skip.
            logger.error(
                "Cannot reverse transaction %s: sender %s has no %s wallet.",
                transaction_id, transaction.sender_id, transaction.currency.value,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reversal failed: sender wallet not found. Contact engineering.",
            )

        try:
            await lock_and_credit_wallet(db, wallet.id, transaction.amount)
        except ValueError:
            logger.error(
                "Cannot reverse transaction %s: wallet %s lock/credit failed.",
                transaction_id, wallet.id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reversal failed. Contact engineering.",
            )

        transaction.status = TransactionStatus.reversed
        audit_action = "reversed"
    else:
        # "legitimate"
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
        # Race: another reviewer's resolution committed first.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This transaction has already been resolved",
        )

    await db.refresh(transaction)
    await db.refresh(fraud_resolution)

    # Same best-effort-after-commit philosophy as bills.py: the resolution
    # (and reversal, if any) already succeeded and is durably committed by
    # this point. Audit logging and cache invalidation are best-effort
    # follow-ups -- a transient failure here must not turn an already-
    # successful resolution into a misleading error response.
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
        logger.error(
            "Resolution succeeded but audit log write failed for transaction %s (reviewer %s).",
            transaction_id, reviewer_id,
            exc_info=True,
        )

    if payload.resolution == "confirmed_fraud":
        try:
            await invalidate_balance_cache(transaction.sender_id)
        except Exception:
            logger.error(
                "Resolution succeeded but balance cache invalidation failed for user %s.",
                transaction.sender_id,
                exc_info=True,
            )

    return ResolveFlagResponse(
        transaction_id=transaction_id,
        resolution=payload.resolution,
        new_status=transaction.status.value,
        reviewer_id=reviewer_id,
        resolved_at=fraud_resolution.resolved_at,
    )


@router.get("/reports/summary", response_model=ComplianceSummaryResponse)
async def get_compliance_summary(
    month: str = Query(..., description="Format YYYY-MM, e.g. 2026-07"),
    current_user: CurrentUser = Depends(require_role(UserRole.compliance_officer, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    NBL-111: monthly compliance summary. Shape approved in review -- see
    app/schemas/admin.py's ComplianceSummaryResponse.

    Two different time bases are used deliberately, not by oversight:
      - total_transactions_created / currently_flagged_from_month are
        keyed off Transaction.created_at (the month being reported on).
      - resolutions_this_month / reversed_amount_by_currency are keyed off
        FraudResolution.resolved_at (when the compliance work happened),
        since a reviewer resolving an old flagged transaction this month
        is this month's compliance activity, regardless of when the
        underlying transaction was created.

    currently_flagged_from_month is a live snapshot, not a historical
    count -- since status is mutable (resolving a flag moves it away from
    "flagged"), a transaction flagged and resolved within the same month
    will NOT be counted here even though it was flagged at some point
    during the month. This is a real limitation, not a bug -- there is no
    immutable "was ever flagged" signal in this schema to fall back on.
    """
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
