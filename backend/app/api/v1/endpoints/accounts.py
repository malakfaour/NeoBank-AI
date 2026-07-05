from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.cache_utils import cache_balance, get_cached_balance, invalidate_balance_cache
from app.db.session import get_db
from app.models.user import KYCStatus, User
from app.models.wallet import Wallet
from app.schemas.user import CurrentUser
from app.schemas.wallet import CardTopUpRequest, CardTopUpResponse
from app.services.account_service import create_wallets_for_user

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
    Get all wallet balances for the authenticated user. Cached in Redis
    for 30s (NBL-403) -- cache is invalidated on every debit/credit by the
    transactions service via app.core.cache_utils.invalidate_balance_cache.
    """
    user_id = int(current_user.id)
    cached = await get_cached_balance(user_id)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Wallet).where(Wallet.user_id == user_id)
    )
    wallets = result.scalars().all()

    if not wallets:
        raise HTTPException(status_code=404, detail="No wallets found for this user")

    response = {
        "user_id": user_id,
        "balances": [
            {
                "currency": w.currency.value,
                "balance": float(w.balance),
                "account_number": w.account_number,
                "iban": w.iban,
            }
            for w in wallets
        ],
    }

    await cache_balance(user_id, response)

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

    wallet.balance = wallet.balance + payload.amount

    await db.commit()
    await db.refresh(wallet)

    await invalidate_balance_cache(wallet.user_id)

    return {
        "wallet_id": wallet.id,
        "currency": wallet.currency.value if hasattr(wallet.currency, "value") else str(wallet.currency),
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
        result = await db.execute(select(User).where(User.phone == phone))
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
