import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.services.chatbot_intent import GROQ_API_URL

_REAL_POST = httpx.AsyncClient.post


async def _mock_chatbot_response(message, session_id, user_id, db):
    await db.commit()
    return "Your balance is available in Accounts."


def _groq_success(intent: str, confidence: float):
    """Only fakes calls to the Groq endpoint; everything else (the test
    client's own calls into the app) passes through to the real post()."""

    async def _post(self, url, *args, **kwargs):
        if str(url) == GROQ_API_URL:
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"intent": intent, "confidence": confidence}
                                )
                            }
                        }
                    ]
                },
            )
        return await _REAL_POST(self, url, *args, **kwargs)

    return _post


def _groq_unreachable():
    async def _post(self, url, *args, **kwargs):
        if str(url) == GROQ_API_URL:
            raise httpx.ConnectError("boom")
        return await _REAL_POST(self, url, *args, **kwargs)

    return _post


@pytest.fixture
async def auth_tokens(client, db_session):
    """Register and login a test user, return tokens."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Chatbot Test User",
            "email": "chatbottest@neobank.com",
            "phone": "+96170000099",
            "password": "TestPass123",
        },
    )
    from app.models.user import KYCStatus, User
    from sqlalchemy import select

    user = await db_session.scalar(
        select(User).where(User.email == "chatbottest@neobank.com")
    )
    user.email_verified_at = datetime.now(timezone.utc)
    user.kyc_status = KYCStatus.approved
    await db_session.commit()
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "chatbottest@neobank.com",
            "password": "TestPass123",
        },
    )
    return response.json()


async def test_non_approved_chatbot_transfer_is_blocked_without_pending_action(
    client, auth_tokens, mock_redis, db_session
):
    from app.models.user import KYCStatus, User
    from sqlalchemy import select

    user = await db_session.scalar(
        select(User).where(User.email == "chatbottest@neobank.com")
    )
    user.kyc_status = KYCStatus.pending
    await db_session.commit()

    session_id = "kyc-locked-chatbot-transfer"
    response = await client.post(
        "/api/v1/chatbot/message",
        json={"session_id": session_id, "message": "send 10 USD to +96170123456"},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["confirmation_required"] is False
    assert "complete your profile" in response.json()["reply"].lower()
    assert await mock_redis.get(f"chat_action:{session_id}") is None
    assert await mock_redis.get(f"chat_incomplete_action:{session_id}") is None


async def test_chatbot_general_intent_happy_path(
    client,
    auth_tokens,
):
    with (
        patch(
            "httpx.AsyncClient.post",
            new=_groq_success("GENERAL", 0.4),
        ),
        patch(
            "app.api.v1.endpoints.chatbot.get_chatbot_response",
            new_callable=AsyncMock,
            return_value="Hello! How can I help you?",
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": "test-general-session",
                "message": "hi there",
            },
            headers={"Authorization": (f"Bearer {auth_tokens['access_token']}")},
        )

    assert response.status_code == 200

    data = response.json()

    assert data["reply"].startswith("Hello!")
    assert data["session_id"] == "test-general-session"
    assert data["intent"] == "GREETING"
    assert data["confidence"] == 1.0
    assert data["confirmation_required"] is False


async def test_chatbot_requires_auth(client):
    """Auth rejected: no Authorization header returns 401."""
    response = await client.post("/api/v1/chatbot/message", json={"message": "hi"})
    assert response.status_code == 401


async def test_chatbot_transfer_intent_requires_confirmation(
    client,
    auth_tokens,
):
    with (
        patch(
            "httpx.AsyncClient.post",
            new=_groq_success(
                "TRANSFER_INTENT",
                0.92,
            ),
        ),
        patch(
            "app.api.v1.endpoints.chatbot.save_chat_turn",
            new_callable=AsyncMock,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": "test-transfer-session",
                "message": "send 100 USD to +96170123456",
            },
            headers={"Authorization": (f"Bearer {auth_tokens['access_token']}")},
        )

    assert response.status_code == 200

    data = response.json()

    assert data["session_id"] == "test-transfer-session"
    assert data["intent"] == "TRANSFER_INTENT"
    assert data["confidence"] == 1.0
    assert data["confirmation_required"] is True
    assert "confirm" in data["reply"].lower()


async def test_chatbot_balance_is_deterministic_when_groq_is_unavailable(
    client,
    auth_tokens,
):
    with (
        patch(
            "httpx.AsyncClient.post",
            new=_groq_unreachable(),
        ),
        patch(
            "app.api.v1.endpoints.chatbot.get_chatbot_response",
            new_callable=AsyncMock,
            return_value="I am still available to help.",
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": "test-fallback-session",
                "message": "what's my balance",
            },
            headers={"Authorization": (f"Bearer {auth_tokens['access_token']}")},
        )

    assert response.status_code == 200

    data = response.json()

    assert "USD: $0.00" in data["reply"]
    assert data["session_id"] == "test-fallback-session"
    assert data["intent"] == "BALANCE_QUERY"
    assert data["confidence"] == 1.0
    assert data["confirmation_required"] is False


async def test_chatbot_logs_intent_classification(client, auth_tokens):
    """Chatbot message saves intent classification into chatbot_logs."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import engine
    from app.models.chatbot_log import ChatbotLog

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("BALANCE_QUERY", 0.87)),
        patch(
            "app.api.v1.endpoints.chatbot.get_chatbot_response",
            side_effect=_mock_chatbot_response,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "message": "what is my balance?",
                "session_id": "test-intent-session",
            },
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200

    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(ChatbotLog)
            .where(ChatbotLog.intent == "BALANCE_QUERY")
            .order_by(ChatbotLog.id.desc())
            .limit(1)
        )
        log = result.scalar_one_or_none()

    assert log is not None
    assert log.confidence == 1.0
    assert log.latency_ms >= 0

