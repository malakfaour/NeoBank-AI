import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class KYCStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    flagged = "flagged"
    rejected = "rejected"


class UserRole(str, enum.Enum):
    customer = "customer"
    compliance_officer = "compliance_officer"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    kyc_status = Column(SAEnum(KYCStatus), nullable=False, default=KYCStatus.pending)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.customer)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    passcode_hash = Column(String(255), nullable=True)

    kyc_records = relationship("KYCRecord", back_populates="user")
    wallets = relationship("Wallet", back_populates="user", cascade="all, delete-orphan")