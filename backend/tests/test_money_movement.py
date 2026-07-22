from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.transaction import Transaction
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


async def _top_up_wallet(
    client, access_token: str, wallet_id: int, amount: str, idempotency_key: str | None = None
) -> None:
    # DEVATTECH-125: X-Idempotency-Key is now required on this endpoint.
    # Defaults to a fresh key per call so every EXISTING call site's
    # intent (a brand-new, non-retried top-up) is preserved unchanged --
    # only tests that specifically exercise retry/idempotency behavior
    # pass an explicit, reused key.
    response = await client.post(
        "/api/v1/accounts/top-up",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Idempotency-Key": idempotency_key or uuid4().hex,
        },
        json={
            "wallet_id": wallet_id,
            "amount": amount,
            "payment_method_id": "pm_card_visa_test_123",
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

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error": "insufficient_balance",
        "available": "10.0000",
        "requested": "50.00",
    }
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


# --- NBL-411: card top-up ---


async def _top_up_wallet_raw(
    client, access_token: str, wallet_id: int, amount: str, idempotency_key: str | None = None
):
    """
    Like _top_up_wallet above, but returns the raw response instead of
    asserting 200 -- needed here since these tests exercise non-200 paths
    (gateway decline, daily limit) that _top_up_wallet's assert would mask.

    DEVATTECH-125: same default-fresh-key-per-call convention as
    _top_up_wallet above.
    """
    return await client.post(
        "/api/v1/accounts/top-up",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Idempotency-Key": idempotency_key or uuid4().hex,
        },
        json={
            "wallet_id": wallet_id,
            "amount": amount,
            "payment_method_id": "pm_card_visa_test_123",
        },
    )


@pytest.mark.anyio
async def test_top_up_success_credits_wallet_balance(client):
    """
    Happy path (NBL-411): a successful Stripe charge credits the wallet by
    the top-up amount. The default autouse mock_payment_gateway fixture
    (conftest.py) already fakes a successful charge_card() call, so no
    per-test monkeypatch is needed here.
    """
    tokens = await _register_user(client, "topup-success")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await _top_up_wallet_raw(client, tokens["access_token"], wallet.id, "75.00")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert Decimal(body["top_up_amount"]) == Decimal("75.00")
    assert Decimal(body["new_balance"]) == Decimal("75.0000")
    assert await _get_wallet_balance(user.id, WalletCurrency.USD) == Decimal("75.0000")


@pytest.mark.anyio
async def test_top_up_declined_by_gateway_does_not_credit_wallet(client, monkeypatch):
    """
    DEVATTECH-131 (was NBL-411, updated for the real Stripe integration):
    a declined card must surface as a 402 with the card_declined shape
    and must NOT touch the wallet balance.
    """
    from app.services.stripe_gateway import CardDeclinedError

    async def _declined_charge_card(payment_method_id, amount, currency, idempotency_key):
        raise CardDeclinedError("Insufficient funds on card")

    monkeypatch.setattr(
        "app.api.v1.endpoints.accounts.charge_card",
        _declined_charge_card,
    )

    tokens = await _register_user(client, "topup-declined")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await _top_up_wallet_raw(client, tokens["access_token"], wallet.id, "50.00")

    assert response.status_code == 402, response.text
    assert response.json()["detail"] == {
        "error": "card_declined",
        "gateway_message": "Insufficient funds on card",
    }
    assert await _get_wallet_balance(user.id, WalletCurrency.USD) == Decimal("0.0000")


@pytest.mark.anyio
async def test_top_up_rejects_usdt_wallet(client):
    """
    DEVATTECH-131: card top-up only supports USD/LBP -- Stripe charges a
    card and settles in fiat, there's no path from that to crediting a
    USDT wallet directly. Must reject before ever calling charge_card().
    """
    tokens = await _register_user(client, "topup-usdt")
    user, usdt_wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USDT)

    response = await _top_up_wallet_raw(client, tokens["access_token"], usdt_wallet.id, "10.00")

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error"] == "unsupported_topup_currency"
    assert await _get_wallet_balance(user.id, WalletCurrency.USDT) == Decimal("0.0000")


