"""
Endpoint-level tests for DEVATTECH-107: transfer daily cap + velocity guard.

Style follows test_money_movement.py / test_wallet_lifecycle.py: real
async HTTP client + real async DB session, direct DB writes for state
setup not reachable purely through the API (e.g. funding a wallet past
the $1000/day top-up cap, which is unrelated to and much lower than the
transfer daily cap being tested here).
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency


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


async def _get_user_and_wallet(email: str, currency: WalletCurrency) -> tuple[User, Wallet]:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        wallet = (
            await session.execute(
                select(Wallet).where(
                    Wallet.user_id == user.id,
                    Wallet.currency == currency,
                )
            )
        ).scalar_one()
        return user, wallet


async def _set_wallet_balance(wallet_id: int, balance: Decimal) -> None:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(select(Wallet).where(Wallet.id == wallet_id))
        ).scalar_one()
        wallet.balance = balance
        await session.commit()


@pytest.fixture
def stub_fraud_scoring(monkeypatch):
    calls = []

    def _delay(transaction_id: int) -> None:
        calls.append(transaction_id)

    monkeypatch.setattr("app.api.v1.endpoints.transactions.score_transaction.delay", _delay)
    return calls


@pytest.mark.anyio
async def test_daily_transfer_limit_exceeded_returns_422(client, stub_fraud_scoring):
    sender_tokens = await _register_user(client, "limit-sender")
    receiver_tokens = await _register_user(client, "limit-receiver")
    sender_user, sender_wallet = await _get_user_and_wallet(sender_tokens["email"], WalletCurrency.USD)
    receiver_user, _ = await _get_user_and_wallet(receiver_tokens["email"], WalletCurrency.USD)

    # Fund well past the daily transfer cap via direct DB write -- the
    # $1000/day top-up cap is unrelated and much lower than the default
    # $10000 transfer cap, so the real top-up endpoint can't fund this.
    await _set_wallet_balance(sender_wallet.id, Decimal("50000.00"))

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "receiver_id": str(receiver_user.id),
            "amount": "10001.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"]["error"] == "daily_limit_exceeded"
    assert "remaining" in body["detail"]


@pytest.mark.anyio
async def test_transfer_velocity_limit_returns_429(client, stub_fraud_scoring):
    sender_tokens = await _register_user(client, "velocity-sender")
    receiver_tokens = await _register_user(client, "velocity-receiver")
    sender_user, sender_wallet = await _get_user_and_wallet(sender_tokens["email"], WalletCurrency.USD)
    receiver_user, _ = await _get_user_and_wallet(receiver_tokens["email"], WalletCurrency.USD)

    # Small balance is enough -- amounts here are tiny and well under the
    # daily cap; this test is only exercising the velocity guard.
    await _set_wallet_balance(sender_wallet.id, Decimal("1000.00"))

    statuses = []
    for _ in range(6):
        response = await client.post(
            "/api/v1/transactions/send",
            headers={
                "Authorization": f"Bearer {sender_tokens['access_token']}",
                "X-Idempotency-Key": uuid4().hex,
            },
            json={
                "receiver_id": str(receiver_user.id),
                "amount": "1.00",
                "currency": "USD",
            },
        )
        statuses.append(response.status_code)

    assert statuses[:5] == [200] * 5, statuses
    assert statuses[5] == 429, statuses
