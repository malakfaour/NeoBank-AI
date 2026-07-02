import redis.asyncio as aioredis
from app.core.config import settings

redis_client = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


# ── Blacklist (access + refresh tokens revoked on logout) ─────────────────────

async def blacklist_token(jti: str, expire_minutes: int = None) -> None:
    ttl = (expire_minutes or settings.JWT_EXPIRE_MINUTES) * 60
    await redis_client.setex(f"blacklist:{jti}", ttl, "1")


async def is_blacklisted(jti: str) -> bool:
    result = await redis_client.get(f"blacklist:{jti}")
    return result is not None


# ── Refresh token registry (valid JTIs that can be rotated) ───────────────────

def _refresh_key(jti: str) -> str:
    return f"refresh:{jti}"


def _user_refresh_key(user_id: str) -> str:
    return f"user_refresh:{user_id}"


async def store_refresh_jti(user_id: str, jti: str) -> None:
    """Store a valid refresh JTI in Redis. Also track it under the user key."""
    ttl = settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60
    pipe = redis_client.pipeline()
    pipe.setex(_refresh_key(jti), ttl, user_id)
    pipe.setex(_user_refresh_key(user_id), ttl, jti)
    await pipe.execute()


async def refresh_jti_exists(jti: str) -> bool:
    """Returns True if the refresh JTI is still valid (not rotated or revoked)."""
    result = await redis_client.get(_refresh_key(jti))
    return result is not None


async def get_user_id_from_refresh_jti(jti: str) -> str | None:
    """Returns the user_id associated with a refresh JTI."""
    return await redis_client.get(_refresh_key(jti))


async def rotate_refresh_jti(
    user_id: str,
    old_jti: str,
    new_jti: str,
) -> None:
    """
    Atomically deletes the old refresh JTI and stores the new one.
    Used during token rotation.
    """
    ttl = settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60
    pipe = redis_client.pipeline()
    pipe.delete(_refresh_key(old_jti))
    pipe.setex(_refresh_key(new_jti), ttl, user_id)
    pipe.setex(_user_refresh_key(user_id), ttl, new_jti)
    await pipe.execute()


async def revoke_all_user_tokens(user_id: str, current_refresh_jti: str) -> None:
    """
    Replay attack detected — blacklist the current refresh JTI and
    delete the user's active refresh token from the registry.
    """
    ttl = settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60
    pipe = redis_client.pipeline()
    pipe.setex(f"blacklist:{current_refresh_jti}", ttl, "1")
    pipe.delete(_user_refresh_key(user_id))
    await pipe.execute()
# ── Passcode action token (short-lived token for high-value actions) ──────────

async def store_action_token(user_id: str, token: str, ttl: int = 300) -> None:
    """Store a short-lived action token (5 min TTL) for high-value actions."""
    await redis_client.set(f"action_token:{user_id}", token, ex=ttl)


async def get_action_token(user_id: str) -> str | None:
    """Retrieve the action token for a user."""
    return await redis_client.get(f"action_token:{user_id}")


# ── Passcode attempt locking ───────────────────────────────────────────────────

def _passcode_attempts_key(user_id: str) -> str:
    return f"passcode_attempts:{user_id}"


async def increment_passcode_attempts(user_id: str) -> int:
    """Increment failed passcode attempts. Returns current count."""
    key = _passcode_attempts_key(user_id)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 600)  # 10 min window
    return count


async def is_passcode_locked(user_id: str) -> bool:
    """Returns True if user has 3+ failed passcode attempts."""
    count = await redis_client.get(_passcode_attempts_key(user_id))
    return int(count) >= 3 if count else False


async def reset_passcode_attempts(user_id: str) -> None:
    """Reset failed attempts after successful passcode verification."""
    await redis_client.delete(_passcode_attempts_key(user_id))