import asyncio
import json
from decimal import Decimal

import httpx
import redis

from app.celery_app import celery_app
from app.core.config import settings
from app.services.exchange_cache import EXCHANGE_RATES_CACHE_KEY
from app.services.exchange_forecast import train_and_forecast_usd_lbp
from app.db.sync_session import SyncSessionLocal
from app.models.model_metrics import ModelMetrics

EXCHANGE_API_URL = "https://open.er-api.com/v6/latest/USD"
EXCHANGE_FORECAST_CACHE_KEY = "exchange:forecast:usd_lbp:7_days"


def decimal_to_str_rates(rates: dict[tuple[str, str], Decimal]) -> dict[str, str]:
    return {f"{base}:{target}": str(rate) for (base, target), rate in rates.items()}


async def fetch_exchange_rates() -> dict[tuple[str, str], Decimal]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(EXCHANGE_API_URL)
        response.raise_for_status()

    data = response.json()

    if data.get("result") != "success":
        raise RuntimeError("Exchange rate provider returned an unsuccessful response")

    provider_rates = data.get("rates", {})

    usd_to_lbp = provider_rates.get("LBP")
    usd_to_eur = provider_rates.get("EUR")

    if usd_to_lbp is None:
        raise RuntimeError("LBP rate was not found in provider response")

    rates: dict[tuple[str, str], Decimal] = {
        ("USD", "LBP"): Decimal(str(usd_to_lbp)),
        ("LBP", "USD"): Decimal("1") / Decimal(str(usd_to_lbp)),
    }

    if usd_to_eur is not None:
        rates[("USD", "EUR")] = Decimal(str(usd_to_eur))
        rates[("EUR", "USD")] = Decimal("1") / Decimal(str(usd_to_eur))

    return rates


async def refresh_exchange_rates_cache() -> dict[str, object]:
    rates = await fetch_exchange_rates()

    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    redis_client.setex(
        EXCHANGE_RATES_CACHE_KEY,
        300,
        json.dumps(decimal_to_str_rates(rates)),
    )

    return {
        "status": "ok",
        "message": "Exchange rates cache refreshed from real provider",
        "rates_count": len(rates),
        "provider": "open.er-api.com",
    }


async def retrain_exchange_forecast_model() -> dict[str, object]:
    rates = await fetch_exchange_rates()

    usd_to_lbp = rates.get(("USD", "LBP"))

    if usd_to_lbp is None:
        raise RuntimeError("USD to LBP rate was not found for forecast training")

    predictions = train_and_forecast_usd_lbp(usd_to_lbp, days=7)

    serialized_predictions = [
        {
            "date": str(item["date"]),
            "predicted_rate": str(item["predicted_rate"]),
        }
        for item in predictions
    ]

    # -------------------------------
    # SAVE MODEL METRICS (SAFE)
    # -------------------------------
    db = SyncSessionLocal()
    try:
        mae_value = 0.0  # placeholder until model returns real MAE

        metric = ModelMetrics(
            model_name="LightGBM",
            mae=float(mae_value),
        )

        db.add(metric)
        db.commit()

    finally:
        db.close()

    # -------------------------------
    # CACHE FORECAST
    # -------------------------------
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    redis_client.setex(
        EXCHANGE_FORECAST_CACHE_KEY,
        7 * 24 * 60 * 60,
        json.dumps(
            {
                "base_currency": "USD",
                "target_currency": "LBP",
                "days": 7,
                "model": "LightGBM",
                "predictions": serialized_predictions,
            }
        ),
    )

    return {
        "status": "ok",
        "message": "Exchange forecast model retrained successfully",
        "model": "LightGBM",
        "predictions_count": len(predictions),
        "cache_key": EXCHANGE_FORECAST_CACHE_KEY,
    }


@celery_app.task(name="app.tasks.exchange_tasks.poll_exchange_rates")
def poll_exchange_rates():
    return asyncio.run(refresh_exchange_rates_cache())


@celery_app.task(name="app.tasks.exchange_tasks.retrain_exchange_forecast")
def retrain_exchange_forecast():
    return asyncio.run(retrain_exchange_forecast_model())