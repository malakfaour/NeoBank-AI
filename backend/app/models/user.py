import enum
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


def default_notification_preferences() -> dict[str, bool]:
    return {"email": True, "push": True, "sms": True}


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
    avatar_url = Column(String(500), nullable=True)
    password_hash = Column(String(255), nullable=False)
    kyc_status = Column(SAEnum(KYCStatus), nullable=False, default=KYCStatus.pending)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.customer)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    passcode_hash = Column(String(255), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    notification_preferences = Column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=default_notification_preferences,
    )

    kyc_records = relationship(
        "KYCRecord",
        back_populates="user",
        foreign_keys="KYCRecord.user_id",
    )
    sessions = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    wallets = relationship(
        "Wallet", back_populates="user", cascade="all, delete-orphan"
    )
    beneficiaries = relationship(
        "Beneficiary", back_populates="user", cascade="all, delete-orphan"
    )
    notifications = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    push_subscriptions = relationship(
        "PushSubscription", back_populates="user", cascade="all, delete-orphan"
    )
    device_credentials = relationship(
        "DeviceCredential", back_populates="user", cascade="all, delete-orphan"
    )
