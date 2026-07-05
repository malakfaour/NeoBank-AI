import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class WalletCurrency(str, enum.Enum):
    USD = "USD"
    LBP = "LBP"
    USDT = "USDT"


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    currency = Column(SAEnum(WalletCurrency), nullable=False)
    balance = Column(Numeric(18, 4), nullable=False, default=0, server_default="0")
    account_number = Column(String(16), unique=True, nullable=True)
    iban = Column(String(34), unique=True, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="wallets")

    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_wallet_user_currency"),
    )