async def test_chatbot_banned_ip_returns_429(client, auth_tokens, mock_redis):
    """Banned-IP check applies to /chatbot/message (DEVATTECH-120)."""
    await mock_redis.set("banned:127.0.0.1", "1", ex=3600)

    response = await client.post(
        "/api/v1/chatbot/message",
        json={"session_id": "test-banned-session", "message": "hi"},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert response.status_code == 429
    assert "banned" in response.json()["detail"].lower()

async def _get_chatbot_test_user_id() -> int:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == "chatbottest@neobank.com")
        )
        user = result.scalar_one()
        return user.id


async def _store_test_pending_transfer(
    mock_redis, session_id: str, user_id: int
) -> None:
    await mock_redis.set(
        f"chat_action:{session_id}",
        json.dumps(
            {
                "type": "transfer",
                "method": "mobile",
                "recipient": "+96170123456",
                "receiver_phone": "+96170123456",
                "amount": "10",
                "currency": "USD",
                "user_id": user_id,
                "idempotency_key": f"chatbot:{session_id}:test",
            }
        ),
        ex=300,
    )


def _transfer_receipt():
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.schemas.transfer import TransferReceipt

    return TransferReceipt(
        transaction_id=123,
        amount=Decimal("10"),
        currency="USD",
        receiver_display_name="Receiver User",
        sender_new_balance=Decimal("90"),
        timestamp=datetime.now(timezone.utc),
    )


