from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


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
    flagged_rate: float
    resolutions_this_month: ResolutionCounts
    reversed_amount_by_currency: list[ReversedAmountByCurrency]


class ExchangeAuditLogItem(BaseModel):
    id: int
    exchange_id: str
    user_id: int | None
    user_full_name: str | None
    user_email: str | None
    from_currency: str
    to_currency: str
    amount: Decimal
    rate: Decimal
    converted_amount: Decimal
    status: str
    provider: str | None
    created_at: datetime


class ExchangeAuditLogPageResponse(BaseModel):
    items: list[ExchangeAuditLogItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class ModelMetricItem(BaseModel):
    model_name: str
    mae: float
    trained_at: datetime


class AdminUserSearchItem(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    kyc_status: str
    role: str


class AdminUserSearchResponse(BaseModel):
    items: list[AdminUserSearchItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminWalletItem(BaseModel):
    id: int
    currency: str
    balance: Decimal
    account_number: str | None
    iban: str | None


class AdminUserWalletsResponse(BaseModel):
    user_id: int
    items: list[AdminWalletItem]


class AdminWalletAdjustRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    direction: Literal["credit", "debit"]
    reason: str = Field(..., min_length=1, max_length=500)


class AdminWalletAdjustResponse(BaseModel):
    wallet_id: int
    transaction_id: int
    direction: str
    amount: Decimal
    new_balance: Decimal
    reason: str
