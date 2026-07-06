import json
from decimal import Decimal
from typing import Any

from app.core.redis import redis_client

EXCHANGE_RATES_CACHE_KEY = "exchange:rates"
EXCHANGE_LATEST_CACHE_KEY = "exchange:latest"


def decimal_to_str_rates(
    rates: dict[tuple[str, str], Decimal],
) -> dict[str, str]:
    return {
        f"{base}:{target}": str(rate)
        for (base, target), rate in rates.items()
    }


def str_to_decimal_rates(
    data: dict[str, str],
) -> dict[tuple[str, str], Decimal]:
    result = {}

    for pair, rate in data.items():
        base, target = pair.split(":")
        result[(base, target)] = Decimal(rate)

    return result


async def get_cached_exchange_rates():
    cached_data = await redis_client.get(
        EXCHANGE_RATES_CACHE_KEY
    )

    if not cached_data:
        return None

    return str_to_decimal_rates(
        json.loads(cached_data)
    )


async def set_cached_exchange_rates(
    rates: dict[tuple[str, str], Decimal],
    ttl_seconds: int = 300,
):
    await redis_client.set(
        EXCHANGE_RATES_CACHE_KEY,
        json.dumps(decimal_to_str_rates(rates)),
        ex=ttl_seconds,
    )


async def get_latest_exchange_rate() -> Any | None:
    """
    Read the latest exchange-rate payload from Redis.

    NBL-510 chatbot tools must access Redis through this
    service instead of reading redis_client directly.
    """
    cached_data = await redis_client.get(
        EXCHANGE_LATEST_CACHE_KEY
    )

    if not cached_data:
        return None

    if isinstance(cached_data, bytes):
        cached_data = cached_data.decode("utf-8")

    try:
        return json.loads(cached_data)
    except (json.JSONDecodeError, TypeError):
        return cached_data