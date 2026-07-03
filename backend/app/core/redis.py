import hashlib
import json

import redis.asyncio as aioredis
from app.core.config import settings

redis_client = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True
)

async def blacklist_token(jti: str, expire_minutes: int = None) -> None:
    ttl = (expire_minutes or settings.JWT_EXPIRE_MINUTES) * 60
    await redis_client.setex(f"blacklist:{jti}", ttl, "1")

async def is_blacklisted(jti: str) -> bool:
    result = await redis_client.get(f"blacklist:{jti}")
    return result is not None


# --- DEVATTECH-72: send-money idempotency ---

IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60  # 24h


def hash_idempotency_key(user_id: int, raw_key: str) -> str:
    """
    Scope the client-supplied X-Idempotency-Key to the requesting user, so
    two different users coincidentally sending the same header value don't
    collide. Also used as Transaction.idempotency_key in the DB (unique
    constraint acts as the final safety net if a Redis race lets two
    identical requests both fall through).
    """
    return hashlib.sha256(f"{user_id}:{raw_key}".encode()).hexdigest()


async def get_cached_idempotent_response(user_id: int, raw_key: str) -> dict | None:
    cached = await redis_client.get(f"idem:{hash_idempotency_key(user_id, raw_key)}")
    if cached is None:
        return None
    return json.loads(cached)


async def cache_idempotent_response(user_id: int, raw_key: str, response: dict) -> None:
    # NOTE: naive check-then-set. Two identical requests arriving within the
    # same few milliseconds could both miss this cache and both proceed to
    # execute — the DB's unique constraint on Transaction.idempotency_key is
    # the actual safety net for that race (see app/api/transactions.py).
    # A SETNX-based lock would close the Redis-level race too, if this
    # becomes a real problem under load.
    await redis_client.setex(
        f"idem:{hash_idempotency_key(user_id, raw_key)}",
        IDEMPOTENCY_TTL_SECONDS,
        json.dumps(response),
    )
# ── Idempotency cache (prevent duplicate transactions) ────────────────────────

async def cache_idempotent_response(key: str, response: dict, ttl: int = 86400) -> None:
    """Cache a response for idempotency checking (default 24h TTL)."""
    import json
    await redis_client.set(f"idempotent:{key}", json.dumps(response), ex=ttl)


async def get_idempotent_response(key: str) -> dict | None:
    """Retrieve a cached idempotent response if it exists."""
    import json
    result = await redis_client.get(f"idempotent:{key}")
    return json.loads(result) if result else None