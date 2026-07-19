import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_utils import cache_balance, get_cached_balance
from app.models.wallet import Wallet, WalletCurrency
from app.utils.account_utils import generate_account_number, generate_iban


logger = logging.getLogger(__name__)

MAX_IDENTIFIER_GENERATION_ATTEMPTS = 5


class AccountIdentifierGenerationError(RuntimeError):
    """Raised when unique wallet identifiers cannot be generated."""


def _is_account_identifier_collision(exc: IntegrityError) -> bool:
    """
    Return True only when an IntegrityError concerns account_number or IBAN.

    SQLite reports column names, while PostgreSQL normally reports the
    unique-constraint name. Checking both the original error and its
    constraint metadata keeps the retry limited to identifier collisions;
    unrelated integrity failures must still propagate immediately.
    """
    original_error = exc.orig
    constraint_name = getattr(original_error, "constraint_name", None)

    if constraint_name is None:
        diagnostic = getattr(original_error, "diag", None)
        constraint_name = getattr(diagnostic, "constraint_name", None)

    error_details = (
        f"{constraint_name or ''} {original_error}"
    ).lower()

    return (
        "account_number" in error_details
        or "iban" in error_details
    )


def _identifier_generation_error() -> AccountIdentifierGenerationError:
    return AccountIdentifierGenerationError(
        "Unable to generate unique account identifiers after "
        f"{MAX_IDENTIFIER_GENERATION_ATTEMPTS} attempts"
    )


async def _create_wallet_with_unique_identifiers(
    *,
    user_id: int,
    currency: WalletCurrency,
    db: AsyncSession,
) -> Wallet:
    last_collision: IntegrityError | None = None

    for attempt in range(1, MAX_IDENTIFIER_GENERATION_ATTEMPTS + 1):
        account_number = generate_account_number()
        iban = generate_iban(account_number)

        wallet = Wallet(
            user_id=user_id,
            currency=currency,
            balance=0,
            account_number=account_number,
            iban=iban,
        )

        try:
            # The savepoint isolates a failed generated pair. It prevents an
            # identifier collision from rolling back the caller's outer
            # transaction, which may already contain a newly registered user.
            async with db.begin_nested():
                db.add(wallet)
                await db.flush([wallet])
        except IntegrityError as exc:
            if not _is_account_identifier_collision(exc):
                raise

            last_collision = exc
            logger.warning(
                "Wallet identifier collision for user_id=%s currency=%s "
                "on attempt %s/%s",
                user_id,
                currency.value,
                attempt,
                MAX_IDENTIFIER_GENERATION_ATTEMPTS,
            )
            continue

        return wallet

    raise _identifier_generation_error() from last_collision


async def _backfill_wallet_identifiers(
    wallet: Wallet,
    db: AsyncSession,
) -> None:
    last_collision: IntegrityError | None = None

    for attempt in range(1, MAX_IDENTIFIER_GENERATION_ATTEMPTS + 1):
        account_number = (
            wallet.account_number or generate_account_number()
        )
        iban = wallet.iban or generate_iban(account_number)

        try:
            async with db.begin_nested():
                wallet.account_number = account_number
                wallet.iban = iban
                await db.flush([wallet])
        except IntegrityError as exc:
            if not _is_account_identifier_collision(exc):
                raise

            last_collision = exc
            logger.warning(
                "Wallet identifier backfill collision for wallet_id=%s "
                "on attempt %s/%s",
                wallet.id,
                attempt,
                MAX_IDENTIFIER_GENERATION_ATTEMPTS,
            )

            # Restore the database values after the savepoint rollback before
            # generating another pair.
            await db.refresh(
                wallet,
                attribute_names=["account_number", "iban"],
            )
            continue

        return

    raise _identifier_generation_error() from last_collision


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
            wallet = await _create_wallet_with_unique_identifiers(
                user_id=user_id,
                currency=currency,
                db=db,
            )
            wallets.append(wallet)

        elif existing.account_number is None or existing.iban is None:
            # Backfill wallets created by the old register() path.
            await _backfill_wallet_identifiers(existing, db)

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
