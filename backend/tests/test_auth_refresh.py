import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import User

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

@pytest.mark.asyncio
async def test_register_returns_user(client):
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "Register User",
        "email": "registeruser@neobank.com",
        "phone": "+96170000031",
        "password": "TestPass123",
    })

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["full_name"] == "Register User"
    assert data["user"]["email"] == "registeruser@neobank.com"
    assert data["user"]["phone"] == "+96170000031"
    assert data["user"]["kyc_status"] == "pending"

@pytest.mark.asyncio
async def test_email_password_login_returns_user(client):
    await client.post("/api/v1/auth/register", json={
        "full_name": "Email Login User",
        "email": "emaillogin@neobank.com",
        "phone": "+96170000032",
        "password": "TestPass123",
    })

    response = await client.post("/api/v1/auth/login", json={
        "email": "emaillogin@neobank.com",
        "password": "TestPass123",
    })

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "emaillogin@neobank.com"
    assert data["user"]["phone"] == "+96170000032"


@pytest.mark.asyncio
async def test_phone_passcode_login_works(client, db_session):
    register_response = await client.post("/api/v1/auth/register", json={
        "full_name": "Phone Login User",
        "email": "phonelogin@neobank.com",
        "phone": "+96170000033",
        "password": "TestPass123",
    })

    user_id = register_response.json()["user"]["id"]

    result = await db_session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.passcode_hash = hash_password("123456")
    await db_session.commit()

    response = await client.post("/api/v1/auth/login", json={
        "phone": "+96170000033",
        "passcode": "123456",
    })

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "phonelogin@neobank.com"
    assert data["user"]["phone"] == "+96170000033"


@pytest.mark.asyncio
async def test_phone_passcode_login_without_passcode_hash_returns_401(client):
    await client.post("/api/v1/auth/register", json={
        "full_name": "No Passcode User",
        "email": "nopasscode@neobank.com",
        "phone": "+96170000034",
        "password": "TestPass123",
    })

    response = await client.post("/api/v1/auth/login", json={
        "phone": "+96170000034",
        "passcode": "123456",
    })

    assert response.status_code == 401
    assert response.json()["detail"] == "Passcode not set"