@pytest.mark.anyio
async def test_top_up_lbp_wallet_succeeds(client):
    """
    DEVATTECH-131: LBP is in scope alongside USD (confirmed decision --
    see stripe_gateway.py's SUPPORTED_CURRENCIES).

    Amount is deliberately small (500 LBP, not a realistic top-up size):
    TOPUP_DAILY_LIMIT (app/core/redis.py) is a flat Decimal("1000")
    applied to every currency with no conversion -- pre-existing, not
    introduced by this ticket, and out of scope to fix here. In practice
    this caps LBP top-ups at ~1000 LBP/day (a fraction of a cent), which
    makes real LBP top-up unusable. Flagged separately as a follow-up;
    this test only needs an amount under that cap to prove the
    USD-vs-LBP currency-conversion path itself (_to_minor_units) works.
    """
    tokens = await _register_user(client, "topup-lbp")
    user, lbp_wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.LBP)

    response = await _top_up_wallet_raw(client, tokens["access_token"], lbp_wallet.id, "500.00")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert Decimal(body["new_balance"]) == Decimal("500.0000")
    assert await _get_wallet_balance(user.id, WalletCurrency.LBP) == Decimal("500.0000")


@pytest.mark.anyio
async def test_top_up_gateway_unavailable_returns_502_without_crediting(client, monkeypatch):
    """
    DEVATTECH-131: a non-decline Stripe failure (network, API outage,
    misconfiguration) must surface as 502, matching the old fake
    gateway's 5xx contract, and must not touch the wallet balance.
    """
    from app.services.stripe_gateway import GatewayUnavailableError

    async def _unavailable_charge_card(payment_method_id, amount, currency, idempotency_key):
        raise GatewayUnavailableError("stripe api outage")

    monkeypatch.setattr(
        "app.api.v1.endpoints.accounts.charge_card",
        _unavailable_charge_card,
    )

    tokens = await _register_user(client, "topup-unavailable")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await _top_up_wallet_raw(client, tokens["access_token"], wallet.id, "20.00")

    assert response.status_code == 502, response.text
    assert await _get_wallet_balance(user.id, WalletCurrency.USD) == Decimal("0.0000")


@pytest.mark.anyio
async def test_top_up_exceeding_daily_limit_returns_422(client):
    """
    NBL-411: the $1000/day cap is enforced across multiple top-ups in the
    same UTC day. First top-up (600) succeeds and credits the wallet;
    second (500) would bring the day's total to 1100 > 1000 and must be
    rejected with 422 before the gateway is ever charged, leaving the
    balance at exactly the first top-up's amount.
    """
    tokens = await _register_user(client, "topup-limit")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    first = await _top_up_wallet_raw(client, tokens["access_token"], wallet.id, "600.00")
    assert first.status_code == 200, first.text

    second = await _top_up_wallet_raw(client, tokens["access_token"], wallet.id, "500.00")

    assert second.status_code == 422, second.text
    body = second.json()["detail"]
    assert body["error"] == "daily_topup_limit_exceeded"
    assert Decimal(body["daily_limit"]) == Decimal("1000")
    assert Decimal(body["already_topped_up_today"]) == Decimal("600.00")
    assert Decimal(body["requested"]) == Decimal("500.00")
    assert await _get_wallet_balance(user.id, WalletCurrency.USD) == Decimal("600.0000")


@pytest.mark.anyio
async def test_top_up_success_creates_transaction_row(client):
    """
    NBL-411: a successful top-up must insert a traceable Transaction row
    (sender_id == receiver_id == the user, category='TopUp', status=completed) --
    not just mutate the wallet balance in place.
    """
    tokens = await _register_user(client, "topup-txrow")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await _top_up_wallet_raw(client, tokens["access_token"], wallet.id, "42.00")
    assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Transaction).where(
                Transaction.sender_id == user.id,
                Transaction.receiver_id == user.id,
                Transaction.category == "TopUp",
            )
        )
        transactions = result.scalars().all()

    assert len(transactions) == 1
    tx = transactions[0]
    assert Decimal(tx.amount) == Decimal("42.00")
    assert tx.status.value == "completed"
    assert tx.currency.value == "USD"


