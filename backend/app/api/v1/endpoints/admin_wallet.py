from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.core.cache_utils import invalidate_balance_cache
from app.db.session import get_db
from app.models.transaction import (
    LedgerDirection,
    Transaction,
    TransactionCurrency,
    TransactionStatus,
)
from app.models.user import User, UserRole
from app.models.wallet import Wallet

from app.schemas.admin import (
    AdminUserSearchItem,
    AdminUserSearchResponse,
    AdminUserStatusResponse,
    AdminUserWalletsResponse,
    AdminWalletAdjustRequest,
    AdminWalletAdjustResponse,
    AdminWalletItem,
)

from app.schemas import CurrentUser

from app.services.audit_log import append_audit
from app.services.wallet_locking import (
    lock_and_credit_wallet,
    lock_and_debit_wallet,
)

from app.utils.transaction_query_utils import compute_total_pages


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users/search", response_model=AdminUserSearchResponse)
async def search_users(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    DEVATTECH-108: search users by name/phone/account number (partial match).
    """

    like_pattern = f"%{q}%"

    filter_condition = or_(
        User.full_name.ilike(like_pattern),
        User.phone.ilike(like_pattern),
        Wallet.account_number.ilike(like_pattern),
    )

    base_query = (
        select(User.id)
        .outerjoin(Wallet, Wallet.user_id == User.id)
        .where(filter_condition)
        .distinct()
    )

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )

    total = count_result.scalar_one()

    id_result = await db.execute(
        base_query.order_by(User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    user_ids = [row[0] for row in id_result.all()]

    result = await db.execute(
        select(User).where(User.id.in_(user_ids)).order_by(User.id.asc())
    )

    users = result.scalars().all()

    return AdminUserSearchResponse(
        items=[
            AdminUserSearchItem(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                phone=u.phone,
                kyc_status=u.kyc_status.value,
                role=u.role.value,
                is_active=u.is_active,
            )
            for u in users
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.get("/users/{user_id}/wallets", response_model=AdminUserWalletsResponse)
async def get_user_wallets(
    user_id: int,
    current_user: CurrentUser = Depends(
        require_role(UserRole.compliance_officer, UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    DEVATTECH-108: list a user's wallets for support lookup.
    """

    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )

    if user_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    result = await db.execute(
        select(Wallet)
        .where(Wallet.user_id == user_id)
        .order_by(Wallet.currency)
    )

    wallets = result.scalars().all()

    return AdminUserWalletsResponse(
        user_id=user_id,
        items=[
            AdminWalletItem(
                id=w.id,
                currency=w.currency.value,
                balance=w.balance,
                account_number=w.account_number,
                iban=w.iban,
            )
            for w in wallets
        ],
    )


async def _set_user_active(
    user_id: int,
    is_active: bool,
    current_user: CurrentUser,
    db: AsyncSession,
) -> AdminUserStatusResponse:
    if int(current_user.id) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot suspend or reactivate your own account.",
        )
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = is_active
    await db.commit()
    await db.refresh(user)

    return AdminUserStatusResponse(id=user.id, is_active=user.is_active)


@router.post("/users/{user_id}/suspend", response_model=AdminUserStatusResponse)
async def suspend_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Suspend a user account -- admin only. Blocks future logins and
    immediately invalidates any active session (get_current_user checks
    is_active on every request), without deleting the account or its data."""
    return await _set_user_active(user_id, False, current_user, db)


@router.post("/users/{user_id}/activate", response_model=AdminUserStatusResponse)
async def activate_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate a previously suspended user account -- admin only."""
    return await _set_user_active(user_id, True, current_user, db)


@router.post("/wallets/{wallet_id}/adjust", response_model=AdminWalletAdjustResponse)
async def adjust_wallet_balance(
    wallet_id: int,
    payload: AdminWalletAdjustRequest,
    current_user: CurrentUser = Depends(
        require_role(UserRole.admin)
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    DEVATTECH-108: manual wallet balance adjustment.
    Admin only.
    """

    wallet_check = await db.execute(
        select(Wallet).where(Wallet.id == wallet_id)
    )

    if wallet_check.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    if payload.direction == "credit":
        wallet = await lock_and_credit_wallet(
            db,
            wallet_id,
            payload.amount,
        )

    else:
        try:
            wallet = await lock_and_debit_wallet(
                db,
                wallet_id,
                payload.amount,
            )

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "insufficient_balance",
                    "detail": str(e),
                },
            )

    transaction = Transaction(
        sender_id=wallet.user_id,
        receiver_id=wallet.user_id,
        amount=payload.amount,
        currency=TransactionCurrency(wallet.currency.value),
        category="Adjustment",
        status=TransactionStatus.completed,
        ledger_direction=(
            LedgerDirection.credit
            if payload.direction == "credit"
            else LedgerDirection.debit
        ),
        idempotency_key=f"admin-adjust:{uuid4().hex}",
    )

    db.add(transaction)

    await db.commit()

    await db.refresh(transaction)
    await db.refresh(wallet)

    await invalidate_balance_cache(wallet.user_id)

    await append_audit(
        db,
        transaction_id=transaction.id,
        action="admin_adjustment",
        actor_id=int(current_user.id),
        metadata={
            "direction": payload.direction,
            "reason": payload.reason,
            "amount": str(payload.amount),
        },
    )

    return AdminWalletAdjustResponse(
        wallet_id=wallet.id,
        transaction_id=transaction.id,
        direction=payload.direction,
        amount=payload.amount,
        new_balance=wallet.balance,
        reason=payload.reason,
    )