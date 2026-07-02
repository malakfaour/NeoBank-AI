from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import KYCStatus, User
from app.models.wallet import Wallet
from app.schemas.user import CurrentUser
from app.services.account_service import create_wallets_for_user

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("/create")
async def create_account(user_id: int, db: AsyncSession = Depends(get_db)):
    """Auto-create 3 wallets for a user at balance=0"""
    try:
        wallets = await create_wallets_for_user(user_id, db)
        return {
            "message": "Wallets created successfully",
            "user_id": user_id,
            "wallets_created": len(wallets)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/balance")
async def get_balance(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get all wallet balances for a user - reads fresh from DB"""
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == user_id)
    )
    wallets = result.scalars().all()
    if not wallets:
        raise HTTPException(status_code=404, detail="No wallets found for this user")
    return {
        "user_id": user_id,
        "balances": [
            {
                "currency": w.currency,
                "balance": float(w.balance)
            }
            for w in wallets
        ]
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
            status_code=400, detail="Provide either phone or iban query param"
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
        # Placeholder: no real account-type concept exists in the schema
        # yet. Hardcoded until product defines individual/business etc.
        "account_type": "individual",
        "kyc_approved": user.kyc_status == KYCStatus.approved,
    }