async def test_chatbot_transfer_intent_stores_pending_action(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-transfer-store-session"

    with patch(
        "httpx.AsyncClient.post",
        new=_groq_success("TRANSFER_INTENT", 0.92),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "send 10 USD to +96170123456",
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
            },
        )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["confirmation_required"] is True
    assert data["pending_action"] == {
        "type": "transfer",
        "method": "mobile",
        "recipient": "+96170123456",
        "amount": "10",
        "currency": "USD",
        "source_account": data["pending_action"]["source_account"],
        "fee": "0.00",
        "total_debit": "10.00",
    }
    assert data["transfer_receipt"] is None

    raw_pending = await mock_redis.get(f"chat_action:{session_id}")
    assert raw_pending is not None

    pending_action = json.loads(raw_pending)
    assert pending_action["type"] == "transfer"
    assert pending_action["method"] == "mobile"
    assert pending_action["receiver_phone"] == "+96170123456"
    assert pending_action["amount"] == "10"
    assert pending_action["currency"] == "USD"

    repeated = await client.post(
        "/api/v1/chatbot/message",
        json={
            "session_id": session_id,
            "message": "send 10 USD to +96170123456",
        },
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert repeated.status_code == 200, repeated.text
    repeated_pending = json.loads(await mock_redis.get(f"chat_action:{session_id}"))
    assert repeated.json()["confirmation_required"] is True
    assert repeated_pending["idempotency_key"] == pending_action["idempotency_key"]


async def test_chatbot_accumulates_transfer_draft_across_messages(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-multi-turn-transfer-session"
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    with patch(
        "httpx.AsyncClient.post",
        new=_groq_success("TRANSFER_INTENT", 0.92),
    ):
        first = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "send 50 USD",
            },
            headers=headers,
        )

    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["confirmation_required"] is False
    assert first_data["pending_action"] is None
    assert "who should i send it to" in first_data["reply"].lower()
    assert await mock_redis.get(f"chat_action:{session_id}") is None
    assert await mock_redis.get(f"chat_incomplete_action:{session_id}") is not None
    partial_ttl = await mock_redis.ttl(f"chat_incomplete_action:{session_id}")
    assert 0 < partial_ttl <= 300

    # A phone-number-only answer may be classified as GENERAL. The existing
    # incomplete draft supplies the conversational context.
    with patch(
        "httpx.AsyncClient.post",
        new=_groq_success("GENERAL", 0.9),
    ):
        second = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "+96170123456",
            },
            headers=headers,
        )

    assert second.status_code == 200, second.text
    second_data = second.json()
    assert second_data["confirmation_required"] is True
    assert second_data["pending_action"] == {
        "type": "transfer",
        "method": "mobile",
        "recipient": "+96170123456",
        "amount": "50",
        "currency": "USD",
        "source_account": second_data["pending_action"]["source_account"],
        "fee": "0.00",
        "total_debit": "50.00",
    }
    assert await mock_redis.get(f"chat_incomplete_action:{session_id}") is None
    stored = json.loads(await mock_redis.get(f"chat_action:{session_id}"))
    assert stored["amount"] == "50"
    assert stored["currency"] == "USD"
    assert stored["receiver_phone"] == "+96170123456"


async def test_chatbot_iban_continues_same_incomplete_transfer(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-multi-turn-iban-session"
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    with patch("httpx.AsyncClient.post", new=_groq_success("TRANSFER_INTENT", 0.92)):
        first = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "Transfer 10 USD to lamine yamal",
            },
            headers=headers,
        )

    assert first.status_code == 200, first.text
    before = json.loads(
        await mock_redis.get(f"chat_incomplete_action:{session_id}")
    )

    with patch("httpx.AsyncClient.post", new=_groq_success("OUT_OF_SCOPE", 1.0)):
        second = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "LB1500000016036118400442",
            },
            headers=headers,
        )

    assert second.status_code == 200, second.text
    data = second.json()
    assert data["confirmation_required"] is True
    assert data["pending_action"]["recipient"] == "LB1500000016036118400442"
    assert {
        "recipient",
        "amount",
        "currency",
        "source_account",
        "fee",
        "total_debit",
    } <= data["pending_action"].keys()
    after = json.loads(await mock_redis.get(f"chat_action:{session_id}"))
    assert after["action_id"] == before["action_id"]
    assert after["idempotency_key"] == before["idempotency_key"]
    assert after["receiver_iban"] == "LB1500000016036118400442"
    assert data["transfer_receipt"] is None


