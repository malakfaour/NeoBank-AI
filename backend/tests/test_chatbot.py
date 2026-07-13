import json
from unittest.mock import AsyncMock, patch

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
async def auth_tokens(client):
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
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "chatbottest@neobank.com",
            "password": "TestPass123",
        },
    )
    return response.json()


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

    assert data["reply"] == "Hello! How can I help you?"
    assert data["session_id"] == "test-general-session"
    assert data["intent"] == "GENERAL"
    assert data["confidence"] == 0.4
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
    assert data["confidence"] == 0.92
    assert data["confirmation_required"] is True
    assert "confirm" in data["reply"].lower()


async def test_chatbot_groq_failure_falls_back_to_general(
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

    assert data["reply"] == "I am still available to help."
    assert data["session_id"] == "test-fallback-session"
    assert data["intent"] == "GENERAL"
    assert data["confidence"] == 0.0
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
            select(ChatbotLog).where(ChatbotLog.intent == "BALANCE_QUERY")
        )
        log = result.scalar_one_or_none()

    assert log is not None
    assert log.confidence == 0.87
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