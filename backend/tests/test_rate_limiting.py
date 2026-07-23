import pytest
import fakeredis.aioredis
from unittest.mock import patch
from uuid import uuid4


async def _register_user(client, label: str) -> dict:
    suffix = uuid4().hex[:10]
    email = f"{label.lower()}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96170{suffix[:6]}",
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200, response.text
    return {**response.json(), "email": email}

@pytest.mark.anyio
async def test_transfer_mobile_rate_limit(client):
    fake = fakeredis.aioredis.FakeRedis()
    tokens = await _register_user(client, "ratelimit-transfer-mobile")
    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):
        for i in range(5):
            response = await client.post(
                "/api/v1/transfer/neo/mobile",
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "X-Action-Token": "dummy",
                    "X-Idempotency-Key": f"rate-limit-{i}",
                },
                json={
                    "receiver_phone": "+96170000000",
                    "amount": 1.0,
                    "currency": "USD",
                },
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        response = await client.post(
            "/api/v1/transfer/neo/mobile",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "X-Action-Token": "dummy",
                "X-Idempotency-Key": "rate-limit-6",
            },
            json={
                "receiver_phone": "+96170000000",
                "amount": 1.0,
                "currency": "USD",
            },
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_exchange_execute_rate_limit(client):
    fake = fakeredis.aioredis.FakeRedis()
    tokens = await _register_user(client, "ratelimit-exchange-execute")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    body = {
        "from_currency": "USD",
        "to_currency": "LBP",
        "amount": 1.0,
    }
    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):
        for i in range(10):
            response = await client.post(
                "/api/v1/exchange/execute",
                headers=headers,
                json=body,
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        response = await client.post(
            "/api/v1/exchange/execute",
            headers=headers,
            json=body,
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_topup_rate_limit(client):
    fake = fakeredis.aioredis.FakeRedis()
    tokens = await _register_user(client, "ratelimit-topup")
    body = {
        "wallet_id": 1,
        "amount": "10.00",
        "payment_method_id": "pm_visa_test_123",
    }
    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):
        for i in range(10):
            response = await client.post(
                "/api/v1/accounts/top-up",
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "X-Idempotency-Key": f"rate-limit-topup-{i}",
                },
                json=body,
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        response = await client.post(
            "/api/v1/accounts/top-up",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "X-Idempotency-Key": "rate-limit-topup-10",
            },
            json=body,
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_beneficiary_create_rate_limit(client):
    fake = fakeredis.aioredis.FakeRedis()
    tokens = await _register_user(client, "ratelimit-beneficiary-create")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    body = {
        "nickname": "Test",
        "type": "mobile",
        "value": "+96170000000",
    }
    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):
        for i in range(10):
            response = await client.post(
                "/api/v1/beneficiaries",
                headers=headers,
                json=body,
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        response = await client.post(
            "/api/v1/beneficiaries",
            headers=headers,
            json=body,
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_beneficiary_update_rate_limit(client):
    fake = fakeredis.aioredis.FakeRedis()
    tokens = await _register_user(client, "ratelimit-beneficiary-update")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    body = {"nickname": "Renamed"}
    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):
        for i in range(10):
            response = await client.patch(
                "/api/v1/beneficiaries/999",
                headers=headers,
                json=body,
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        response = await client.patch(
            "/api/v1/beneficiaries/999",
            headers=headers,
            json=body,
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_beneficiary_delete_rate_limit(client):
    fake = fakeredis.aioredis.FakeRedis()
    tokens = await _register_user(client, "ratelimit-beneficiary-delete")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):
        for i in range(10):
            response = await client.delete(
                "/api/v1/beneficiaries/999",
                headers=headers,
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        response = await client.delete(
            "/api/v1/beneficiaries/999",
            headers=headers,
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers
@pytest.mark.anyio
async def test_transfer_iban_rate_limit(client):
    fake = fakeredis.aioredis.FakeRedis()
    tokens = await _register_user(client, "ratelimit-transfer-iban")
    with patch("app.services.rate_limiter.redis_client", fake), \
         patch("app.core.redis.redis_client", fake):
        for i in range(5):
            response = await client.post(
                "/api/v1/transfer/neo/iban",
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "X-Action-Token": "dummy",
                    "X-Idempotency-Key": f"rate-limit-iban-{i}",
                },
                json={
                    "receiver_iban": "LB1200000000000000001234567890",
                    "amount": 1.0,
                    "currency": "USD",
                },
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        response = await client.post(
            "/api/v1/transfer/neo/iban",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "X-Action-Token": "dummy",
                "X-Idempotency-Key": "rate-limit-iban-6",
            },
            json={
                "receiver_iban": "LB1200000000000000001234567890",
                "amount": 1.0,
                "currency": "USD",
            },
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers
