import logging
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
from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus, ExchangeLegType
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
from app.core.config import settings
from app.services.exchange_cache import (
    get_cached_exchange_rates,
    get_cached_exchange_rates_with_age,
    set_cached_exchange_rates,
)
from app.services.exchange_forecast import train_and_forecast_usd_lbp
from app.services.market_hours import get_market_status, is_market_open
<<<<<<< HEAD
from app.services.wallet_status import WalletClosedError, WalletFrozenError, assert_wallet_active
from app.tasks.exchange_tasks import fetch_exchange_rates
=======
from app.services.exchange_cache import fetch_exchange_rates
>>>>>>> d3ffa24 (feat(exchange): DEVATTECH-94 DS-2 exchange forecast — dataset, LightGBM+Prophet training, FORECAST_MODEL config, /exchange/forecast serves winner)


router = APIRouter(prefix="/exchange", tags=["exchange"])
logger = logging.getLogger(__name__)


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

    try:
        assert_wallet_active(source_wallet)
    except (WalletFrozenError, WalletClosedError) as e:
        reason = "wallet_frozen" if isinstance(e, WalletFrozenError) else "wallet_closed"
        raise HTTPException(
            status_code=422,
            detail={"error": reason},
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

    try:
        assert_wallet_active(target_wallet)
    except (WalletFrozenError, WalletClosedError) as e:
        reason = "wallet_frozen" if isinstance(e, WalletFrozenError) else "wallet_closed"
        raise HTTPException(
            status_code=422,
            detail={"error": reason},
        )

    converted_amount = payload.amount * rate

    # Move money
    source_wallet.balance -= payload.amount
    target_wallet.balance += converted_amount

    exchange_id = uuid4()

    # Ledger fix (Issue 1 of 3, DEVATTECH-92 prerequisite): TWO Transaction
    # rows now record this exchange -- a debit leg in the source currency
    # and a credit leg in the target currency -- distinguished by
    # exchange_leg, so balance reconstruction can identify each leg
    # directly from transaction data. category="Exchange" is unchanged on
    # both rows, per instruction -- existing category-based logic
    # elsewhere (transactions.py's type derivation/filtering) is
    # untouched and continues to work unmodified. Distinct
    # idempotency_key suffixes (":debit" / ":credit") are required only
    # to satisfy the column's UNIQUE constraint -- nothing reads or
    # parses this suffix; exchange_leg is the actual, reliable signal.
    debit_transaction = Transaction(
        sender_id=user_id,
        receiver_id=user_id,
        amount=payload.amount,
        currency=TransactionCurrency(from_currency),
        category="Exchange",
        status=TransactionStatus.completed,
        exchange_leg=ExchangeLegType.debit,
        idempotency_key=f"exchange:{exchange_id.hex}:debit",
    )
    db.add(debit_transaction)

    credit_transaction = Transaction(
        sender_id=user_id,
        receiver_id=user_id,
        amount=converted_amount,
        currency=TransactionCurrency(to_currency),
        category="Exchange",
        status=TransactionStatus.completed,
        exchange_leg=ExchangeLegType.credit,
        idempotency_key=f"exchange:{exchange_id.hex}:credit",
    )
    db.add(credit_transaction)

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
    await db.refresh(debit_transaction)
    await db.refresh(credit_transaction)

    await invalidate_balance_cache(user_id)
    # Real, separate audit entries for BOTH legs -- one append_audit()
    # call per Transaction, since TransactionAuditLog.transaction_id is a
    # required, single-target FK (one entry cannot cover two
    # transactions). Without this, GET /admin/transactions/{id}/audit-trail
    # for the credit leg's id would return zero rows -- confirmed gap,
    # fixed here. Each entry's metadata records which leg it is and the
    # paired transaction's id, so either leg's audit trail can be traced
    # to its counterpart.
    #
    # Both calls are best-effort follow-ups, same convention as
    # bills.py's pay_bill and admin.py's resolve_flag: append_audit()
    # commits internally/independently of the exchange's own commit
    # above, so by this point the exchange has ALREADY succeeded and is
    # durably committed. An uncaught exception in either audit write must
    # not surface as a 500 to the client for a request that actually
    # succeeded -- that would falsely tell the user their exchange
    # failed and could invite a duplicate attempt. Logged at ERROR level
    # for manual follow-up instead of propagating.
    try:
        await append_audit(
            db,
            transaction_id=debit_transaction.id,
            action="exchange_completed",
            actor_id=user_id,
            metadata={
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate": str(rate),
                "converted_amount": str(converted_amount),
                "leg": "debit",
                "paired_transaction_id": credit_transaction.id,
            },
        )
    except Exception:
        logger.error(
            "Exchange %s succeeded but debit-leg audit write failed for "
            "transaction %s (user %s). Manual audit backfill may be required.",
            exchange_id, debit_transaction.id, user_id,
            exc_info=True,
        )

    try:
        await append_audit(
            db,
            transaction_id=credit_transaction.id,
            action="exchange_completed",
            actor_id=user_id,
            metadata={
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate": str(rate),
                "converted_amount": str(converted_amount),
                "leg": "credit",
                "paired_transaction_id": debit_transaction.id,
            },
        )
    except Exception:
        logger.error(
            "Exchange %s succeeded but credit-leg audit write failed for "
            "transaction %s (user %s). Manual audit backfill may be required.",
            exchange_id, credit_transaction.id, user_id,
            exc_info=True,
        )

    # Response shape is UNCHANGED -- ExchangeExecutionResponse is not
    # modified, per instruction. The two transaction ids exist in the DB
    # and in the audit metadata above; DEVATTECH-92 reads directly from
    # the DB, not through this response.
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