import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BeneficiaryType(str, enum.Enum):
    MOBILE = "mobile"
    IBAN = "iban"
    BANK_ACCOUNT = "bank_account"


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    nickname: Mapped[str] = mapped_column(String(100), nullable=False)

    type: Mapped[BeneficiaryType] = mapped_column(
        Enum(BeneficiaryType, name="beneficiary_type"),
        nullable=False,
    )

    value: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )