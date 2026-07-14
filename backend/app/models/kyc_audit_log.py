from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class KYCAuditLog(Base):
    """Append-only audit trail for KYC review decisions."""

    __tablename__ = "kyc_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    kyc_record_id = Column(
        Integer, ForeignKey("kyc_records.id"), nullable=False, index=True
    )
    action = Column(String(50), nullable=False)
    actor_id = Column(Integer, nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    event_metadata = Column("metadata", JSONB().with_variant(JSON, "sqlite"), nullable=True)

    kyc_record = relationship("KYCRecord")
