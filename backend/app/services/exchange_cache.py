import json
from decimal import Decimal

from app.core.redis import redis_client

EXCHANGE_RATES_CACHE_KEY = "exchange:rates"


def decimal_to_str_rates(rates: dict[tuple[str, str], Decimal]) -> dict[str, str]:
    return {f"{base}:{target}": str(rate) for (base, target), rate in rates.items()}


def str_to_decimal_rates(data: dict[str, str]) -> dict[tuple[str, str], Decimal]:
    result = {}

    for pair, rate in data.items():
        base, target = pair.split(":")
        result[(base, target)] = Decimal(rate)

    return result


async def get_cached_exchange_rates():
    cached_data = await redis_client.get(EXCHANGE_RATES_CACHE_KEY)

    if not cached_data:
        return None

    return str_to_decimal_rates(json.loads(cached_data))


async def set_cached_exchange_rates(
    rates: dict[tuple[str, str], Decimal],
    ttl_seconds: int = 300,
):
    await redis_client.set(
        EXCHANGE_RATES_CACHE_KEY,
        json.dumps(decimal_to_str_rates(rates)),
        ex=ttl_seconds,
    )