from decimal import Decimal
from pydantic import BaseModel, Field


class SendMoneyRequest(BaseModel):
    receiver_id: str
    amount: Decimal = Field(..., gt=0)
    currency: str  # "USD" | "LBP" | "USDT"


class SendMoneyResponse(BaseModel):
    transaction_id: int
    status: str
    amount: Decimal
    currency: str
    sender_id: int
    receiver_id: int
    fraud_score: float | None = None
