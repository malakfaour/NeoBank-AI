import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.wallet import WalletCurrency


class BillType(str, enum.Enum):
    ogero = "ogero"
    edl = "edl"
    water = "water"
    mobile_topup = "mobile_topup"


class BillPaymentStatus(str, enum.Enum):
    success = "success"
    failed = "failed"


class BillPayment(Base):
    __tablename__ = "bill_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False, index=True)
    bill_type = Column(SAEnum(BillType), nullable=False, index=True)
    bill_reference = Column(String(100), nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(SAEnum(WalletCurrency), nullable=False)
    status = Column(SAEnum(BillPaymentStatus), nullable=False)
    biller_error = Column(String(255), nullable=True)
    # Populated only on success -- links to the Transaction row recording
    # the actual debit. NULL for failed payments (no debit, no Transaction
    # row created).
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    paid_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")
    wallet = relationship("Wallet")
    transaction = relationship("Transaction")
