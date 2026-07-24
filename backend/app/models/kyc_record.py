import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class KYCRecordStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    flagged = "flagged"
    rejected = "rejected"


class KYCDocumentType(str, enum.Enum):
    passport = "passport"
    drivers_license = "drivers_license"
    national_id = "national_id"


class KYCRecord(Base):
    __tablename__ = "kyc_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    selfie_url = Column(String(500), nullable=True)
    id_photo_url = Column(String(500), nullable=True)
    document_type = Column(SAEnum(KYCDocumentType), nullable=True)
    match_score = Column(Float, nullable=True)
    liveness_score = Column(Float, nullable=True)
    status = Column(SAEnum(KYCRecordStatus), nullable=False, default=KYCRecordStatus.pending)
    rejection_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="kyc_records", foreign_keys=[user_id])
