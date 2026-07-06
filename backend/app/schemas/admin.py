from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class FlaggedTransactionItem(BaseModel):
    id: int
    sender_id: int
    sender_name: str
    sender_email: str
    amount: Decimal
    currency: str
    fraud_score: float | None
    scoring_model: str | None
    status: str
    created_at: datetime


class FlaggedTransactionsResponse(BaseModel):
    items: list[FlaggedTransactionItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class ResolveFlagRequest(BaseModel):
    resolution: Literal["legitimate", "confirmed_fraud"]
    reviewer_note: str | None = None


class ResolveFlagResponse(BaseModel):
    transaction_id: int
    resolution: str
    new_status: str
    reviewer_id: int
    resolved_at: datetime


class ResolutionCounts(BaseModel):
    legitimate: int
    confirmed_fraud: int


class ReversedAmountByCurrency(BaseModel):
    currency: str
    total_amount: Decimal
    count: int


class ComplianceSummaryResponse(BaseModel):
    month: str
    total_transactions_created: int
    currently_flagged_from_month: int
    resolutions_this_month: ResolutionCounts
    reversed_amount_by_currency: list[ReversedAmountByCurrency]
