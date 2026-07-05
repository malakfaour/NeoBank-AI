import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def auth_tokens(client):
    """Register and login a test user, return tokens."""
    await client.post("/api/v1/auth/register", json={
        "full_name": "Test User",
        "email": "refreshtest@neobank.com",
        "phone": "+96170000001",
        "password": "TestPass123",
    })
    response = await client.post("/api/v1/auth/login", json={
        "email": "refreshtest@neobank.com",
        "password": "TestPass123",
    })
    return response.json()


async def test_refresh_happy_path(client, auth_tokens):
    """Happy path: valid refresh token returns new token pair."""
    response = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": auth_tokens["refresh_token"],
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != auth_tokens["refresh_token"]


async def test_refresh_replay_attack(client, auth_tokens):
    """Replay attack: using same refresh token twice returns 401."""
    from app.core.security import create_refresh_token

    # Create a fresh token and mock Redis to simulate it being already used
    refresh_token, jti = create_refresh_token("test-user-999", role="customer")

    with patch("app.api.v1.endpoints.auth.is_blacklisted", new=AsyncMock(return_value=False)), \
         patch("app.api.v1.endpoints.auth.refresh_jti_exists", new=AsyncMock(return_value=False)), \
         patch("app.api.v1.endpoints.auth.revoke_all_user_tokens", new=AsyncMock()):

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert response.status_code == 401
        assert "already used" in response.json()["detail"]


async def test_refresh_expired_token(client):
    """Expired refresh token returns 401."""
    import jwt
    from datetime import datetime, timezone
    from app.core.config import settings

    expired_token = jwt.encode(
        {
            "sub": "999",
            "jti": "expired-jti",
            "exp": datetime(2020, 1, 1, tzinfo=timezone.utc),
            "type": "refresh",
            "role": "customer",
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": expired_token,
    })
    assert response.status_code == 401


async def test_refresh_after_logout(client, auth_tokens):
    """After logout, refresh token returns 401."""
    rotated = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": auth_tokens["refresh_token"],
    })
    new_tokens = rotated.json()

    await client.post("/api/v1/auth/logout", json={
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
    })

    response = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": new_tokens["refresh_token"],
    })
    assert response.status_code == 401