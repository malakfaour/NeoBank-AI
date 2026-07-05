from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TransferByMobileRequest(BaseModel):
    receiver_phone: str
    amount: Decimal = Field(..., gt=0)
    currency: str  # "USD" | "LBP" | "USDT"


class TransferReceipt(BaseModel):
    transaction_id: int
    amount: Decimal
    currency: str
    receiver_display_name: str
    sender_new_balance: Decimal
    timestamp: datetime


class TransferByIbanRequest(BaseModel):
    receiver_iban: str
    amount: Decimal = Field(..., gt=0)
    currency: str  # "USD" | "LBP" | "USDT"
