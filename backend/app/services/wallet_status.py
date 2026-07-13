"""
Shared guard and audit-writer for wallet lifecycle state (DEVATTECH-104).

Every code path that mutates Wallet.balance must call assert_wallet_active()
immediately after locking the wallet row (SELECT ... FOR UPDATE) and before
any balance check or mutation. This is the single source of truth for the
frozen/closed block described in DEVATTECH-104's AC -- do not re-implement
this check inline at a call site.

record_status_change() / record_status_change_sync() write to
account_status_audit_logs (append-only, trigger-protected -- see migration
1e652f5a22fd). Separate from services/audit_log.py's append_audit() because
transaction_audit_logs.transaction_id is NOT NULL and these are not
transaction events.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.account_status_audit_log import AccountStatusAuditLog
from app.models.wallet import Wallet, WalletStatus


class WalletFrozenError(Exception):
    """Raised when a mutation is attempted on a frozen wallet."""


class WalletClosedError(Exception):
    """Raised when a mutation is attempted on a closed wallet."""


def assert_wallet_active(wallet: Wallet) -> None:
    """
    Raises WalletFrozenError or WalletClosedError if the wallet is not
    active. Callers are responsible for translating these into the
    422 {"error": "wallet_frozen"} / {"error": "wallet_closed"} response
    shape at their own HTTP boundary.
    """
    if wallet.status == WalletStatus.frozen:
        raise WalletFrozenError(f"Wallet {wallet.id} is frozen")
    if wallet.status == WalletStatus.closed:
        raise WalletClosedError(f"Wallet {wallet.id} is closed")


async def record_status_change(
    db: AsyncSession,
    *,
    wallet_id: int,
    action: str,
    actor_id: int | None,
    metadata: dict | None = None,
) -> AccountStatusAuditLog:
    """
    Insert one row into account_status_audit_logs and commit immediately,
    same convention as services/audit_log.py's append_audit().
    """
    audit_entry = AccountStatusAuditLog(
        wallet_id=wallet_id,
        action=action,
        actor_id=actor_id,
        event_metadata=metadata,
    )
    db.add(audit_entry)
    await db.commit()
    await db.refresh(audit_entry)
    return audit_entry


def record_status_change_sync(
    db: Session,
    *,
    wallet_id: int,
    action: str,
    actor_id: int | None,
    metadata: dict | None = None,
) -> AccountStatusAuditLog:
    """Sync equivalent of record_status_change() for Celery task code paths."""
    audit_entry = AccountStatusAuditLog(
        wallet_id=wallet_id,
        action=action,
        actor_id=actor_id,
        event_metadata=metadata,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry
