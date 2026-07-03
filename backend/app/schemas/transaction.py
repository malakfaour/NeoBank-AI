from datetime import datetime
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


# --- DEVATTECH-73: transaction history / detail / summary ---


class TransactionListItem(BaseModel):
    id: int
    type: str  # "send" | "receive" (see DEVATTECH-73 notes: topup/bill/exchange not yet derivable)
    amount: Decimal
    currency: str
    counterparty_name: str | None
    category: str | None
    fraud_score: float | None
    rule_triggered: str | None  # always None for now — fraud_flags table doesn't exist yet
    status: str
    created_at: datetime
    flagged: bool  # derived from status == "flagged", not a fraud_flags table (doesn't exist yet)


class TransactionListResponse(BaseModel):
    items: list[TransactionListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class TransactionAuditLogItem(BaseModel):
    id: int
    action: str
    actor_id: int | None
    timestamp: datetime
    metadata: dict | None


class TransactionDetailResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    type: str
    amount: Decimal
    currency: str
    counterparty_name: str | None
    category: str | None
    fraud_score: float | None
    rule_triggered: str | None
    status: str
    flagged: bool
    created_at: datetime
    audit_logs: list[TransactionAuditLogItem]


class CategorySummaryItem(BaseModel):
    category: str | None
    # NOTE: currency is included even though the ticket's literal shape
    # didn't list it — grouping by category alone would sum different
    # currencies (USD/LBP/USDT) into one meaningless total. See
    # DEVATTECH-73 notes.
    currency: str
    total_amount: Decimal
    transaction_count: int


class TransactionSummaryResponse(BaseModel):
    month: str
    summary: list[CategorySummaryItem]