async def test_invalid_iban_keeps_incomplete_transfer_active(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-invalid-follow-up-iban-session"
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    with patch("httpx.AsyncClient.post", new=_groq_success("TRANSFER_INTENT", 0.92)):
        await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_id, "message": "send 10 USD"},
            headers=headers,
        )
    before = await mock_redis.get(f"chat_incomplete_action:{session_id}")

    with patch("httpx.AsyncClient.post", new=_groq_success("OUT_OF_SCOPE", 1.0)):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_id, "message": "LB123"},
            headers=headers,
        )

    assert response.status_code == 200, response.text
    assert "iban is invalid" in response.json()["reply"].lower()
    assert await mock_redis.get(f"chat_incomplete_action:{session_id}") == before
    assert await mock_redis.get(f"chat_action:{session_id}") is None


async def test_chatbot_unrelated_reply_discards_incomplete_transfer(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-abandoned-transfer-session"
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    with patch(
        "httpx.AsyncClient.post",
        new=_groq_success("TRANSFER_INTENT", 0.92),
    ):
        first = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_id, "message": "send 50 USD"},
            headers=headers,
        )
    assert first.status_code == 200, first.text
    assert await mock_redis.get(f"chat_incomplete_action:{session_id}") is not None

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.9)),
        patch(
            "app.api.v1.endpoints.chatbot.get_chatbot_response",
            new_callable=AsyncMock,
            return_value="Hello! How can I help?",
        ),
    ):
        unrelated = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "how are you today? I have 2 questions.",
            },
            headers=headers,
        )

    assert unrelated.status_code == 200, unrelated.text
    assert unrelated.json()["confirmation_required"] is False
    assert unrelated.json()["reply"] == (
        "I can only assist with NeoBank services such as balances, "
        "transactions, transfers, and exchange rates."
    )
    assert await mock_redis.get(f"chat_incomplete_action:{session_id}") is None
    assert await mock_redis.get(f"chat_action:{session_id}") is None

    # A later recipient cannot revive the abandoned amount/currency.
    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.9)),
        patch(
            "app.api.v1.endpoints.chatbot.get_chatbot_response",
            new_callable=AsyncMock,
            return_value="How else can I help?",
        ),
    ):
        later = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_id, "message": "+96170123456"},
            headers=headers,
        )
    assert later.status_code == 200, later.text
    assert later.json()["confirmation_required"] is False
    assert await mock_redis.get(f"chat_action:{session_id}") is None


async def test_chatbot_confirm_without_action_token_does_not_execute(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-confirm-missing-token-session"
    user_id = await _get_chatbot_test_user_id()

    await _store_test_pending_transfer(mock_redis, session_id, user_id)

    mock_execute = AsyncMock(return_value=_transfer_receipt())

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)),
        patch(
            "app.api.v1.endpoints.chatbot.execute_transfer_by_mobile",
            new=mock_execute,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "confirm",
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
            },
        )

    assert response.status_code == 403
    mock_execute.assert_not_called()

    assert await mock_redis.get(f"chat_action:{session_id}") is not None


async def test_chatbot_confirm_with_valid_action_token_executes_transfer_service(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-confirm-valid-token-session"
    user_id = await _get_chatbot_test_user_id()
    action_token = "chatbot-action-token"

    await _store_test_pending_transfer(mock_redis, session_id, user_id)
    await mock_redis.set(f"action_token:{user_id}", action_token, ex=300)

    mock_execute = AsyncMock(return_value=_transfer_receipt())

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)),
        patch(
            "app.api.v1.endpoints.chatbot.execute_transfer_by_mobile",
            new=mock_execute,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "confirm",
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-Action-Token": action_token,
            },
        )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["confirmation_required"] is False
    assert data["pending_action"] is None
    assert data["transfer_receipt"]["transaction_id"] == 123
    assert data["transfer_receipt"]["receiver_display_name"] == "Receiver User"

    mock_execute.assert_awaited_once()
    assert await mock_redis.get(f"chat_action:{session_id}") is None
    assert await mock_redis.get(f"action_token:{user_id}") is None


