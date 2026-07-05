from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.transaction_audit_log import TransactionAuditLog


async def append_audit(
    db: AsyncSession,
    *,
    transaction_id: int,
    action: str,
    actor_id: int | None,
    metadata: dict | None = None,
) -> TransactionAuditLog:
    """
    Insert one row into transaction_audit_logs and commit immediately.

    This commits on its own, separate from whatever transaction created or
    updated the Transaction row — callers (e.g. send_money) invoke this
    after their own commit(s) per DEVATTECH-72's step ordering. The table
    is append-only at the database level (trigger added by DEVATTECH-35's
    migration blocks UPDATE/DELETE), so this function only ever inserts —
    there is intentionally no update_audit()/delete_audit() here.
    """
    audit_entry = TransactionAuditLog(
        transaction_id=transaction_id,
        action=action,
        actor_id=actor_id,
        event_metadata=metadata,
    )
    db.add(audit_entry)
    await db.commit()
    await db.refresh(audit_entry)
    return audit_entry


def append_audit_sync(
    db: Session,
    *,
    transaction_id: int,
    action: str,
    actor_id: int | None,
    metadata: dict | None = None,
) -> TransactionAuditLog:
    """Sync equivalent of append_audit() for Celery task code paths."""
    audit_entry = TransactionAuditLog(
        transaction_id=transaction_id,
        action=action,
        actor_id=actor_id,
        event_metadata=metadata,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry
