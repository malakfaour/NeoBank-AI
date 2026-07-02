from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.schemas.exchange import (
    ConvertCurrencyResponse,
    ExchangeExecutionRequest,
    ExchangeExecutionResponse,
    ExchangeRateResponse,
)
from app.services.exchange_cache import (
    get_cached_exchange_rates,
    set_cached_exchange_rates,
)
from app.services.market_hours import get_market_status, is_market_open
from app.tasks.exchange_tasks import fetch_exchange_rates


router = APIRouter(prefix="/exchange", tags=["exchange"])


async def get_rates_from_cache_or_provider() -> dict[tuple[str, str], Decimal]:
    cached_rates = await get_cached_exchange_rates()

    if cached_rates is not None:
        return cached_rates

    rates = await fetch_exchange_rates()
    await set_cached_exchange_rates(rates)

    return rates


@router.get("/market-status")
async def market_status():
    return get_market_status()


@router.get("/rates", response_model=list[ExchangeRateResponse])
async def get_exchange_rates():
    cached_rates = await get_cached_exchange_rates()

    if cached_rates is None:
        rates = await fetch_exchange_rates()
        await set_cached_exchange_rates(rates)
        provider = "open.er-api.com"
    else:
        rates = cached_rates
        provider = "redis-cache"

    return [
        {
            "base_currency": base,
            "target_currency": target,
            "rate": rate,
            "provider": provider,
            "last_updated_at": None,
        }
        for (base, target), rate in rates.items()
    ]


@router.get("/convert", response_model=ConvertCurrencyResponse)
async def convert_currency(
    amount: Decimal = Query(..., gt=0),
    from_currency: str = Query(..., min_length=3, max_length=3),
    to_currency: str = Query(..., min_length=3, max_length=3),
):
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if not is_market_open():
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Exchange market is currently closed",
                **get_market_status(),
            },
        )

    if from_currency == to_currency:
        raise HTTPException(
            status_code=400,
            detail="from_currency and to_currency cannot be the same",
        )

    rates = await get_rates_from_cache_or_provider()

    rate = rates.get((from_currency, to_currency))

    if rate is None:
        raise HTTPException(
            status_code=400,
            detail=f"Exchange pair {from_currency}->{to_currency} is not supported",
        )

    converted_amount = amount * rate

    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "amount": amount,
        "rate": rate,
        "converted_amount": converted_amount,
    }


@router.post("/execute", response_model=ExchangeExecutionResponse)
async def execute_exchange(payload: ExchangeExecutionRequest):
    from_currency = payload.from_currency.upper()
    to_currency = payload.to_currency.upper()

    if not is_market_open():
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Exchange market is currently closed",
                **get_market_status(),
            },
        )

    if from_currency == to_currency:
        raise HTTPException(
            status_code=400,
            detail="from_currency and to_currency cannot be the same",
        )

    rates = await get_rates_from_cache_or_provider()

    rate = rates.get((from_currency, to_currency))

    if rate is None:
        raise HTTPException(
            status_code=400,
            detail=f"Exchange pair {from_currency}->{to_currency} is not supported",
        )

    converted_amount = payload.amount * rate

    return {
        "exchange_id": uuid4(),
        "status": "executed",
        "from_currency": from_currency,
        "to_currency": to_currency,
        "amount": payload.amount,
        "rate": rate,
        "converted_amount": converted_amount,
        "message": "Exchange executed successfully",
    }