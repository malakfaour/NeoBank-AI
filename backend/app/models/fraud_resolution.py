import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class FraudResolutionType(str, enum.Enum):
    legitimate = "legitimate"
    confirmed_fraud = "confirmed_fraud"


class FraudResolution(Base):
    """
    NBL-111: compliance resolution record for a flagged transaction.

    Kept as its own table rather than adding columns to Transaction, so
    that models/transaction.py (and the DEVATTECH-72/73/74/75 logic built
    on it) stays completely untouched.

    One resolution per transaction -- transaction_id is unique, so a
    second resolution attempt on an already-resolved transaction fails at
    the DB level rather than silently creating a duplicate/conflicting
    record.

    Not append-only/audit-enforced at the DB level like
    transaction_audit_logs -- this is a compliance record, not the audit
    trail itself (the audit trail entry for the reversal action goes
    through append_audit(), same as everywhere else).
    """

    __tablename__ = "fraud_resolutions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(
        Integer, ForeignKey("transactions.id"), nullable=False, unique=True, index=True
    )
    resolution = Column(SAEnum(FraudResolutionType), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reviewer_note = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    transaction = relationship("Transaction")
    reviewer = relationship("User")
