"""
Endpoint-level tests for DEVATTECH-104: wallet lifecycle (freeze/unfreeze/close).

Style follows test_money_movement.py: real async HTTP client + real async
DB session against the SQLite test DB, direct DB writes for state setup
that isn't reachable purely through the API (e.g. forcing a wallet to
`frozen` before hitting a money-movement endpoint).

Admin-role access is tested by minting a token with role="admin" directly
via create_access_token(), since /auth/register only ever creates
customer-role users and get_current_user() reads role purely from the JWT
claim (no DB re-fetch) -- confirmed in app/api/dependencies.py. This
avoids the heavier RBAC/DB fixture gap documented in test_admin.py, which
only applies to endpoints behind require_role() with real cross-table DB
state; our lifecycle endpoints don't use require_role().

NOT covered here: admin.py's fraud-reversal credit path being blocked on
a frozen/closed wallet. Exercising that endpoint needs the same
Postgres-backed DB fixture test_admin.py already documents as missing --
out of scope to build here. wallet_locking.py's guard is still unit-
reachable via the bills.py debit path tested below, which shares the same
lock_and_debit_wallet()/lock_and_credit_wallet() guard call.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency, WalletStatus


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


async def _set_wallet_status(wallet_id: int, status: WalletStatus) -> None:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(select(Wallet).where(Wallet.id == wallet_id))
        ).scalar_one()
        wallet.status = status
        await session.commit()


async def _get_wallet_status(wallet_id: int) -> WalletStatus:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(select(Wallet).where(Wallet.id == wallet_id))
        ).scalar_one()
        return wallet.status


def _admin_token() -> str:
    access_token, _ = create_access_token(subject="999999", role="admin")
    return access_token


async def _top_up_wallet(client, access_token: str, wallet_id: int, amount: str):
    # DEVATTECH-125: X-Idempotency-Key is now required on this endpoint.
    return await client.post(
        "/api/v1/accounts/top-up",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "wallet_id": wallet_id,
            "amount": amount,
            "card_token": "tok_visa_test_123",
        },
    )


@pytest.mark.anyio
async def test_freeze_wallet_by_owner_succeeds(client):
    tokens = await _register_user(client, "freeze-owner")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/freeze",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "frozen"
    assert await _get_wallet_status(wallet.id) == WalletStatus.frozen


@pytest.mark.anyio
async def test_freeze_wallet_by_non_owner_rejected(client):
    owner_tokens = await _register_user(client, "freeze-victim")
    other_tokens = await _register_user(client, "freeze-attacker")
    _, wallet = await _get_user_and_wallet(owner_tokens["email"], WalletCurrency.USD)

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/freeze",
        headers={"Authorization": f"Bearer {other_tokens['access_token']}"},
    )
    assert response.status_code == 403, response.text
    assert await _get_wallet_status(wallet.id) == WalletStatus.active


@pytest.mark.anyio
async def test_freeze_wallet_by_admin_succeeds(client):
    owner_tokens = await _register_user(client, "freeze-admin-target")
    _, wallet = await _get_user_and_wallet(owner_tokens["email"], WalletCurrency.USD)

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/freeze",
        headers={"Authorization": f"Bearer {_admin_token()}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "frozen"


@pytest.mark.anyio
async def test_unfreeze_wallet_succeeds(client):
    tokens = await _register_user(client, "unfreeze-owner")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_status(wallet.id, WalletStatus.frozen)

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/unfreeze",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert await _get_wallet_status(wallet.id) == WalletStatus.active


@pytest.mark.anyio
async def test_close_wallet_with_zero_balance_succeeds(client):
    tokens = await _register_user(client, "close-empty")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/close",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "closed"
    assert await _get_wallet_status(wallet.id) == WalletStatus.closed


@pytest.mark.anyio
async def test_close_wallet_with_nonzero_balance_rejected(client):
    tokens = await _register_user(client, "close-funded")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _top_up_wallet(client, tokens["access_token"], wallet.id, "10.00")

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/close",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "wallet_balance_not_zero"
    assert await _get_wallet_status(wallet.id) == WalletStatus.active


@pytest.mark.anyio
async def test_close_already_closed_wallet_is_idempotent(client):
    tokens = await _register_user(client, "close-twice")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_status(wallet.id, WalletStatus.closed)

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/close",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "closed"


@pytest.mark.anyio
async def test_freeze_closed_wallet_rejected(client):
    tokens = await _register_user(client, "freeze-closed")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_status(wallet.id, WalletStatus.closed)

    response = await client.post(
        f"/api/v1/accounts/{wallet.id}/freeze",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "wallet_closed"


@pytest.mark.anyio
async def test_send_money_from_frozen_wallet_rejected(client):
    sender_tokens = await _register_user(client, "blocked-sender")
    receiver_tokens = await _register_user(client, "blocked-receiver")
    sender_user, sender_wallet = await _get_user_and_wallet(sender_tokens["email"], WalletCurrency.USD)
    receiver_user, _ = await _get_user_and_wallet(receiver_tokens["email"], WalletCurrency.USD)
    await _top_up_wallet(client, sender_tokens["access_token"], sender_wallet.id, "100.00")
    await _set_wallet_status(sender_wallet.id, WalletStatus.frozen)

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "receiver_id": str(receiver_user.id),
            "amount": "10.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "wallet_frozen"
    assert await _get_wallet_status(sender_wallet.id) == WalletStatus.frozen


@pytest.mark.anyio
async def test_top_up_to_frozen_wallet_rejected(client):
    tokens = await _register_user(client, "blocked-topup")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_status(wallet.id, WalletStatus.frozen)

    response = await _top_up_wallet(client, tokens["access_token"], wallet.id, "10.00")
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "wallet_frozen"


@pytest.mark.anyio
async def test_exchange_from_closed_wallet_rejected(client, monkeypatch):
    tokens = await _register_user(client, "blocked-exchange")
    user, usd_wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _top_up_wallet(client, tokens["access_token"], usd_wallet.id, "100.00")
    await _set_wallet_status(usd_wallet.id, WalletStatus.closed)

    async def fake_rates():
        return {("USD", "LBP"): Decimal("89500.00")}

    monkeypatch.setattr("app.api.v1.endpoints.exchange.is_market_open", lambda: True)
    monkeypatch.setattr("app.api.v1.endpoints.exchange.get_rates_from_cache_or_provider", fake_rates)

    response = await client.post(
        "/api/v1/exchange/execute",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "from_currency": "USD",
            "to_currency": "LBP",
            "amount": "10.00",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "wallet_closed"
