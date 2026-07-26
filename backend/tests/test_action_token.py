from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.user import KYCStatus, User
from app.models.wallet import Wallet, WalletCurrency
from app.services.otp import generate_and_store_otp


@pytest.fixture(autouse=True)
def _enable_action_token(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_ACTION_TOKEN", True)

async def _approve_kyc(user_id: int) -> None:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        user.kyc_status = KYCStatus.approved
        await session.commit()


async def _set_iban(user_id: int, currency: WalletCurrency, iban: str) -> None:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(
                select(Wallet).where(
                    Wallet.user_id == user_id,
                    Wallet.currency == currency,
                )
            )
        ).scalar_one()
        wallet.iban = iban
        await session.commit()


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
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        return user.id


async def _get_wallet_id(user_id: int) -> int:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(
                select(Wallet).where(
                    Wallet.user_id == user_id,
                    Wallet.currency == WalletCurrency.USD,
                )
            )
        ).scalar_one()
        return wallet.id


async def _top_up(client, access_token: str, wallet_id: int, amount: str) -> None:
    # DEVATTECH-125: X-Idempotency-Key is now required on this endpoint.
    response = await client.post(
        "/api/v1/accounts/top-up",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "wallet_id": wallet_id,
            "amount": amount,
            "payment_method_id": "pm_card_visa_test_123",
        },
    )
    assert response.status_code == 200, response.text


