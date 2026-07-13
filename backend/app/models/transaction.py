import enum

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class TransactionCurrency(str, enum.Enum):
    USD = "USD"
    LBP = "LBP"
    USDT = "USDT"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    flagged = "flagged"
    reversed = "reversed"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_sender_created_at", "sender_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(SAEnum(TransactionCurrency), nullable=False)
    # Populated later by spending-categorization ML feature (DEVATTECH-86).
    # Free text for now — category taxonomy isn't finalized yet.
    category = Column(String(50), nullable=True)
    # Populated by the fraud-scoring Celery job (DEVATTECH-41 / DEVATTECH-75).
    fraud_score = Column(Float, nullable=True)
    # Which model produced fraud_score: 'isolation_forest' (cold-start,
    # < 5 prior transactions) or 'xgboost' (DEVATTECH-84 / NBL-109).
    scoring_model = Column(String(50), nullable=True)
    status = Column(SAEnum(TransactionStatus), nullable=False, default=TransactionStatus.pending)
    # DEVATTECH-87: set True if any deterministic fraud rule (1-3) fired.
    # Independent of fraud_score/scoring_model -- see fraud_rules.py.
    rule_triggered = Column(Boolean, nullable=False, default=False)
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # NOTE: no back_populates here — User model isn't being modified as part
    # of this ticket. Add sent_transactions / received_transactions on User
    # with matching back_populates if/when that's wired up.
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

