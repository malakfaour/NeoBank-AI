import asyncio
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.cache_utils import invalidate_balance_cache
from app.core.config import settings
from app.core.redis import (
    TOPUP_DAILY_LIMIT,
    get_topup_daily_total,
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
from app.schemas.user import CurrentUser
from app.schemas.wallet import CardTopUpRequest, CardTopUpResponse, WalletStatusChangeResponse
from app.services.account_service import (
    create_wallets_for_user,
    get_user_balances,
)
from app.services.audit_log import append_audit
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


async def _call_payment_gateway(
    card_token: str,
    amount,
    currency: str,
) -> httpx.Response:
    """
    Calls the external card payment gateway (NBL-411). Retries once, after
    a 2s pause, on a 5xx response -- gateways are occasionally flaky under
    load and a single retry clears most transient failures without the
    user needing to resubmit. Not retried on 402 (declined), since that's
    a definitive answer from the gateway, not a transient failure.
    """
    payload = {
        "card_token": card_token,
        "amount": str(amount),
        "currency": currency,
    }

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        response = await http_client.post(
            settings.PAYMENT_GATEWAY_URL,
            json=payload,
        )

        if response.status_code >= 500:
            await asyncio.sleep(2)
            response = await http_client.post(
                settings.PAYMENT_GATEWAY_URL,
                json=payload,
            )

    return response


@router.post("/top-up", response_model=CardTopUpResponse)
async def card_top_up(
    payload: CardTopUpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Tokenized card top-up endpoint.

    This endpoint does not accept or store real card numbers.
    It only accepts a tokenized card reference such as tok_visa_test_123.
    Only the authenticated owner of the wallet can top it up.
    """

    if not payload.card_token.startswith("tok_"):
        raise HTTPException(
            status_code=400,
            detail="Invalid card token. Use a tokenized card reference.",
        )

    result = await db.execute(
        select(Wallet).where(
            Wallet.id == payload.wallet_id,
            Wallet.user_id == int(current_user.id),
        )
    )
    wallet = result.scalar_one_or_none()

    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet not found")

    daily_total = await get_topup_daily_total(int(current_user.id))
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

    gateway_response = await _call_payment_gateway(
        payload.card_token,
        payload.amount,
        wallet.currency.value,
    )

    if gateway_response.status_code == 402:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "card_declined",
                "gateway_message": gateway_response.json().get(
                    "message",
                    "Card declined",
                ),
            },
        )

    if gateway_response.status_code >= 500:
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
    # idempotency_key: CardTopUpRequest has no client-supplied idempotency
    # header today (unlike /transactions/send), so a fresh uuid4 is used
    # here purely to satisfy the column's UNIQUE NOT NULL constraint. This
    # does NOT protect against a double-submit the way send_money's
    # header-based key does -- flagged as a follow-up, not solved by this
    # ticket.
    transaction = Transaction(
        sender_id=wallet.user_id,
        receiver_id=wallet.user_id,
        amount=payload.amount,
        currency=TransactionCurrency(wallet.currency.value),
        category="TopUp",
        status=TransactionStatus.completed,
        idempotency_key=f"topup:{uuid4().hex}",
    )
    db.add(transaction)

    await db.commit()
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
        },
    )

    return {
        "wallet_id": wallet.id,
        "currency": (
            wallet.currency.value
            if hasattr(wallet.currency, "value")
            else str(wallet.currency)
        ),
        "top_up_amount": payload.amount,
        "new_balance": wallet.balance,
        "status": "success",
        "message": "Card top-up completed successfully",
    }


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

