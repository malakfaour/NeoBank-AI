import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def test_rate_limit_boundary(client):
    """
    Confirm boundary: exactly max_requests allowed, next one returns 429.
    Tests /auth/login with sliding window limit of 5/min.
    """
    from app.services import rate_limiter as rl_module
    import fakeredis.aioredis

    fake = fakeredis.aioredis.FakeRedis()

    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):

        # Make 5 requests — all should pass
        for i in range(5):
            response = await client.post("/auth/login", json={
                "email": f"test{i}@neobank.com",
                "password": "wrongpass",
            })
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"

        # 6th request — should be 429
        response = await client.post("/auth/login", json={
            "email": "test6@neobank.com",
            "password": "wrongpass",
        })
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"


async def test_ip_ban_after_10_consecutive_429s():
    """After 10 consecutive 429s from same IP, IP gets banned for 1 hour."""
    import fakeredis.aioredis
    from fastapi import Request
    from app.services.rate_limiter import check_rate_limit, _ban_key

    fake = fakeredis.aioredis.FakeRedis()

    with patch("app.services.rate_limiter.redis_client", fake):
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "1.2.3.4"

        # Trigger 10 consecutive 429s
        for _ in range(10):
            await fake.incr("429_count:1.2.3.4")
        await fake.expire("429_count:1.2.3.4", 300)

        # Simulate 11th — should trigger ban
        from app.services.rate_limiter import _track_consecutive_429
        await _track_consecutive_429("1.2.3.4")

        # Check ban key exists
        banned = await fake.exists(_ban_key("1.2.3.4"))
        assert banned == 1


async def test_retry_after_header_present():
    """429 response must include Retry-After header."""
    import fakeredis.aioredis
    from fastapi import Request
    from app.services.rate_limiter import check_rate_limit

    fake = fakeredis.aioredis.FakeRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch("app.services.rate_limiter.redis_client", fake), \
             patch("app.core.redis.redis_client", fake):

            for _ in range(6):
                response = await client.post("/auth/login", json={
                    "email": "test@test.com",
                    "password": "wrong",
                })

            assert response.status_code == 429
            assert "Retry-After" in response.headers