async def test_chatbot_confirm_executes_real_mobile_transfer_path(
    client,
    auth_tokens,
    mock_redis,
):
    """Exercise the real service path; do not mock execute_transfer_by_mobile."""
    from decimal import Decimal

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.user import KYCStatus, User
    from app.models.wallet import Wallet, WalletCurrency

    receiver_tokens = await _register_chatbot_user(client, "confirmreceiver")
    sender_id = await _get_chatbot_test_user_id()

    async with AsyncSessionLocal() as session:
        sender = await session.get(User, sender_id)
        receiver = await session.scalar(
            select(User).where(User.id == int(receiver_tokens["user"]["id"]))
        )
        sender.kyc_status = KYCStatus.approved
        receiver.kyc_status = KYCStatus.approved
        sender_wallet = await session.scalar(
            select(Wallet).where(
                Wallet.user_id == sender_id,
                Wallet.currency == WalletCurrency.USD,
            )
        )
        sender_wallet.balance = Decimal("50")
        await session.commit()

    session_id = "test-real-confirm-transfer-session"
    action_token = "real-confirm-action-token"
    await _store_test_pending_transfer(mock_redis, session_id, sender_id)
    pending = json.loads(await mock_redis.get(f"chat_action:{session_id}"))
    pending["recipient"] = receiver.phone
    pending["receiver_phone"] = receiver.phone
    await mock_redis.set(
        f"chat_action:{session_id}",
        json.dumps(pending),
        ex=300,
    )
    await mock_redis.set(f"action_token:{sender_id}", action_token, ex=300)

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)),
        patch(
            "app.api.v1.endpoints.transactions.score_transaction.delay",
            side_effect=RuntimeError("Method Not Allowed"),
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_id, "message": "confirm"},
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-Action-Token": action_token,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["transfer_receipt"]["amount"] == "10.0000"
    assert await mock_redis.get(f"chat_action:{session_id}") is None


async def test_chatbot_cancel_discards_pending_action(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-cancel-pending-session"
    user_id = await _get_chatbot_test_user_id()

    await _store_test_pending_transfer(mock_redis, session_id, user_id)

    with patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": session_id,
                "message": "cancel",
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
            },
        )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["confirmation_required"] is False
    assert "cancelled" in data["reply"].lower()
    assert await mock_redis.get(f"chat_action:{session_id}") is None


async def test_chatbot_cancel_does_not_delete_another_users_pending_action(
    client,
    auth_tokens,
    mock_redis,
):
    session_id = "test-unauthorized-cancel-session"
    owner_user_id = await _get_chatbot_test_user_id()
    other_user_tokens = await _register_chatbot_user(client, "cancelattacker")

    await _store_test_pending_transfer(
        mock_redis,
        session_id,
        owner_user_id,
    )

    with patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_id, "message": "cancel"},
            headers={
                "Authorization": (
                    f"Bearer {other_user_tokens['access_token']}"
                ),
            },
        )

    assert response.status_code == 200, response.text
    assert "no pending transfer to cancel" in response.json()["reply"].lower()
    assert await mock_redis.get(f"chat_action:{session_id}") is not None


async def test_chatbot_rejects_oversized_message(client, auth_tokens):
    response = await client.post(
        "/api/v1/chatbot/message",
        json={
            "session_id": "oversized-message-session",
            "message": "x" * 2001,
        },
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert response.status_code == 422


async def test_chatbot_confirm_without_pending_action_does_not_execute(
    client,
    auth_tokens,
):
    mock_execute = AsyncMock(return_value=_transfer_receipt())

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)),
        patch(
            "app.api.v1.endpoints.chatbot.execute_transfer_by_mobile",
            new=mock_execute,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": "test-expired-pending-session",
                "message": "confirm",
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
            },
        )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["confirmation_required"] is False
    assert "expired" in data["reply"].lower()
    mock_execute.assert_not_called()


