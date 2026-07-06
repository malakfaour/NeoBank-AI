import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.chatbot_intent import GROQ_API_URL

_REAL_POST = httpx.AsyncClient.post


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
    await client.post("/api/v1/auth/register", json={
        "full_name": "Chatbot Test User",
        "email": "chatbottest@neobank.com",
        "phone": "+96170000099",
        "password": "TestPass123",
    })
    response = await client.post("/api/v1/auth/login", json={
        "email": "chatbottest@neobank.com",
        "password": "TestPass123",
    })
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
            headers={
                "Authorization": (
                    f"Bearer {auth_tokens['access_token']}"
                )
            },
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
                "message": "send 100 to Sara",
            },
            headers={
                "Authorization": (
                    f"Bearer {auth_tokens['access_token']}"
                )
            },
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
            headers={
                "Authorization": (
                    f"Bearer {auth_tokens['access_token']}"
                )
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["reply"] == "I am still available to help."
    assert data["session_id"] == "test-fallback-session"
    assert data["intent"] == "GENERAL"
    assert data["confidence"] == 0.0
    assert data["confirmation_required"] is False