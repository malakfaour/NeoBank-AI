from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.session import get_db
from app.models.exchange_audit_log import ExchangeAuditLog
from app.schemas.exchange import (
    ConvertCurrencyResponse,
    ExchangeExecutionRequest,
    ExchangeExecutionResponse,
    ExchangeForecastResponse,
    ExchangeRateResponse,
)
from app.services.exchange_cache import (
    get_cached_exchange_rates,
    set_cached_exchange_rates,
)
from app.services.exchange_forecast import train_and_forecast_usd_lbp
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
async def execute_exchange(
    payload: ExchangeExecutionRequest,
    db: AsyncSession = Depends(get_db),
):
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

    exchange_id = uuid4()
    converted_amount = payload.amount * rate

    audit_log = ExchangeAuditLog(
        exchange_id=str(exchange_id),
        from_currency=from_currency,
        to_currency=to_currency,
        amount=payload.amount,
        rate=rate,
        converted_amount=converted_amount,
        status="executed",
        provider="open.er-api.com/redis-cache",
    )

    db.add(audit_log)
    await db.commit()

    return {
        "exchange_id": exchange_id,
        "status": "executed",
        "from_currency": from_currency,
        "to_currency": to_currency,
        "amount": payload.amount,
        "rate": rate,
        "converted_amount": converted_amount,
        "message": "Exchange executed successfully",
    }


@router.get("/forecast", response_model=ExchangeForecastResponse)
async def forecast_exchange_rate(days: int = Query(7, ge=1, le=7)):
    rates = await get_rates_from_cache_or_provider()

    latest_rate = rates.get(("USD", "LBP"))

    if latest_rate is None:
        raise HTTPException(
            status_code=400,
            detail="USD to LBP rate is not available for forecasting",
        )

    predictions = await run_in_threadpool(
        train_and_forecast_usd_lbp,
        latest_rate,
        days,
    )

    return {
        "base_currency": "USD",
        "target_currency": "LBP",
        "days": days,
        "model": "LightGBM",
        "predictions": predictions,
    }