import asyncio
import json
from decimal import Decimal

import httpx
import redis

from app.celery_app import celery_app
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.model_metrics import ModelMetrics
from app.services.exchange_cache import (
    EXCHANGE_RATES_CACHE_KEY,
    fetch_exchange_rates,
)
from app.services.exchange_ml_service import (
    train_and_evaluate_models,
)


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
    Sync exchange-rate fetcher for Celery polling task.
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


async def save_model_metrics(
    results: list[dict],
):
    async with AsyncSessionLocal() as session:

        for result in results:
            session.add(
                ModelMetrics(
                    model_name=result["model"],
                    mae=result["mae"],
                )
            )

        await session.commit()


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

    # Async provider fetch used because tests/mock expect it
    rates = asyncio.run(
        fetch_exchange_rates()
    )

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

    asyncio.run(
        save_model_metrics(
            evaluation["results"]
        )
    )

    return {
        "status": "ok",
        "winner": evaluation["winner"],
        "metrics_saved": len(
            evaluation["results"]
        ),
    }


async def retrain_exchange_forecast_model():
    rates = await fetch_exchange_rates()

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

    await save_model_metrics(
        evaluation["results"]
    )

    return {
    "status": "ok",
    "winner": evaluation["winner"],
    "mae": min(
        result["mae"]
        for result in evaluation["results"]
    ),
    "metrics_saved": len(
        evaluation["results"]
    ),
}