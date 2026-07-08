from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class AccountStatusAuditLog(Base):
    """
    Append-only audit trail for wallet lifecycle events (freeze/unfreeze/
    close) -- DEVATTECH-104.

    UPDATE and DELETE on this table are blocked at the DB level by a
    trigger created in migration 1e652f5a22fd -- this model has no
    update/delete helpers on purpose. Rows should only ever be inserted.

    Separate from TransactionAuditLog because transaction_audit_logs.
    transaction_id is NOT NULL and these events are not transactions.
    """

    __tablename__ = "account_status_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    actor_id = Column(Integer, nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    event_metadata = Column("metadata", JSONB().with_variant(JSON, "sqlite"), nullable=True)

    wallet = relationship("Wallet")
