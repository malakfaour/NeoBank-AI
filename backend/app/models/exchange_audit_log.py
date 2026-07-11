from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.sql import func

from app.db.base import Base


class ExchangeAuditLog(Base):
    __tablename__ = "exchange_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    exchange_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)

    amount = Column(Numeric(18, 4), nullable=False)
    rate = Column(Numeric(18, 8), nullable=False)
    converted_amount = Column(Numeric(18, 4), nullable=False)

    status = Column(String(30), nullable=False, default="executed")
    provider = Column(String(100), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
