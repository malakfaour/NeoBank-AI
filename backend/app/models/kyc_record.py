import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.db.base import Base


class KYCRecordStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    flagged = "flagged"
    rejected = "rejected"


class KYCRecord(Base):
    __tablename__ = "kyc_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    selfie_url = Column(String(500), nullable=True)
    id_photo_url = Column(String(500), nullable=True)
    match_score = Column(Float, nullable=True)
    status = Column(SAEnum(KYCRecordStatus), nullable=False, default=KYCRecordStatus.pending)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="kyc_records")
