
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.cache_utils import invalidate_balance_cache
from app.core.redis import (
    TOPUP_DAILY_LIMIT,
    cache_idempotent_response,
    get_cached_idempotent_response,
    get_topup_daily_total,
    hash_idempotency_key,
    increment_topup_daily,
)
from app.db.session import get_db
from app.models.transaction import (
    Transaction,
    TransactionCurrency,
    TransactionStatus,
)
from app.models.user import KYCStatus, User, UserRole
from app.models.wallet import Wallet, WalletStatus
from app.schemas.auth import CurrentUser
from app.schemas.wallet import CardTopUpRequest, CardTopUpResponse, WalletStatusChangeResponse
from app.services.account_service import (
    create_wallets_for_user,
    get_user_balances,
)
from app.services.audit_log import append_audit
from app.services.stripe_gateway import (
    SUPPORTED_CURRENCIES,
    CardDeclinedError,
    GatewayUnavailableError,
    charge_card,
)
from app.services.wallet_status import WalletClosedError, WalletFrozenError, assert_wallet_active, record_status_change

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("/create")
async def create_account(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Auto-create 3 wallets for the authenticated user at balance=0"""
    user_id = int(current_user.id)
    try:
        wallets = await create_wallets_for_user(user_id, db)
        return {
            "message": "Wallets created successfully",
            "user_id": user_id,
            "wallets_created": len(wallets),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/balance")
async def get_balance(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all wallet balances for the authenticated user.

    Cached in Redis for 30 seconds.
    """
    user_id = int(current_user.id)

    response = await get_user_balances(
        user_id=user_id,
        db=db,
    )

    if response is None:
        raise HTTPException(
            status_code=404,
            detail="No wallets found for this user",
        )

    return response


@router.post("/top-up", response_model=CardTopUpResponse)
async def card_top_up(
    payload: CardTopUpRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Real card top-up endpoint (DEVATTECH-131).

    Card data itself never reaches this backend: the frontend tokenizes it
    directly with Stripe (Stripe Elements) and sends only the resulting
    payment_method_id here. Only the authenticated owner of the wallet can
    top it up. USD and LBP wallets only -- see stripe_gateway.py for why
    USDT is out of scope for a card charge.

    DEVATTECH-125: idempotency, matching send_money's pattern exactly.
    "topup:" prefix applied to the raw client-supplied key at every call
    site (Redis lookup, Redis cache-set, and the hashed
    Transaction.idempotency_key value) -- this is the entire fix for a
    real cross-endpoint collision risk: hash_idempotency_key(user_id,
    raw_key) ignores its own `endpoint` parameter whenever `raw_key` is
    passed directly (confirmed from the current app/core/redis.py,
    NOT modified here), so an unprefixed key reused by a naive client
    across /transactions/send and /accounts/top-up would hash identically
    on both endpoints. The prefix resolves this without touching the
    shared Redis helper at all.
    """

    user_id = int(current_user.id)

    # --- idempotency: replay cached response if this key was already used ---
    # Deliberately BEFORE wallet lookup, daily-limit processing, and the
    # gateway call -- a cache hit must short-circuit all of that, per
    # approved scope.
    cached_response = await get_cached_idempotent_response(user_id, f"topup:{x_idempotency_key}")
    if cached_response is not None:
        return CardTopUpResponse(**cached_response)

    result = await db.execute(
        select(Wallet).where(
            Wallet.id == payload.wallet_id,
            Wallet.user_id == user_id,
        )
    )
    wallet = result.scalar_one_or_none()

    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet not found")

    if wallet.currency.value not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_topup_currency",
                "message": (
                    f"Card top-up isn't available for {wallet.currency.value} wallets. "
                    "Top up your USD or LBP wallet, then use Exchange to convert."
                ),
            },
        )

    daily_total = await get_topup_daily_total(user_id)
    if daily_total + payload.amount > TOPUP_DAILY_LIMIT:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "daily_topup_limit_exceeded",
                "daily_limit": str(TOPUP_DAILY_LIMIT),
                "already_topped_up_today": str(daily_total),
                "requested": str(payload.amount),
            },
        )

    # Stripe-side idempotency key only -- distinct from the client's
    # X-Idempotency-Key / Transaction.idempotency_key above (DEVATTECH-125).
    # This one just needs to be stable per attempt so Stripe itself doesn't
    # double-charge on a retried request; it does not replace the header-based
    # key that makes this endpoint safely replayable end-to-end.
    attempt_key = uuid4().hex

    try:
        stripe_payment_intent_id = await charge_card(
            payload.payment_method_id,
            payload.amount,
            wallet.currency.value,
            idempotency_key=attempt_key,
        )
    except CardDeclinedError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "card_declined",
                "gateway_message": exc.message,
            },
        )
    except GatewayUnavailableError:
        raise HTTPException(
            status_code=502,
            detail="Payment gateway unavailable",
        )

    # Row-locked re-fetch right before the mutation (NBL-411). Deliberately
    # NOT locked earlier: the gateway call above can take up to ~22s
    # worst-case (10s timeout + 2s retry pause + 10s retry), and holding a
    # SELECT FOR UPDATE across that entire external call would block every
    # other operation on this wallet for the duration. Locking only here
    # matches the pattern in transactions.send_money.
    result = await db.execute(
        select(Wallet).where(Wallet.id == wallet.id).with_for_update()
    )
    wallet = result.scalar_one()
    try:
        assert_wallet_active(wallet)
    except (WalletFrozenError, WalletClosedError) as e:
        reason = "wallet_frozen" if isinstance(e, WalletFrozenError) else "wallet_closed"
        raise HTTPException(
            status_code=422,
            detail={"error": reason},
        )

    wallet.balance = wallet.balance + payload.amount

    # NBL-411: top-ups are modeled as sender_id == receiver_id == the
    # topping-up user, since Transaction.sender_id is NOT NULL and this
    # table has no separate type/direction column -- category='TopUp'
    # is the discriminator (see transactions.py list/detail/summary,
    # which key off this same category value). This intentionally does
    # NOT go through fraud scoring (score_transaction is only dispatched
    # from send_money) since a self-top-up has no fraud-relevant
    # sender/receiver relationship to score.
    #
    # idempotency_key: DEVATTECH-125 -- now derived from the required
    # X-Idempotency-Key header via hash_idempotency_key(), same pattern
    # as send_money. "topup:" prefix distinguishes this endpoint's keys
    # from send_money's within the shared Redis idempotency helper (see
    # this function's docstring for why that prefix is required).
    transaction = Transaction(
        sender_id=wallet.user_id,
        receiver_id=wallet.user_id,
        amount=payload.amount,
        currency=TransactionCurrency(wallet.currency.value),
        category="TopUp",
        status=TransactionStatus.completed,
        idempotency_key=hash_idempotency_key(user_id, f"topup:{x_idempotency_key}"),
    )
    db.add(transaction)

    try:
        await db.commit()
    except IntegrityError:
        # Redis-level idempotency check above raced and both requests got
        # past it -- the DB's unique constraint on idempotency_key is the
        # real safety net, same pattern as send_money. Roll back so the
        # balance mutation staged above never lands twice.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Duplicate request: this idempotency key is already being processed",
        )

    await db.refresh(wallet)
    await db.refresh(transaction)

    await invalidate_balance_cache(wallet.user_id)
    await increment_topup_daily(wallet.user_id, payload.amount)

    await append_audit(
        db,
        transaction_id=transaction.id,
        action="topup_completed",
        actor_id=wallet.user_id,
        metadata={
            "amount": str(payload.amount),
            "currency": wallet.currency.value,
            "wallet_id": wallet.id,
            "stripe_payment_intent_id": stripe_payment_intent_id,
        },
    )

    response = CardTopUpResponse(
        wallet_id=wallet.id,
        currency=(
            wallet.currency.value
            if hasattr(wallet.currency, "value")
            else str(wallet.currency)
        ),
        top_up_amount=payload.amount,
        new_balance=wallet.balance,
        status="success",
        message="Card top-up completed successfully",
    )

    await cache_idempotent_response(user_id, f"topup:{x_idempotency_key}", response.model_dump(mode="json"))

    return response


@router.get("/validate-recipient")
async def validate_recipient(
    phone: str | None = None,
    iban: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Pre-transfer recipient check for the frontend confirmation screen.
    Never returns 404 for a missing recipient -- exists=False instead,
    to avoid account enumeration (DEVATTECH-82).
    """
    if not phone and not iban:
        raise HTTPException(
            status_code=400,
            detail="Provide either phone or iban query param",
        )

    user = None

    if iban:
        result = await db.execute(
            select(User)
            .join(Wallet, Wallet.user_id == User.id)
            .where(Wallet.iban == iban)
        )
        user = result.scalars().first()
    elif phone:
        result = await db.execute(
            select(User).where(User.phone == phone)
        )
        user = result.scalar_one_or_none()

    if user is None:
        return {
            "exists": False,
            "display_name": None,
            "account_type": None,
            "kyc_approved": False,
        }

    return {
        "exists": True,
        "display_name": user.full_name,
        "account_type": "individual",
        "kyc_approved": user.kyc_status == KYCStatus.approved,
    }




async def _get_owned_or_admin_wallet(wallet_id: int, current_user: CurrentUser, db: AsyncSession) -> Wallet:
    """
    Shared ownership/role check for lifecycle endpoints (DEVATTECH-104).
    "Owner or admin": the wallet's own user, or a user with admin/
    compliance_officer role. Not using require_role() alone since that
    would reject the wallet's own owner.
    """
    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet not found")

    is_owner = wallet.user_id == int(current_user.id)
    is_admin = current_user.role in (UserRole.admin, UserRole.compliance_officer)
    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized for this wallet")

    return wallet


@router.post("/{wallet_id}/freeze", response_model=WalletStatusChangeResponse)
async def freeze_wallet(
    wallet_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_or_admin_wallet(wallet_id, current_user, db)

    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    wallet = result.scalar_one()

    if wallet.status == WalletStatus.closed:
        raise HTTPException(status_code=422, detail={"error": "wallet_closed"})

    if wallet.status != WalletStatus.frozen:
        wallet.status = WalletStatus.frozen
        await db.commit()
        await record_status_change(
            db,
            wallet_id=wallet.id,
            action="frozen",
            actor_id=int(current_user.id),
        )
        await invalidate_balance_cache(wallet.user_id)

    return WalletStatusChangeResponse(
        wallet_id=wallet.id,
        status=wallet.status.value,
        message="Wallet frozen",
    )


@router.post("/{wallet_id}/unfreeze", response_model=WalletStatusChangeResponse)
async def unfreeze_wallet(
    wallet_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_or_admin_wallet(wallet_id, current_user, db)

    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    wallet = result.scalar_one()

    if wallet.status == WalletStatus.closed:
        raise HTTPException(status_code=422, detail={"error": "wallet_closed"})

    if wallet.status != WalletStatus.active:
        wallet.status = WalletStatus.active
        await db.commit()
        await record_status_change(
            db,
            wallet_id=wallet.id,
            action="unfrozen",
            actor_id=int(current_user.id),
        )
        await invalidate_balance_cache(wallet.user_id)

    return WalletStatusChangeResponse(
        wallet_id=wallet.id,
        status=wallet.status.value,
        message="Wallet unfrozen",
    )


@router.post("/{wallet_id}/close", response_model=WalletStatusChangeResponse)
async def close_wallet(
    wallet_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_or_admin_wallet(wallet_id, current_user, db)

    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    wallet = result.scalar_one()

    if wallet.status == WalletStatus.closed:
        return WalletStatusChangeResponse(
            wallet_id=wallet.id,
            status=wallet.status.value,
            message="Wallet already closed",
        )

    if wallet.balance != 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "wallet_balance_not_zero", "balance": str(wallet.balance)},
        )

    wallet.status = WalletStatus.closed
    await db.commit()
    await record_status_change(
        db,
        wallet_id=wallet.id,
        action="closed",
        actor_id=int(current_user.id),
    )
    await invalidate_balance_cache(wallet.user_id)

    return WalletStatusChangeResponse(
        wallet_id=wallet.id,
        status=wallet.status.value,
        message="Wallet closed",
    )
