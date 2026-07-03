import time
import logging

from fastapi import HTTPException, Request, status

from app.core.redis import redis_client

logger = logging.getLogger(__name__)

# ── IP ban tracking ────────────────────────────────────────────────────────────

def _ban_key(ip: str) -> str:
    return f"banned:{ip}"

def _consecutive_429_key(ip: str) -> str:
    return f"429_count:{ip}"


async def _check_ip_banned(ip: str) -> None:
    """Raise 429 if IP is currently banned."""
    if await redis_client.exists(_ban_key(ip)):
        ttl = await redis_client.ttl(_ban_key(ip))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"IP banned for {ttl} more seconds due to repeated abuse.",
            headers={"Retry-After": str(ttl)},
        )


async def _track_consecutive_429(ip: str) -> None:
    """
    Track consecutive 429 responses from an IP.
    After 10 in 5 minutes, ban the IP for 1 hour.
    """
    key = _consecutive_429_key(ip)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 300)  # 5-min window
    if count >= 10:
        await redis_client.set(_ban_key(ip), "1", ex=3600)  # ban 1 hour
        await redis_client.delete(key)
        logger.warning(f"IP {ip} banned for 1 hour after 10 consecutive 429s")


async def _reset_consecutive_429(ip: str) -> None:
    """Reset consecutive 429 counter on successful request."""
    await redis_client.delete(_consecutive_429_key(ip))


# ── Sliding window rate limiter ────────────────────────────────────────────────

async def check_rate_limit(
    request: Request,
    key_prefix: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """
    Sliding-window rate limiter using Redis sorted sets.
    - Adds current timestamp to sorted set
    - Removes entries older than the window
    - Counts remaining entries
    - Returns 429 with Retry-After and X-RateLimit-Remaining headers
    - Tracks consecutive 429s per IP and bans after 10 in 5 min
    """
    ip = request.client.host if request.client else "unknown"

    await _check_ip_banned(ip)

    key = f"sliding:{key_prefix}:{ip}"
    now = time.time()
    window_start = now - window_seconds

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, "-inf", window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window_seconds + 1)
    results = await pipe.execute()

    count = results[2]
    if count > max_requests:
        await _track_consecutive_429(ip)
        oldest = await redis_client.zrange(key, 0, 0, withscores=True)
        retry_after = int(window_seconds - (now - oldest[0][1])) if oldest else window_seconds
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Remaining": "0",
            },
        )

    await _reset_consecutive_429(ip)