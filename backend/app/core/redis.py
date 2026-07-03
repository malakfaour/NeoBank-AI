import json

import redis.asyncio as aioredis

from app.core.config import settings

redis_client = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


def get_redis_client():
    return redis_client


# ── Blacklist (access + refresh tokens revoked on logout) ─────────────────────

async def blacklist_token(jti: str, expire_minutes: int = None) -> None:
    ttl = (expire_minutes or settings.JWT_EXPIRE_MINUTES) * 60
    await redis_client.set(f"blacklist:{jti}", "1", ex=ttl)


async def is_blacklisted(jti: str) -> bool:
    result = await redis_client.get(f"blacklist:{jti}")
    return result is not None


# ── Refresh token registry ─────────────────────────────────────────────────────

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


# ── Passcode action token ──────────────────────────────────────────────────────

async def store_action_token(user_id: str, token: str, ttl: int = 300) -> None:
    await redis_client.set(f"action_token:{user_id}", token, ex=ttl)


async def get_action_token(user_id: str) -> str | None:
    return await redis_client.get(f"action_token:{user_id}")


# ── Passcode attempt locking ───────────────────────────────────────────────────

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


# ── Idempotency cache (prevent duplicate transactions) ────────────────────────

async def cache_idempotent_response(key: str, response: dict, ttl: int = 86400) -> None:
    """Cache a response for idempotency checking (default 24h TTL)."""
    await redis_client.set(f"idempotent:{key}", json.dumps(response), ex=ttl)


async def get_idempotent_response(key: str) -> dict | None:
    """Retrieve a cached idempotent response if it exists."""
    result = await redis_client.get(f"idempotent:{key}")
    return json.loads(result) if result else None


# Alias for backward compatibility
get_cached_idempotent_response = get_idempotent_response
def hash_idempotency_key(user_id: str, endpoint: str, payload: str) -> str:
    """Generate a unique idempotency key from user, endpoint, and payload."""
    import hashlib
    raw = f"{user_id}:{endpoint}:{payload}"
    return hashlib.sha256(raw.encode()).hexdigest()