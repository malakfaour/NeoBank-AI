import hashlib
import json

import redis.asyncio as aioredis

from app.core.config import settings
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

redis_client = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)

IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
CHAT_ACTION_TTL_SECONDS = 5 * 60


def get_redis_client():
    return redis_client


async def blacklist_token(jti: str, expire_minutes: int = None) -> None:
    ttl = (expire_minutes or settings.JWT_EXPIRE_MINUTES) * 60
    await redis_client.set(f"blacklist:{jti}", "1", ex=ttl)


async def is_blacklisted(jti: str) -> bool:
    result = await redis_client.get(f"blacklist:{jti}")
    return result is not None


def _refresh_key(jti: str) -> str:
    return f"refresh:{jti}"


def _user_refresh_key(user_id: str) -> str:
    return f"user_refresh:{user_id}"


async def store_refresh_jti(user_id: str, jti: str) -> None:
    ttl = settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60
    pipe = redis_client.pipeline()
    pipe.set(_refresh_key(jti), user_id, ex=ttl)
    pipe.set(_user_refresh_key(user_id), jti, ex=ttl)
    await pipe.execute()


async def refresh_jti_exists(jti: str) -> bool:
    result = await redis_client.get(_refresh_key(jti))
    return result is not None


async def get_user_id_from_refresh_jti(jti: str) -> str | None:
    return await redis_client.get(_refresh_key(jti))


async def rotate_refresh_jti(user_id: str, old_jti: str, new_jti: str) -> None:
    ttl = settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60
    pipe = redis_client.pipeline()
    pipe.delete(_refresh_key(old_jti))
    pipe.set(_refresh_key(new_jti), user_id, ex=ttl)
    pipe.set(_user_refresh_key(user_id), new_jti, ex=ttl)
    await pipe.execute()


async def revoke_all_user_tokens(user_id: str, current_refresh_jti: str) -> None:
    ttl = settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60
    pipe = redis_client.pipeline()
    pipe.set(f"blacklist:{current_refresh_jti}", "1", ex=ttl)
    pipe.delete(_user_refresh_key(user_id))
    await pipe.execute()


async def store_action_token(user_id: str, token: str, ttl: int = 300) -> None:
    await redis_client.set(f"action_token:{user_id}", token, ex=ttl)


async def get_action_token(user_id: str) -> str | None:
    return await redis_client.get(f"action_token:{user_id}")


async def consume_action_token(user_id: str, token: str) -> bool:
    """
    Atomically fetch-and-delete the action token for user_id (Redis GETDEL).
    Single-use: a replay with the same token, or any check after the token
    was already consumed/expired, gets None back and returns False.
    """
    stored = await redis_client.getdel(f"action_token:{user_id}")
    return stored is not None and stored == token


def _chat_action_key(session_id: str) -> str:
    """Redis key for a pending chatbot action. TTL is always required."""
    return f"chat_action:{session_id}"


async def store_chat_pending_action(
    session_id: str,
    payload: dict,
    ttl: int = CHAT_ACTION_TTL_SECONDS,
) -> None:
    await redis_client.set(
        _chat_action_key(session_id),
        json.dumps(payload),
        ex=ttl,
    )


async def get_chat_pending_action(session_id: str) -> dict | None:
    raw_payload = await redis_client.get(_chat_action_key(session_id))

    if raw_payload is None:
        return None

    return json.loads(raw_payload)


async def delete_chat_pending_action(session_id: str) -> None:
    await redis_client.delete(_chat_action_key(session_id))


def _passcode_attempts_key(user_id: str) -> str:
    return f"passcode_attempts:{user_id}"


async def increment_passcode_attempts(user_id: str) -> int:
    key = _passcode_attempts_key(user_id)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 600)
    return count


async def is_passcode_locked(user_id: str) -> bool:
    count = await redis_client.get(_passcode_attempts_key(user_id))
    return int(count) >= 3 if count else False


async def reset_passcode_attempts(user_id: str) -> None:
    await redis_client.delete(_passcode_attempts_key(user_id))


