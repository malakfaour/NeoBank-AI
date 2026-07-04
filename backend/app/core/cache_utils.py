import json

from app.core.redis import redis_client

BALANCE_CACHE_TTL_SECONDS = 30


def _balance_cache_key(user_id: int) -> str:
    return f"balance:{user_id}"


async def get_cached_balance(user_id: int) -> dict | None:
    cached = await redis_client.get(_balance_cache_key(user_id))
    if cached is None:
        return None
    return json.loads(cached)


async def cache_balance(user_id: int, data: dict) -> None:
    await redis_client.setex(
        _balance_cache_key(user_id),
        BALANCE_CACHE_TTL_SECONDS,
        json.dumps(data),
    )


async def invalidate_balance_cache(user_id: int) -> None:
    """
    Call after any debit or credit so the next GET /accounts/balance for
    this user reads fresh data instead of a stale cached balance
    (NBL-403 cache layer). Imported directly by the transactions service
    -- keep this module free of any accounts.py-specific imports so it
    stays a clean shared dependency.
    """
    await redis_client.delete(_balance_cache_key(user_id))
