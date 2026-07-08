"""
Locked-debit helper for endpoints that need to safely deduct from a
SINGLE wallet.

NOTE: this is not literally extracted from send_money's code.
send_money locks a sender+receiver PAIR together (two wallets, one
statement, ordered by id to avoid deadlocks) -- there's no second wallet
to lock for a bill payment, so the same code can't be reused verbatim.
This follows the same SELECT ... FOR UPDATE principle instead.

Used by: app/api/v1/endpoints/bills.py only. send_money is NOT modified
to use this -- DEVATTECH-72 logic is unchanged, per instruction.

DEVATTECH-104: both functions now call assert_wallet_active() right after
the row lock, before any balance check/mutation, so frozen/closed wallets
are rejected on this path too. WalletFrozenError/WalletClosedError are NOT
ValueError subclasses -- callers must catch them separately from the
existing "not found"/"insufficient balance" ValueError handling, since
they map to a different response (422 wallet_frozen/wallet_closed, not
the 404/500 paths ValueError triggers here).
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet
from app.services.wallet_status import assert_wallet_active


async def lock_and_debit_wallet(db: AsyncSession, wallet_id: int, amount: Decimal) -> Wallet:
    """
    Locks the given wallet row (SELECT ... FOR UPDATE), re-checks balance,
    and debits it in-place. Does NOT commit -- the caller controls the
    transaction boundary (so it can be combined with other inserts in one
    commit, same convention as send_money).

    Callers should have already done an advisory (non-locked) balance
    check before any slow/external work (e.g. the biller call) -- this
    function's re-check is the authoritative one, immediately before the
    actual debit.

    Raises ValueError if the wallet doesn't exist, or if balance is
    insufficient at lock time. Callers decide how to translate either case
    into an HTTP response. Raising ValueError here (an application-level
    error) rather than letting SQLAlchemy's NoResultFound propagate keeps
    this helper's failure mode predictable and independent of the ORM,
    which matters since it may be reused by other endpoints later.

    Raises WalletFrozenError / WalletClosedError (DEVATTECH-104) if the
    wallet is not active -- see assert_wallet_active().
    """
    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    wallet = result.scalar_one_or_none()

    if wallet is None:
        raise ValueError(f"Wallet {wallet_id} not found")

    assert_wallet_active(wallet)

    if wallet.balance < amount:
        raise ValueError("Insufficient balance at debit time")

    wallet.balance -= amount
    return wallet


async def lock_and_credit_wallet(db: AsyncSession, wallet_id: int, amount: Decimal) -> Wallet:
    """
    Locks the given wallet row (SELECT ... FOR UPDATE) and credits it
    in-place. Does NOT commit -- caller controls the transaction boundary,
    same convention as lock_and_debit_wallet.

    Used by NBL-111's fraud-reversal flow, to credit the sender back when
    a flagged transaction is confirmed as fraud.

    Unlike lock_and_debit_wallet, there is no insufficient-balance check
    here -- crediting a wallet can't fail on balance grounds.

    Raises ValueError if the wallet doesn't exist, for the same reason
    lock_and_debit_wallet does: a predictable application-level error
    rather than SQLAlchemy's NoResultFound, since this may be reused
    elsewhere later.

    Raises WalletFrozenError / WalletClosedError (DEVATTECH-104) if the
    wallet is not active -- see assert_wallet_active().
    """
    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    wallet = result.scalar_one_or_none()

    if wallet is None:
        raise ValueError(f"Wallet {wallet_id} not found")

    assert_wallet_active(wallet)

    wallet.balance += amount
    return wallet