def hash_idempotency_key(
    user_id: int,
    raw_key: str | None = None,
    endpoint: str | None = None,
    payload: str | None = None,
) -> str:
    """Generate a unique idempotency key scoped per user."""
    base = raw_key or f"{endpoint}:{payload}"
    value = f"{user_id}:{base}"
    return hashlib.sha256(value.encode()).hexdigest()


async def get_cached_idempotent_response(user_id: int, raw_key: str) -> dict | None:
    cached = await redis_client.get(f"idem:{hash_idempotency_key(user_id, raw_key)}")
    if cached is None:
        return None
    return json.loads(cached)


async def cache_idempotent_response(
    user_id: int,
    raw_key: str,
    response: dict,
    ttl: int = IDEMPOTENCY_TTL_SECONDS,
) -> None:
    # The DB unique constraint on Transaction.idempotency_key remains the
    # final safety net if two identical requests race past Redis.
    await redis_client.setex(
        f"idem:{hash_idempotency_key(user_id, raw_key)}",
        ttl,
        json.dumps(response),
    )


async def get_idempotent_response(key: str) -> dict | None:
    """Legacy raw-key cache accessor kept for backward compatibility."""
    result = await redis_client.get(f"idempotent:{key}")
    return json.loads(result) if result else None


# NBL-411: max total card top-ups per user per UTC day.
TOPUP_DAILY_LIMIT = Decimal("1000")


def _topup_daily_key(user_id: int) -> str:
    return f"topup_daily:{user_id}"


async def get_topup_daily_total(user_id: int) -> Decimal:
    """Current UTC-day top-up total for user_id, in dollars (NBL-411)."""
    cents = await redis_client.get(_topup_daily_key(user_id))
    return Decimal(cents) / 100 if cents is not None else Decimal("0")


async def increment_topup_daily(user_id: int, amount: Decimal) -> Decimal:
    """
    Atomically add `amount` (dollars) to today's top-up total for user_id
    and return the new total (NBL-411 daily limit).

    Stored as integer cents so INCRBY (atomic, exact) can be used instead
    of INCRBYFLOAT, which accumulates binary float error on repeated
    increments -- not acceptable for money math.

    TTL is (re)computed on every call to expire at the next UTC midnight.
    Since Redis drops the key at that boundary, the first top-up of a new
    day always starts a fresh key with a correct TTL; later top-ups the
    same day just refresh the same expiry, which is a harmless no-op.
    """
    key = _topup_daily_key(user_id)
    amount_cents = int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))

    now = datetime.now(timezone.utc)
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    ttl_seconds = int((next_midnight - now).total_seconds())

    pipe = redis_client.pipeline()
    pipe.incrby(key, amount_cents)
    pipe.expire(key, ttl_seconds)
    results = await pipe.execute()
    return Decimal(results[0]) / 100


def _transfer_daily_key(user_id: int) -> str:
    return f"transfer_daily:{user_id}"


async def get_transfer_daily_total(user_id: int) -> Decimal:
    """
    Current UTC-day transfer total for user_id, in dollars (DEVATTECH-107).
    Mirrors get_topup_daily_total() -- same integer-cents storage, same
    UTC-midnight TTL behavior. The limit itself lives in
    settings.DAILY_TRANSFER_LIMIT_USD, not a module constant here (unlike
    TOPUP_DAILY_LIMIT), per the ticket's "DAILY_TRANSFER_LIMIT_USD config"
    wording.
    """
    cents = await redis_client.get(_transfer_daily_key(user_id))
    return Decimal(cents) / 100 if cents is not None else Decimal("0")


async def increment_transfer_daily(user_id: int, amount: Decimal) -> Decimal:
    """
    Atomically add `amount` (dollars) to today's transfer total for
    user_id and return the new total (DEVATTECH-107 daily limit). Exact
    same pattern as increment_topup_daily() -- integer cents so INCRBY
    stays atomic/exact, TTL recomputed each call to expire at next UTC
    midnight.
    """
    key = _transfer_daily_key(user_id)
    amount_cents = int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))

    now = datetime.now(timezone.utc)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl_seconds = int((next_midnight - now).total_seconds())

    pipe = redis_client.pipeline()
    pipe.incrby(key, amount_cents)
    pipe.expire(key, ttl_seconds)
    results = await pipe.execute()
    return Decimal(results[0]) / 100
