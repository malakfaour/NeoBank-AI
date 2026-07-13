from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class CurrencyEnum(str, Enum):
    USD = "USD"
    LBP = "LBP"
    USDT = "USDT"


class WalletResponse(BaseModel):
    id: int
    user_id: int
    currency: CurrencyEnum
    balance: float

    class Config:
        from_attributes = True


class WalletStatusEnum(str, Enum):
    active = "active"
    frozen = "frozen"
    closed = "closed"


class WalletStatusChangeResponse(BaseModel):
    wallet_id: int
    status: WalletStatusEnum
    message: str


class CardTopUpRequest(BaseModel):
    wallet_id: int = Field(..., gt=0)
    amount: Decimal = Field(..., gt=0)
    card_token: str = Field(..., min_length=8)


class CardTopUpResponse(BaseModel):
    wallet_id: int
    currency: str
    top_up_amount: Decimal
    new_balance: Decimal
    status: str
    message: str
