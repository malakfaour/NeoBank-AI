from sqlalchemy import Column, Integer, String, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True, index=True)

    base_currency = Column(String(3), nullable=False, index=True)
    target_currency = Column(String(3), nullable=False, index=True)

    rate = Column(Numeric(18, 6), nullable=False)

    provider = Column(String(50), nullable=True)

    last_updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "target_currency",
            name="uq_exchange_rate_pair",
        ),
    )
