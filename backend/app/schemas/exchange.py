from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExchangeRateResponse(BaseModel):
    base_currency: str
    target_currency: str
    rate: Decimal
    provider: str | None = None
    last_updated_at: datetime | None = None


class LiveExchangeRateResponse(BaseModel):
    base_currency: str
    target_currency: str
    rate: Decimal
    provider: str | None = None
    last_updated_at: datetime | None = None
    cache_age_seconds: int
    stale: bool = False


class ConvertCurrencyResponse(BaseModel):
    from_currency: str
    to_currency: str
    amount: Decimal
    rate: Decimal
    converted_amount: Decimal


class ExchangeExecutionRequest(BaseModel):
    from_currency: Literal["USD", "LBP"]
    to_currency: Literal["USD", "LBP"]
    amount: Decimal = Field(..., gt=0)


class ExchangeExecutionResponse(BaseModel):
    exchange_id: UUID
    status: str
    from_currency: str
    to_currency: str
    amount: Decimal
    rate: Decimal
    converted_amount: Decimal
    message: str


class ExchangeForecastPoint(BaseModel):
    date: date
    predicted_rate: Decimal


class ExchangeForecastResponse(BaseModel):
    base_currency: str
    target_currency: str
    days: int
    model: str
    predictions: list[ExchangeForecastPoint]