async def test_chatbot_confirm_action_token_replay_returns_403(
    client,
    auth_tokens,
    mock_redis,
):
    """
    X-Action-Token single-use on chat-confirm (DEVATTECH-120): a token
    already consumed by one confirm cannot be replayed on a second one.
    """
    user_id = await _get_chatbot_test_user_id()
    action_token = "chatbot-replay-token"

    session_1 = "test-replay-session-1"
    await _store_test_pending_transfer(mock_redis, session_1, user_id)
    await mock_redis.set(f"action_token:{user_id}", action_token, ex=300)

    mock_execute = AsyncMock(return_value=_transfer_receipt())

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)),
        patch(
            "app.api.v1.endpoints.chatbot.execute_transfer_by_mobile",
            new=mock_execute,
        ),
    ):
        first = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_1, "message": "confirm"},
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-Action-Token": action_token,
            },
        )

    assert first.status_code == 200, first.text
    mock_execute.assert_awaited_once()

    # A second, separate pending transfer -- replaying the same (now
    # consumed) token against it must be rejected.
    session_2 = "test-replay-session-2"
    await _store_test_pending_transfer(mock_redis, session_2, user_id)

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)),
        patch(
            "app.api.v1.endpoints.chatbot.execute_transfer_by_mobile",
            new=mock_execute,
        ),
    ):
        second = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_2, "message": "confirm"},
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-Action-Token": action_token,
            },
        )

    assert second.status_code == 403
    # Still only the first call -- replay must not execute a second transfer.
    mock_execute.assert_awaited_once()


async def test_chatbot_confirm_another_users_action_token_returns_403(
    client,
    auth_tokens,
    mock_redis,
):
    """
    Cross-user token on chat-confirm (DEVATTECH-120): a token issued to a
    different user cannot be used to confirm this user's pending transfer.
    """
    user_id = await _get_chatbot_test_user_id()
    other_user_id = user_id + 999999  # doesn't need to be a real user row
    other_users_token = "someone-elses-token"

    session_id = "test-cross-user-token-session"
    await _store_test_pending_transfer(mock_redis, session_id, user_id)
    # Token stored under a DIFFERENT user's action_token key.
    await mock_redis.set(f"action_token:{other_user_id}", other_users_token, ex=300)

    mock_execute = AsyncMock(return_value=_transfer_receipt())

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.1)),
        patch(
            "app.api.v1.endpoints.chatbot.execute_transfer_by_mobile",
            new=mock_execute,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={"session_id": session_id, "message": "confirm"},
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-Action-Token": other_users_token,
            },
        )

    assert response.status_code == 403
    mock_execute.assert_not_called()
    # The pending action must still be there -- rejected before execution.
    assert await mock_redis.get(f"chat_action:{session_id}") is not None


async def _register_chatbot_user(client, label: str) -> dict:
    suffix = uuid4().hex[:10]
    numeric_suffix = f"{int(suffix, 16) % 1_000_000:06d}"
    email = f"{label.lower()}-{suffix}@example.com"

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96171{numeric_suffix}",
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200, response.text

    from app.db.session import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        user.email_verified_at = datetime.now(timezone.utc)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "TestPass123",
        },
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()


async def _create_test_chat_session(
    session_id: str,
    user_id: int,
    messages: list[dict[str, str]],
) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models.chat_session import ChatSession

    async with AsyncSessionLocal() as session:
        session.add(
            ChatSession(
                session_id=session_id,
                user_id=user_id,
                messages=messages,
            )
        )
        await session.commit()


