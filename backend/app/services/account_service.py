from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_utils import cache_balance, get_cached_balance
from app.models.wallet import Wallet, WalletCurrency
from app.utils.account_utils import generate_account_number, generate_iban


async def create_wallets_for_user(
    user_id: int,
    db: AsyncSession,
):
    wallets = []

    for currency in WalletCurrency:
        result = await db.execute(
            select(Wallet).where(
                Wallet.user_id == user_id,
                Wallet.currency == currency,
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            account_number = generate_account_number()
            iban = generate_iban(account_number)

            wallet = Wallet(
                user_id=user_id,
                currency=currency,
                balance=0,
                account_number=account_number,
                iban=iban,
            )
            db.add(wallet)
            wallets.append(wallet)

        elif existing.account_number is None or existing.iban is None:
            # Backfill wallets created by the old register() path.
            existing.account_number = (
                existing.account_number or generate_account_number()
            )
            existing.iban = (
                existing.iban
                or generate_iban(existing.account_number)
            )

    await db.commit()

    return wallets


async def get_user_balances(
    user_id: int,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """
    Return all wallet balances for one user.

    Reused by:
    - GET /accounts/balance
    - NBL-510 chatbot balance tool

    Uses the existing Redis balance cache.
    """
    cached = await get_cached_balance(user_id)

    if cached is not None:
        return cached

    result = await db.execute(
        select(Wallet).where(
            Wallet.user_id == user_id,
        )
    )
    wallets = result.scalars().all()

    if not wallets:
        return None

    response: dict[str, Any] = {
        "user_id": user_id,
        "balances": [
            {
                "currency": wallet.currency.value,
                "balance": float(wallet.balance),
                "account_number": wallet.account_number,
                "iban": wallet.iban,
            }
            for wallet in wallets
        ],
    }

    await cache_balance(user_id, response)

    return response