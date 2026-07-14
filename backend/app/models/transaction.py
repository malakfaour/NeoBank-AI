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


class ExchangeLegType(str, enum.Enum):
    """
    Ledger fix (Issue 1 of 3, DEVATTECH-92 prerequisite): distinguishes
    the two Transaction rows a currency exchange now writes -- one debit
    (source currency, source amount) and one credit (target currency,
    converted amount) -- so balance reconstruction can identify each leg
    directly from transaction data, without parsing idempotency_key
    strings or joining ExchangeAuditLog.

    NULL for every non-exchange transaction, and for any exchange row
    created before this fix -- historical exchange rows keep
    exchange_leg=NULL rather than being backfilled, per instruction.
    """

    debit = "debit"
    credit = "credit"


class LedgerDirection(str, enum.Enum):
    """
    Ledger fix (Issues 2+3 of 3): explicit typed credit/debit direction
    for Transaction rows where sender_id == receiver_id and the
    direction isn't already implied by ExchangeLegType (Exchange rows).
    Currently used by:
      - Reversal rows (Issue 2): always ledger_direction=credit -- the
        compensating credit-back to the original sender.
      - Adjustment rows (Issue 3): credit or debit, per the admin's
        chosen direction.

    NULL for every other transaction, and for any Reversal/Adjustment
    row created before this fix -- historical rows keep
    ledger_direction=NULL rather than being backfilled, per instruction.
    """

    debit = "debit"
    credit = "credit"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
    Index("ix_transactions_sender_created_at", "sender_id", "created_at"),
    Index("ix_transactions_receiver_created_at", "receiver_id", "created_at"),
    Index("ix_transactions_status", "status"),
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
    # Ledger fix (Issue 1 of 3): nullable, set only on category="Exchange"
    # rows going forward. See ExchangeLegType above.
    exchange_leg = Column(SAEnum(ExchangeLegType), nullable=True)
    # Ledger fix (Issues 2+3 of 3): nullable, set on category="Reversal"
    # (always credit) and category="Adjustment" (credit or debit) rows
    # going forward. See LedgerDirection above.
    ledger_direction = Column(SAEnum(LedgerDirection), nullable=True)
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # NOTE: no back_populates here — User model isn't being modified as part
    # of this ticket. Add sent_transactions / received_transactions on User
    # with matching back_populates if/when that's wired up.
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