async def test_chatbot_history_returns_owned_session_messages(client, auth_tokens):
    session_id = "history-owned-session"
    user_id = await _get_chatbot_test_user_id()
    messages = [
        {
            "role": "user",
            "content": "what is my balance?",
        },
        {
            "role": "assistant",
            "content": "Your balance is available in Accounts.",
        },
    ]

    await _create_test_chat_session(
        session_id=session_id,
        user_id=user_id,
        messages=messages,
    )

    history_response = await client.get(
        "/api/v1/chatbot/history",
        params={"session_id": session_id},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert history_response.status_code == 200, history_response.text

    data = history_response.json()

    assert data["session_id"] == session_id
    assert data["messages"] == messages


async def test_chatbot_history_requires_auth(client):
    response = await client.get(
        "/api/v1/chatbot/history",
        params={"session_id": "missing-auth-session"},
    )

    assert response.status_code == 401


async def test_chatbot_history_returns_404_for_missing_session(client, auth_tokens):
    response = await client.get(
        "/api/v1/chatbot/history",
        params={"session_id": "does-not-exist"},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat session not found"


async def test_chatbot_history_rejects_other_users_session(client, auth_tokens):
    owner_tokens = await _register_chatbot_user(client, "ownerhistory")
    session_id = "history-owned-by-other-user"

    await _create_test_chat_session(
        session_id=session_id,
        user_id=int(owner_tokens["user"]["id"]),
        messages=[
            {
                "role": "user",
                "content": "hello from owner",
            },
            {
                "role": "assistant",
                "content": "Hello owner.",
            },
        ],
    )

    other_user_response = await client.get(
        "/api/v1/chatbot/history",
        params={"session_id": session_id},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert other_user_response.status_code == 403


async def test_delete_chatbot_session_deletes_owned_session(client, auth_tokens):
    session_id = "delete-owned-session"
    user_id = await _get_chatbot_test_user_id()
    await _create_test_chat_session(
        session_id=session_id,
        user_id=user_id,
        messages=[{"role": "user", "content": "private conversation"}],
    )

    response = await client.delete(
        f"/api/v1/chatbot/session/{session_id}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert response.status_code == 204

    history_response = await client.get(
        "/api/v1/chatbot/history",
        params={"session_id": session_id},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert history_response.status_code == 404


async def test_delete_chatbot_session_returns_404_for_missing(
    client,
    auth_tokens,
):
    response = await client.delete(
        "/api/v1/chatbot/session/delete-session-does-not-exist",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat session not found"


async def test_delete_chatbot_session_requires_auth(client):
    response = await client.delete(
        "/api/v1/chatbot/session/delete-session-without-auth",
    )

    assert response.status_code == 401


async def test_delete_chatbot_session_rejects_other_users_session(
    client,
    auth_tokens,
):
    owner_tokens = await _register_chatbot_user(client, "ownerdelete")
    session_id = "delete-owned-by-other-user"
    messages = [{"role": "user", "content": "owner-only conversation"}]
    await _create_test_chat_session(
        session_id=session_id,
        user_id=int(owner_tokens["user"]["id"]),
        messages=messages,
    )

    response = await client.delete(
        f"/api/v1/chatbot/session/{session_id}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )

    assert response.status_code == 403

    owner_history = await client.get(
        "/api/v1/chatbot/history",
        params={"session_id": session_id},
        headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
    )
    assert owner_history.status_code == 200
    assert owner_history.json()["messages"] == messages


async def test_chatbot_message_uses_20_per_minute_rate_limit(client, auth_tokens):
    mock_rate_limit = AsyncMock()

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.4)),
        patch(
            "app.api.v1.endpoints.chatbot.get_chatbot_response",
            new_callable=AsyncMock,
            return_value="Hello!",
        ),
        patch(
            "app.api.v1.endpoints.chatbot.check_rate_limit",
            new=mock_rate_limit,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": "rate-limit-session",
                "message": "hello",
            },
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200, response.text

    mock_rate_limit.assert_awaited_once()
    call_kwargs = mock_rate_limit.await_args.kwargs
    assert call_kwargs["key_prefix"] == "chatbot_message"
    assert call_kwargs["max_requests"] == 20
    assert call_kwargs["window_seconds"] == 60


async def test_chatbot_logs_never_store_raw_message_text(client, auth_tokens):
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.chatbot_log import ChatbotLog

    raw_message = "my private card number is 4111111111111111"

    with (
        patch("httpx.AsyncClient.post", new=_groq_success("GENERAL", 0.4)),
        patch(
            "app.api.v1.endpoints.chatbot.get_chatbot_response",
            side_effect=_mock_chatbot_response,
        ),
    ):
        response = await client.post(
            "/api/v1/chatbot/message",
            json={
                "session_id": "pii-log-hygiene-session",
                "message": raw_message,
            },
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ChatbotLog).where(ChatbotLog.intent == "GENERAL")
        )
        logs = result.scalars().all()

    assert logs
    for log in logs:
        assert not hasattr(log, "message")
        assert not hasattr(log, "raw_message")
        assert not hasattr(log, "prompt")
        assert raw_message not in str(log.__dict__)
