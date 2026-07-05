from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.transaction_audit_log import TransactionAuditLog
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


async def _get_wallet_balance(user_id: int, currency: WalletCurrency) -> Decimal:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(
                select(Wallet).where(
                    Wallet.user_id == user_id,
                    Wallet.currency == currency,
                )
            )
        ).scalar_one()
        return wallet.balance


async def _top_up_wallet(client, access_token: str, wallet_id: int, amount: str) -> None:
    response = await client.post(
        "/api/v1/accounts/top-up",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "wallet_id": wallet_id,
            "amount": amount,
            "card_token": "tok_visa_test_123",
        },
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def stub_fraud_scoring(monkeypatch):
    calls = []

    def _delay(transaction_id: int) -> None:
        calls.append(transaction_id)

    monkeypatch.setattr("app.api.v1.endpoints.transactions.score_transaction.delay", _delay)
    return calls


@pytest.mark.anyio
async def test_send_money_debits_sender_and_credits_receiver(client, stub_fraud_scoring):
    sender_tokens = await _register_user(client, "sender")
    receiver_tokens = await _register_user(client, "receiver")

    sender_user, sender_wallet = await _get_user_and_wallet(
        sender_tokens["email"],
        WalletCurrency.USD,
    )
    receiver_user, _ = await _get_user_and_wallet(
        receiver_tokens["email"],
        WalletCurrency.USD,
    )

    await _top_up_wallet(client, sender_tokens["access_token"], sender_wallet.id, "100.00")

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "receiver_id": str(receiver_user.id),
            "amount": "25.50",
            "currency": "USD",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert Decimal(body["amount"]) == Decimal("25.50")
    assert body["sender_id"] == sender_user.id
    assert body["receiver_id"] == receiver_user.id
    assert await _get_wallet_balance(sender_user.id, WalletCurrency.USD) == Decimal("74.5000")
    assert await _get_wallet_balance(receiver_user.id, WalletCurrency.USD) == Decimal("25.5000")
    assert stub_fraud_scoring == [body["transaction_id"]]


@pytest.mark.anyio
async def test_send_money_rejects_insufficient_balance(client, stub_fraud_scoring):
    sender_tokens = await _register_user(client, "lowfunds-sender")
    receiver_tokens = await _register_user(client, "lowfunds-receiver")

    sender_user, sender_wallet = await _get_user_and_wallet(
        sender_tokens["email"],
        WalletCurrency.USD,
    )
    receiver_user, _ = await _get_user_and_wallet(
        receiver_tokens["email"],
        WalletCurrency.USD,
    )

    await _top_up_wallet(client, sender_tokens["access_token"], sender_wallet.id, "10.00")

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "receiver_id": str(receiver_user.id),
            "amount": "50.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient balance"
    assert await _get_wallet_balance(sender_user.id, WalletCurrency.USD) == Decimal("10.0000")
    assert await _get_wallet_balance(receiver_user.id, WalletCurrency.USD) == Decimal("0.0000")
    assert stub_fraud_scoring == []


@pytest.mark.anyio
async def test_send_money_is_idempotent(client, stub_fraud_scoring):
    sender_tokens = await _register_user(client, "idem-sender")
    receiver_tokens = await _register_user(client, "idem-receiver")

    sender_user, sender_wallet = await _get_user_and_wallet(
        sender_tokens["email"],
        WalletCurrency.USD,
    )
    receiver_user, _ = await _get_user_and_wallet(
        receiver_tokens["email"],
        WalletCurrency.USD,
    )

    await _top_up_wallet(client, sender_tokens["access_token"], sender_wallet.id, "90.00")

    idempotency_key = uuid4().hex
    request_body = {
        "receiver_id": str(receiver_user.id),
        "amount": "40.00",
        "currency": "USD",
    }
    headers = {
        "Authorization": f"Bearer {sender_tokens['access_token']}",
        "X-Idempotency-Key": idempotency_key,
    }

    first = await client.post("/api/v1/transactions/send", headers=headers, json=request_body)
    second = await client.post("/api/v1/transactions/send", headers=headers, json=request_body)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert await _get_wallet_balance(sender_user.id, WalletCurrency.USD) == Decimal("50.0000")
    assert await _get_wallet_balance(receiver_user.id, WalletCurrency.USD) == Decimal("40.0000")
    assert stub_fraud_scoring == [first.json()["transaction_id"]]


@pytest.mark.anyio
async def test_send_money_creates_audit_log_row(client, stub_fraud_scoring):
    sender_tokens = await _register_user(client, "audit-sender")
    receiver_tokens = await _register_user(client, "audit-receiver")

    sender_user, sender_wallet = await _get_user_and_wallet(
        sender_tokens["email"],
        WalletCurrency.USD,
    )
    receiver_user, _ = await _get_user_and_wallet(
        receiver_tokens["email"],
        WalletCurrency.USD,
    )

    await _top_up_wallet(client, sender_tokens["access_token"], sender_wallet.id, "60.00")

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "receiver_id": str(receiver_user.id),
            "amount": "15.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 200, response.text
    transaction_id = response.json()["transaction_id"]

    async with AsyncSessionLocal() as session:
        audit_logs = (
            await session.execute(
                select(TransactionAuditLog)
                .where(TransactionAuditLog.transaction_id == transaction_id)
                .order_by(TransactionAuditLog.id.asc())
            )
        ).scalars().all()

    assert any(log.action == "created" for log in audit_logs)
    assert audit_logs[0].actor_id == sender_user.id
    assert stub_fraud_scoring == [transaction_id]


@pytest.mark.anyio
async def test_send_money_to_nonexistent_recipient_keeps_balance_unchanged(client, stub_fraud_scoring):
    sender_tokens = await _register_user(client, "missing-recipient-sender")

    sender_user, sender_wallet = await _get_user_and_wallet(
        sender_tokens["email"],
        WalletCurrency.USD,
    )

    await _top_up_wallet(client, sender_tokens["access_token"], sender_wallet.id, "30.00")

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "receiver_id": "999999",
            "amount": "5.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Sender or receiver has no USD wallet"
    assert await _get_wallet_balance(sender_user.id, WalletCurrency.USD) == Decimal("30.0000")
    assert stub_fraud_scoring == []
