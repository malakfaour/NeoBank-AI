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
    # DEVATTECH-131: was `card_token` (a fake "tok_..." string). Now a real
    # Stripe PaymentMethod id (e.g. "pm_1Nx..."), created client-side by
    # Stripe Elements -- the raw card number never reaches this backend.
    payment_method_id: str = Field(..., min_length=8)


class CardTopUpResponse(BaseModel):
    wallet_id: int
    currency: str
    top_up_amount: Decimal
    new_balance: Decimal
    status: str
    message: str
class CardTopUpRequiresActionResponse(BaseModel):
    """
    Returned instead of CardTopUpResponse when Stripe requires a 3D
    Secure challenge before the charge can complete. The wallet has NOT
    been credited yet -- the frontend must run stripe.confirmCardPayment
    (client_secret) and then call POST /accounts/top-up/confirm.
    """
    status: str = "requires_action"
    payment_intent_id: str
    client_secret: str


class ConfirmTopUpRequest(BaseModel):
    wallet_id: int = Field(..., gt=0)
    amount: Decimal = Field(..., gt=0)
    payment_intent_id: str = Field(..., min_length=8)