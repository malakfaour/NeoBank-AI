from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency
from app.services.otp import generate_and_store_otp


@pytest.fixture(autouse=True)
def _enable_action_token(monkeypatch):
    """These tests specifically exercise the gate, regardless of the
    conftest-wide default (REQUIRE_ACTION_TOKEN=false)."""
    monkeypatch.setattr(settings, "REQUIRE_ACTION_TOKEN", True)


async def _register_user(client, label: str) -> dict:
    suffix = uuid4().hex[:10]
    phone = f"+96170{suffix[:6]}"
    email = f"{label.lower()}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": phone,
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200, response.text
    return {**response.json(), "email": email, "phone": phone}


async def _get_user_id(email: str) -> int:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        return user.id


async def _get_wallet_id(user_id: int) -> int:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(
                select(Wallet).where(Wallet.user_id == user_id, Wallet.currency == WalletCurrency.USD)
            )
        ).scalar_one()
        return wallet.id


async def _top_up(client, access_token: str, wallet_id: int, amount: str) -> None:
    response = await client.post(
        "/api/v1/accounts/top-up",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"wallet_id": wallet_id, "amount": amount, "card_token": "tok_visa_test_123"},
    )
    assert response.status_code == 200, response.text


async def _get_action_token(client, access_token: str, user_id: int, phone: str) -> str:
    """Sets a passcode (via a directly-issued OTP, bypassing real SMS) then
    verifies it to obtain a real action_token through the actual endpoints."""
    with patch("app.services.otp.send_sms", new=AsyncMock(return_value="SM_test_sid")):
        otp = await generate_and_store_otp(str(user_id), phone)

    set_resp = await client.post(
        "/api/v1/auth/passcode/set",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"passcode": "123456", "otp_code": otp},
    )
    assert set_resp.status_code == 200, set_resp.text

    verify_resp = await client.post(
        "/api/v1/auth/passcode/verify",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"passcode": "123456"},
    )
    assert verify_resp.status_code == 200, verify_resp.text
    return verify_resp.json()["action_token"]


async def test_send_money_with_valid_action_token_succeeds(client):
    """Happy path: correct token, correct user, one-time use, request succeeds."""
    sender = await _register_user(client, "atsender")
    receiver = await _register_user(client, "atreceiver")

    sender_id = await _get_user_id(sender["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)

    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")
    token = await _get_action_token(client, sender["access_token"], sender_id, sender["phone"])

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
            "X-Action-Token": token,
        },
        json={"receiver_id": str(receiver_id), "amount": "10.00", "currency": "USD"},
    )
    assert response.status_code == 200, response.text


async def test_send_money_missing_action_token_returns_403(client):
    """Missing header entirely -> 403."""
    sender = await _register_user(client, "atmissing")
    receiver = await _register_user(client, "atmissing2")
    sender_id = await _get_user_id(sender["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)
    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={"receiver_id": str(receiver_id), "amount": "10.00", "currency": "USD"},
    )
    assert response.status_code == 403


async def test_send_money_action_token_replay_returns_403(client):
    """Reusing an already-consumed token -> 403 on the second attempt."""
    sender = await _register_user(client, "atreplay")
    receiver = await _register_user(client, "atreplay2")
    sender_id = await _get_user_id(sender["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)
    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")
    token = await _get_action_token(client, sender["access_token"], sender_id, sender["phone"])

    headers = {
        "Authorization": f"Bearer {sender['access_token']}",
        "X-Action-Token": token,
    }
    first = await client.post(
        "/api/v1/transactions/send",
        headers={**headers, "X-Idempotency-Key": uuid4().hex},
        json={"receiver_id": str(receiver_id), "amount": "5.00", "currency": "USD"},
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        "/api/v1/transactions/send",
        headers={**headers, "X-Idempotency-Key": uuid4().hex},
        json={"receiver_id": str(receiver_id), "amount": "5.00", "currency": "USD"},
    )
    assert second.status_code == 403


async def test_send_money_another_users_action_token_returns_403(client):
    """A valid token belonging to a different user must not work -> 403."""
    sender = await _register_user(client, "atcross")
    other_user = await _register_user(client, "atcrossother")
    receiver = await _register_user(client, "atcrossreceiver")

    sender_id = await _get_user_id(sender["email"])
    other_id = await _get_user_id(other_user["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)
    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")

    # Token issued to "other_user", not to "sender".
    other_token = await _get_action_token(client, other_user["access_token"], other_id, other_user["phone"])

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
            "X-Action-Token": other_token,
        },
        json={"receiver_id": str(receiver_id), "amount": "5.00", "currency": "USD"},
    )
    assert response.status_code == 403


async def test_exchange_execute_requires_auth(client):
    """/exchange/execute now requires auth -- no Authorization header -> 401."""
    response = await client.post(
        "/api/v1/exchange/execute",
        json={"from_currency": "USD", "to_currency": "LBP", "amount": "10.00"},
    )
    assert response.status_code == 401