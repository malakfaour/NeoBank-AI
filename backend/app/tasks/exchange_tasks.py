import json
from decimal import Decimal

import httpx
import redis

from app.celery_app import celery_app
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.model_metrics import ModelMetrics
from app.services.exchange_cache import EXCHANGE_RATES_CACHE_KEY, fetch_exchange_rates
from app.services.exchange_ml_service import train_and_evaluate_models


EXCHANGE_API_URL = "https://open.er-api.com/v6/latest/USD"

EXCHANGE_FORECAST_CACHE_KEY = (
    "exchange:forecast:usd_lbp:7_days"
)


def decimal_to_str_rates(
    rates: dict[tuple[str, str], Decimal],
) -> dict[str, str]:
    return {
        f"{base}:{target}": str(rate)
        for (base, target), rate in rates.items()
    }


def fetch_exchange_rates_sync() -> dict[tuple[str, str], Decimal]:
    """
    Sync exchange-rate fetcher for Celery tasks.
    """

    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            EXCHANGE_API_URL
        )

        response.raise_for_status()

    data = response.json()

    if data.get("result") != "success":
        raise RuntimeError(
            "Exchange rate provider returned unsuccessful response"
        )

    provider_rates = data.get(
        "rates",
        {},
    )

    usd_to_lbp = provider_rates.get("LBP")
    usd_to_eur = provider_rates.get("EUR")

    if usd_to_lbp is None:
        raise RuntimeError(
            "LBP rate was not found"
        )

    rates = {
        ("USD", "LBP"): Decimal(
            str(usd_to_lbp)
        ),
        ("LBP", "USD"): Decimal("1")
        / Decimal(str(usd_to_lbp)),
    }

    if usd_to_eur:
        rates[("USD", "EUR")] = Decimal(
            str(usd_to_eur)
        )

        rates[("EUR", "USD")] = (
            Decimal("1")
            / Decimal(str(usd_to_eur))
        )

    return rates


@celery_app.task(
    name="app.tasks.exchange_tasks.poll_exchange_rates"
)
def poll_exchange_rates():
    rates = fetch_exchange_rates_sync()

    redis_client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    redis_client.setex(
        EXCHANGE_RATES_CACHE_KEY,
        300,
        json.dumps(
            decimal_to_str_rates(rates)
        ),
    )

    return {
        "status": "ok",
        "rates_count": len(rates),
    }


@celery_app.task(
    name="app.tasks.exchange_tasks.retrain_exchange_forecast"
)
def retrain_exchange_forecast():

    rates = fetch_exchange_rates_sync()

    usd_to_lbp = rates.get(
        ("USD", "LBP")
    )

    if usd_to_lbp is None:
        raise RuntimeError(
            "USD/LBP rate unavailable"
        )

    evaluation = train_and_evaluate_models(
        usd_to_lbp
    )

    redis_client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    redis_client.setex(
        EXCHANGE_FORECAST_CACHE_KEY,
        7 * 24 * 60 * 60,
        json.dumps(
            {
                "base_currency": "USD",
                "target_currency": "LBP",
                "model": evaluation["winner"],
            }
        ),
    )

    with SyncSessionLocal() as session:

        for result in evaluation["results"]:

            session.add(
                ModelMetrics(
                    model_name=result["model"],
                    mae=result["mae"],
                )
            )

        session.commit()

    return {
        "status": "ok",
        "winner": evaluation["winner"],
        "metrics_saved": len(
            evaluation["results"]
        ),
    }

# Alias expected by tests
retrain_exchange_forecast_model = retrain_exchange_forecast

async def retrain_exchange_forecast_model():
    from app.db.session import AsyncSessionLocal
    from app.models.model_metrics import ModelMetrics

    rates = await fetch_exchange_rates()
    usd_to_lbp = rates.get(("USD", "LBP"))
    if usd_to_lbp is None:
        raise RuntimeError("USD/LBP rate unavailable")

    from app.services.exchange_forecast import train_evaluate_and_forecast_usd_lbp
    result = train_evaluate_and_forecast_usd_lbp(usd_to_lbp)
    mae = result["mae"]

    async with AsyncSessionLocal() as session:
        session.add(ModelMetrics(model_name="LightGBM", mae=mae))
        await session.commit()

    return {"status": "ok", "mae": mae}
