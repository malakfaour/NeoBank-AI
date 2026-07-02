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