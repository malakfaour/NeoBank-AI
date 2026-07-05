from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class TransactionAuditLog(Base):
    """
    Append-only audit trail for transactions (DEVATTECH-35).

    UPDATE and DELETE on this table are blocked at the DB level by a
    trigger created in the migration — this model has no update/delete
    helpers on purpose. Rows should only ever be inserted.
    """

    __tablename__ = "transaction_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    # No FK — may reference a user, or a system/service actor (e.g. a Celery
    # job or compliance process) that isn't a row in `users`.
    actor_id = Column(Integer, nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Column is named "metadata" in the DB; "metadata" can't be used as the
    # Python attribute name since it's reserved by Base.metadata.
    event_metadata = Column("metadata", JSONB().with_variant(JSON, "sqlite"), nullable=True)

    transaction = relationship("Transaction")
