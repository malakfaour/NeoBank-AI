from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class BillPayRequest(BaseModel):
    bill_type: Literal[
        "ogero",
        "edl",
        "water",
        "mobile_topup",
    ]

    bill_reference: str

    amount: Decimal = Field(
        ...,
        gt=0,
    )

    currency: Literal[
        "USD",
        "LBP",
        "USDT",
    ]

    from_wallet_id: int


class BillPayResponse(BaseModel):
    bill_payment_id: int
    status: str
    bill_type: str
    bill_reference: str
    amount: Decimal
    currency: str
    transaction_id: int | None


class BillHistoryItem(BaseModel):
    id: int
    bill_type: str
    bill_reference: str
    amount: Decimal
    currency: str
    status: str
    biller_error: str | None
    paid_at: datetime


class BillHistoryResponse(BaseModel):
    items: list[BillHistoryItem]
    page: int
    page_size: int
    total: int
    total_pages: int