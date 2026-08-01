import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import redis
from sqlalchemy import select

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
from app.services.exchange_forecast import (
    train_and_forecast_usd_lbp,
)
from app.services.model_artifact import (
    backup_current_model,
    atomic_save,
    rollback_model,
)


EXCHANGE_API_URL = "https://open.er-api.com/v6/latest/USD"

EXCHANGE_FORECAST_CACHE_KEY = (
    "exchange:forecast:usd_lbp:7_days"
)

BEAT_LAST_RUN_KEY = "beat:last_run"


def decimal_to_str_rates(
    rates: dict[tuple[str, str], Decimal],
) -> dict[str, str]:
    return {
        f"{base}:{target}": str(rate)
        for (base, target), rate in rates.items()
    }


def fetch_exchange_rates_sync() -> dict[tuple[str, str], Decimal]:

    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            EXCHANGE_API_URL
        )

        response.raise_for_status()

    data = response.json()

    if data.get("result") != "success":
        raise RuntimeError(
            "Exchange provider failed"
        )

    provider_rates = data.get(
        "rates",
        {},
    )

    usd_to_lbp = provider_rates.get("LBP")

    if usd_to_lbp is None:
        raise RuntimeError(
            "LBP rate missing"
        )

    rates = {
        ("USD", "LBP"): Decimal(
            str(usd_to_lbp)
        ),
        ("LBP", "USD"): Decimal("1")
        / Decimal(str(usd_to_lbp)),
    }

    return rates


def update_beat_heartbeat():

    redis_client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    redis_client.setex(
        BEAT_LAST_RUN_KEY,
        7 * 24 * 60 * 60,
        datetime.now(
            timezone.utc
        ).isoformat(),
    )


async def get_previous_mae():

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(ModelMetrics)
            .where(
                ModelMetrics.model_name == "LightGBM"
            )
            .order_by(
                ModelMetrics.trained_at.desc()
            )
            .limit(1)
        )

        row = result.scalar_one_or_none()

        if row is None:
            return None

        return row.mae


async def apply_model_safety(
    new_mae: float,
) -> str:

    previous_mae = await get_previous_mae()

    backup_current_model()

    if (
        previous_mae is not None
        and new_mae > previous_mae * 1.2
    ):
        rollback_model()
        return "rollback"

    atomic_save()

    return "accepted"


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

    rates = asyncio.run(
        fetch_exchange_rates()
    )

    usd_to_lbp = rates.get(
        ("USD", "LBP")
    )

    if usd_to_lbp is None:
        raise RuntimeError(
            "USD/LBP unavailable"
        )

    evaluation = train_and_evaluate_models(
        usd_to_lbp
    )

    predictions = train_and_forecast_usd_lbp(
        usd_to_lbp,
        days=7,
        model_name=evaluation["winner"],
    )

    new_mae = min(
        item["mae"]
        for item in evaluation["results"]
    )

    model_status = asyncio.run(
        apply_model_safety(
            new_mae
        )
    )

    update_beat_heartbeat()

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
                "days": 7,
                "model": evaluation["winner"],
                "mae": new_mae,
                "model_status": model_status,
                "predictions": [
                    {
                        "date": str(item["date"]),
                        "predicted_rate": str(
                            item["predicted_rate"]
                        ),
                    }
                    for item in predictions
                ],
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
        "mae": new_mae,
        "model_status": model_status,
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
            "USD/LBP unavailable"
        )

    evaluation = train_and_evaluate_models(
        usd_to_lbp
    )

    predictions = train_and_forecast_usd_lbp(
        usd_to_lbp,
        days=7,
        model_name=evaluation["winner"],
    )

    new_mae = min(
        result["mae"]
        for result in evaluation["results"]
    )

    model_status = await apply_model_safety(
        new_mae
    )

    redis_client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    redis_client.setex(
        BEAT_LAST_RUN_KEY,
        7 * 24 * 60 * 60,
        datetime.now(
            timezone.utc
        ).isoformat(),
    )

    redis_client.setex(
        EXCHANGE_FORECAST_CACHE_KEY,
        7 * 24 * 60 * 60,
        json.dumps(
            {
                "base_currency": "USD",
                "target_currency": "LBP",
                "days": 7,
                "model": evaluation["winner"],
                "mae": new_mae,
                "model_status": model_status,
                "predictions": [
                    {
                        "date": str(item["date"]),
                        "predicted_rate": str(
                            item["predicted_rate"]
                        ),
                    }
                    for item in predictions
                ],
            }
        ),
    )

    await save_model_metrics(
        evaluation["results"]
    )

    return {
        "status": "ok",
        "winner": evaluation["winner"],
        "mae": new_mae,
        "model_status": model_status,
        "metrics_saved": len(
            evaluation["results"]
        ),
    }
