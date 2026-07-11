from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.cache_utils import invalidate_balance_cache
from app.api.dependencies import require_action_token
from app.db.session import get_db
from app.models.exchange_audit_log import ExchangeAuditLog
from app.models.exchange_rate import ExchangeRate
from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.exchange import (
    ConvertCurrencyResponse,
    ExchangeExecutionRequest,
    ExchangeExecutionResponse,
    ExchangeForecastResponse,
    LiveExchangeRateResponse,
    ExchangeRateResponse,
)
from app.schemas.user import CurrentUser
from app.services.audit_log import append_audit
from app.services.exchange_cache import (
    get_cached_exchange_rates,
    get_cached_exchange_rates_with_age,
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


@router.get("/rates/live", response_model=LiveExchangeRateResponse)
async def get_live_exchange_rate(
    from_currency: str = Query(..., min_length=3, max_length=3),
    to_currency: str = Query(..., min_length=3, max_length=3),
    db: AsyncSession = Depends(get_db),
):
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    cached_rates, cache_age_seconds = await get_cached_exchange_rates_with_age()
    if cached_rates is not None:
        rate = cached_rates.get((from_currency, to_currency))
        if rate is None:
            raise HTTPException(
                status_code=404,
                detail=f"Exchange pair {from_currency}->{to_currency} is not supported",
            )

        return {
            "base_currency": from_currency,
            "target_currency": to_currency,
            "rate": rate,
            "provider": "redis-cache",
            "last_updated_at": None,
            "cache_age_seconds": cache_age_seconds or 0,
        }

    latest_db_rate = await db.scalar(
        select(ExchangeRate)
        .where(
            ExchangeRate.base_currency == from_currency,
            ExchangeRate.target_currency == to_currency,
        )
        .order_by(ExchangeRate.last_updated_at.desc())
        .limit(1)
    )
    if latest_db_rate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Exchange pair {from_currency}->{to_currency} is not supported",
        )

    last_updated_at = latest_db_rate.last_updated_at
    if last_updated_at.tzinfo is None:
        last_updated_at = last_updated_at.replace(tzinfo=timezone.utc)

    cache_age_seconds = max(
        0,
        int((datetime.now(timezone.utc) - last_updated_at).total_seconds()),
    )

    return {
        "base_currency": latest_db_rate.base_currency,
        "target_currency": latest_db_rate.target_currency,
        "rate": latest_db_rate.rate,
        "provider": latest_db_rate.provider,
        "last_updated_at": last_updated_at,
        "cache_age_seconds": cache_age_seconds,
    }


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
    current_user: CurrentUser = Depends(require_action_token),
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

    user_id = int(current_user.id)

    try:
        from_wallet_currency = WalletCurrency(from_currency)
        to_wallet_currency = WalletCurrency(to_currency)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Unsupported currency",
        )

    locked_wallets_result = await db.execute(
        select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.currency.in_([from_wallet_currency, to_wallet_currency]),
        )
        .order_by(Wallet.id.asc())
        .with_for_update()
    )
    wallets_by_currency = {wallet.currency: wallet for wallet in locked_wallets_result.scalars().all()}
    source_wallet = wallets_by_currency.get(from_wallet_currency)
    target_wallet = wallets_by_currency.get(to_wallet_currency)

    if source_wallet is None:
        raise HTTPException(
            status_code=404,
            detail=f"{from_currency} wallet not found",
        )

    if source_wallet.balance < payload.amount:
        raise HTTPException(
            status_code=422,
            detail="Insufficient balance",
        )

    if target_wallet is None:
        raise HTTPException(
            status_code=404,
            detail=f"{to_currency} wallet not found",
        )

    converted_amount = payload.amount * rate

    # Move money
    source_wallet.balance -= payload.amount
    target_wallet.balance += converted_amount

    exchange_id = uuid4()
    transaction = Transaction(
        sender_id=user_id,
        receiver_id=user_id,
        amount=payload.amount,
        currency=TransactionCurrency(from_currency),
        category="Exchange",
        status=TransactionStatus.completed,
        idempotency_key=f"exchange:{exchange_id.hex}",
    )
    db.add(transaction)

    audit_log = ExchangeAuditLog(
        exchange_id=str(exchange_id),
        user_id=user_id,
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
    await db.refresh(transaction)

    await invalidate_balance_cache(user_id)
    await append_audit(
        db,
        transaction_id=transaction.id,
        action="exchange_completed",
        actor_id=user_id,
        metadata={
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": str(rate),
            "converted_amount": str(converted_amount),
        },
    )

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