@pytest.mark.anyio
async def test_top_up_is_idempotent(client, monkeypatch):
    """
    DEVATTECH-125: same X-Idempotency-Key retried against /accounts/top-up
    must return the identical cached response, credit the wallet exactly
    once, and must NOT call the payment gateway a second time -- the
    cache-hit check happens before the gateway call, per approved scope.
    """
    call_count = {"count": 0}

    async def _counting_charge_card(payment_method_id, amount, currency, idempotency_key):
        call_count["count"] += 1
        return "pi_test_idempotent_123"

    monkeypatch.setattr(
        "app.api.v1.endpoints.accounts.charge_card",
        _counting_charge_card,
    )

    tokens = await _register_user(client, "topup-idem")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    idempotency_key = uuid4().hex
    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Idempotency-Key": idempotency_key,
    }
    request_body = {
        "wallet_id": wallet.id,
        "amount": "20.00",
        "payment_method_id": "pm_card_visa_test_123",
    }

    first = await client.post("/api/v1/accounts/top-up", headers=headers, json=request_body)
    second = await client.post("/api/v1/accounts/top-up", headers=headers, json=request_body)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert await _get_wallet_balance(user.id, WalletCurrency.USD) == Decimal("20.0000")
    assert call_count["count"] == 1


@pytest.mark.anyio
async def test_shared_idempotency_key_does_not_collide_across_endpoints(client, stub_fraud_scoring):
    """
    DEVATTECH-125 regression: the SAME raw X-Idempotency-Key value, reused
    by the same user across /accounts/top-up and /transactions/send, must
    NOT collide. hash_idempotency_key(user_id, raw_key) ignores its
    `endpoint` parameter when raw_key is passed directly (see
    app/core/redis.py, not modified by this ticket) -- the "topup:"
    prefix applied only at the top-up call site is what prevents this
    collision, without touching the shared Redis helper. Both calls must
    succeed independently, each producing its own distinct Transaction
    row with a distinct idempotency_key.
    """
    sender_tokens = await _register_user(client, "collision-sender")
    receiver_tokens = await _register_user(client, "collision-receiver")

    sender_user, sender_wallet = await _get_user_and_wallet(
        sender_tokens["email"], WalletCurrency.USD
    )
    receiver_user, _ = await _get_user_and_wallet(
        receiver_tokens["email"], WalletCurrency.USD
    )

    shared_key = uuid4().hex

    top_up_response = await client.post(
        "/api/v1/accounts/top-up",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": shared_key,
        },
        json={
            "wallet_id": sender_wallet.id,
            "amount": "80.00",
            "payment_method_id": "pm_card_visa_test_123",
        },
    )
    assert top_up_response.status_code == 200, top_up_response.text

    send_response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender_tokens['access_token']}",
            "X-Idempotency-Key": shared_key,
        },
        json={
            "receiver_id": str(receiver_user.id),
            "amount": "30.00",
            "currency": "USD",
        },
    )
    assert send_response.status_code == 200, send_response.text

    # Both operations must have actually happened -- proving neither call
    # was silently short-circuited as a false "duplicate" of the other.
    assert await _get_wallet_balance(sender_user.id, WalletCurrency.USD) == Decimal("50.0000")
    assert await _get_wallet_balance(receiver_user.id, WalletCurrency.USD) == Decimal("30.0000")

    async with AsyncSessionLocal() as session:
        topup_tx = (
            await session.execute(
                select(Transaction).where(
                    Transaction.sender_id == sender_user.id,
                    Transaction.receiver_id == sender_user.id,
                    Transaction.category == "TopUp",
                )
            )
        ).scalar_one()
        send_tx = (
            await session.execute(
                select(Transaction).where(
                    Transaction.id == send_response.json()["transaction_id"]
                )
            )
        ).scalar_one()

    assert topup_tx.idempotency_key != send_tx.idempotency_key
    assert stub_fraud_scoring == [send_tx.id]