async def _get_action_token(
    client,
    access_token: str,
    user_id: int,
    phone: str,
) -> str:
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
    sender = await _register_user(client, "atsender")
    receiver = await _register_user(client, "atreceiver")

    sender_id = await _get_user_id(sender["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)

    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")
    token = await _get_action_token(
        client,
        sender["access_token"],
        sender_id,
        sender["phone"],
    )

    with patch("app.api.v1.endpoints.transactions.score_transaction.delay") as mock_delay:
        response = await client.post(
            "/api/v1/transactions/send",
            headers={
                "Authorization": f"Bearer {sender['access_token']}",
                "X-Idempotency-Key": uuid4().hex,
                "X-Action-Token": token,
            },
            json={
                "receiver_id": str(receiver_id),
                "amount": "10.00",
                "currency": "USD",
            },
        )

    assert response.status_code == 200, response.text
    mock_delay.assert_called_once()


async def test_send_money_missing_action_token_returns_403(client):
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
        json={
            "receiver_id": str(receiver_id),
            "amount": "10.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 403


async def test_send_money_action_token_replay_returns_403(client):
    sender = await _register_user(client, "atreplay")
    receiver = await _register_user(client, "atreplay2")

    sender_id = await _get_user_id(sender["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)

    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")
    token = await _get_action_token(
        client,
        sender["access_token"],
        sender_id,
        sender["phone"],
    )

    headers = {
        "Authorization": f"Bearer {sender['access_token']}",
        "X-Action-Token": token,
    }

    with patch("app.api.v1.endpoints.transactions.score_transaction.delay") as mock_delay:
        first = await client.post(
            "/api/v1/transactions/send",
            headers={**headers, "X-Idempotency-Key": uuid4().hex},
            json={
                "receiver_id": str(receiver_id),
                "amount": "5.00",
                "currency": "USD",
            },
        )

    assert first.status_code == 200, first.text
    mock_delay.assert_called_once()

    second = await client.post(
        "/api/v1/transactions/send",
        headers={**headers, "X-Idempotency-Key": uuid4().hex},
        json={
            "receiver_id": str(receiver_id),
            "amount": "5.00",
            "currency": "USD",
        },
    )

    assert second.status_code == 403


async def test_send_money_another_users_action_token_returns_403(client):
    sender = await _register_user(client, "atcross")
    other_user = await _register_user(client, "atcrossother")
    receiver = await _register_user(client, "atcrossreceiver")

    sender_id = await _get_user_id(sender["email"])
    other_id = await _get_user_id(other_user["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)

    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")

    other_token = await _get_action_token(
        client,
        other_user["access_token"],
        other_id,
        other_user["phone"],
    )

    response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
            "X-Action-Token": other_token,
        },
        json={
            "receiver_id": str(receiver_id),
            "amount": "5.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 403


async def test_exchange_execute_requires_auth(client):
    response = await client.post(
        "/api/v1/exchange/execute",
        json={
            "from_currency": "USD",
            "to_currency": "LBP",
            "amount": "10.00",
        },
    )

    assert response.status_code == 401


async def test_exchange_execute_missing_action_token_returns_403(client):
    user = await _register_user(client, "atexchange")

    response = await client.post(
        "/api/v1/exchange/execute",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={
            "from_currency": "USD",
            "to_currency": "LBP",
            "amount": "10.00",
        },
    )

    assert response.status_code == 403


async def test_neo_transfer_mobile_missing_action_token_returns_403(client):
    sender = await _register_user(client, "atneo")
    receiver = await _register_user(client, "atneoreceiver")

    sender_id = await _get_user_id(sender["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)

    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")

    response = await client.post(
        "/api/v1/transfer/neo/mobile",
        headers={"Authorization": f"Bearer {sender['access_token']}"},
        json={
            "receiver_mobile": receiver["phone"],
            "amount": "10.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 403

@pytest.mark.anyio
async def test_neo_transfer_mobile_happy_path_succeeds(client):
    # Regression test: transfer_service.execute_transfer() calls
    # transactions.send_money() directly (not over HTTP), and send_money()
    # requires a `request: Request` argument for its DEVATTECH-107 rate
    # limiting. That argument was missing on this call path -- every real
    # /transfer/neo/mobile and /transfer/neo/iban request 500'd with
    # `TypeError: send_money() missing 1 required positional argument:
    # 'request'`, and nothing caught it because the only existing tests on
    # these endpoints were rejection-path tests (missing action token,
    # rate limits) that never reach the actual send_money() call.
    sender = await _register_user(client, "neohappy")
    receiver = await _register_user(client, "neohappyreceiver")

    sender_id = await _get_user_id(sender["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)

    await _approve_kyc(receiver_id)
    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")
    token = await _get_action_token(
        client,
        sender["access_token"],
        sender_id,
        sender["phone"],
    )

    with patch("app.api.v1.endpoints.transactions.score_transaction.delay"):
        response = await client.post(
            "/api/v1/transfer/neo/mobile",
            headers={
                "Authorization": f"Bearer {sender['access_token']}",
                "X-Idempotency-Key": uuid4().hex,
                "X-Action-Token": token,
            },
            json={
                "receiver_phone": receiver["phone"],
                "amount": "10.00",
                "currency": "USD",
            },
        )

    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_neo_transfer_iban_happy_path_succeeds(client):
    # Same regression as test_neo_transfer_mobile_happy_path_succeeds
    # above, for the IBAN path specifically (execute_transfer_by_iban ->
    # execute_transfer -> send_money).
    sender = await _register_user(client, "neoibanhappy")
    receiver = await _register_user(client, "neoibanhappyreceiver")

    sender_id = await _get_user_id(sender["email"])
    receiver_id = await _get_user_id(receiver["email"])
    sender_wallet_id = await _get_wallet_id(sender_id)
    # generate_iban() (account_utils.py) produces a 24-character IBAN
    # ("LB" + 2 check digits + 20-char BBAN), but this endpoint's own
    # LEBANESE_IBAN_PATTERN requires 28 ("LB" + 26) -- a separate,
    # pre-existing format mismatch that makes every real generated IBAN
    # fail this endpoint's validation. Not this test's concern (or this
    # fix's scope) -- write a pattern-compliant IBAN directly so this
    # test isolates the request-param regression it exists to catch.
    receiver_iban = "LB" + ("02" + "1234567890" * 3)[:26]
    await _set_iban(receiver_id, WalletCurrency.USD, receiver_iban)

    await _approve_kyc(receiver_id)
    await _top_up(client, sender["access_token"], sender_wallet_id, "50.00")
    token = await _get_action_token(
        client,
        sender["access_token"],
        sender_id,
        sender["phone"],
    )

    with patch("app.api.v1.endpoints.transactions.score_transaction.delay"):
        response = await client.post(
            "/api/v1/transfer/neo/iban",
            headers={
                "Authorization": f"Bearer {sender['access_token']}",
                "X-Idempotency-Key": uuid4().hex,
                "X-Action-Token": token,
            },
            json={
                "receiver_iban": receiver_iban,
                "amount": "10.00",
                "currency": "USD",
            },
        )

    assert response.status_code == 200, response.text