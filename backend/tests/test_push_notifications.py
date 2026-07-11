from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.notification import NotificationType
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.notifications import notify


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


async def _get_user_by_email(email: str) -> User:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        return user


async def _add_push_subscription(user_id: int, token: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(PushSubscription(user_id=user_id, token=token))
        await session.commit()


@pytest.mark.anyio
async def test_subscribe_push_notifications_persists_token(client):
    tokens = await _register_user(client, "pushsub")
    user = await _get_user_by_email(tokens["email"])
    push_token = f"fcm-token-{uuid4().hex}"

    response = await client.post(
        "/api/v1/notifications/push/subscribe",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"token": f"  {push_token}  "},
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["token"] == push_token

    async with AsyncSessionLocal() as session:
        subscription = await session.scalar(
            select(PushSubscription).where(
                PushSubscription.token == push_token,
            )
        )

    assert subscription is not None
    assert subscription.user_id == user.id


@pytest.mark.anyio
async def test_subscribe_push_notifications_reassigns_duplicate_token(client):
    first_tokens = await _register_user(client, "pushfirst")
    second_tokens = await _register_user(client, "pushsecond")
    second_user = await _get_user_by_email(second_tokens["email"])
    push_token = f"fcm-token-{uuid4().hex}"

    first_response = await client.post(
        "/api/v1/notifications/push/subscribe",
        headers={"Authorization": f"Bearer {first_tokens['access_token']}"},
        json={"token": push_token},
    )

    assert first_response.status_code == 200, first_response.text

    second_response = await client.post(
        "/api/v1/notifications/push/subscribe",
        headers={"Authorization": f"Bearer {second_tokens['access_token']}"},
        json={"token": push_token},
    )

    assert second_response.status_code == 200, second_response.text

    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count(PushSubscription.id)).where(
                PushSubscription.token == push_token,
            )
        )
        subscription = await session.scalar(
            select(PushSubscription).where(
                PushSubscription.token == push_token,
            )
        )

    assert count == 1
    assert subscription is not None
    assert subscription.user_id == second_user.id


@pytest.mark.anyio
async def test_notify_sends_fcm_for_kyc_notification(client, monkeypatch):
    tokens = await _register_user(client, "pushkyc")
    user = await _get_user_by_email(tokens["email"])
    push_token = f"fcm-token-{uuid4().hex}"
    await _add_push_subscription(user.id, push_token)

    mock_send_fcm = AsyncMock()
    monkeypatch.setattr(
        "app.services.notifications.send_fcm_pushes",
        mock_send_fcm,
    )
    monkeypatch.setattr(
        "app.services.notifications.send_email",
        lambda **kwargs: None,
    )

    notification_id = await notify(
        user_id=user.id,
        notification_type=NotificationType.KYC_APPROVED,
        metadata={"full_name": user.full_name},
    )

    assert notification_id > 0
    mock_send_fcm.assert_awaited_once()

    call_kwargs = mock_send_fcm.await_args.kwargs

    assert call_kwargs["tokens"] == [push_token]
    assert call_kwargs["title"] == "KYC approved"
    assert call_kwargs["body"] == "Your KYC verification was approved."
    assert call_kwargs["data"]["type"] == "KYC_APPROVED"
    assert call_kwargs["data"]["notification_id"] == notification_id


@pytest.mark.anyio
async def test_notify_does_not_send_fcm_for_general_notification(
    client,
    monkeypatch,
):
    tokens = await _register_user(client, "pushgeneral")
    user = await _get_user_by_email(tokens["email"])
    await _add_push_subscription(user.id, f"fcm-token-{uuid4().hex}")

    mock_send_fcm = AsyncMock()
    monkeypatch.setattr(
        "app.services.notifications.send_fcm_pushes",
        mock_send_fcm,
    )

    notification_id = await notify(
        user_id=user.id,
        notification_type=NotificationType.ALERT,
        metadata={"message": "General alert"},
    )

    assert notification_id > 0
    mock_send_fcm.assert_not_awaited()


@pytest.mark.anyio
async def test_notify_ignores_fcm_failure(client, monkeypatch):
    tokens = await _register_user(client, "pushfailure")
    user = await _get_user_by_email(tokens["email"])
    await _add_push_subscription(user.id, f"fcm-token-{uuid4().hex}")

    mock_send_fcm = AsyncMock(side_effect=RuntimeError("FCM unavailable"))
    monkeypatch.setattr(
        "app.services.notifications.send_fcm_pushes",
        mock_send_fcm,
    )
    monkeypatch.setattr(
        "app.services.notifications.send_email",
        lambda **kwargs: None,
    )

    notification_id = await notify(
        user_id=user.id,
        notification_type=NotificationType.KYC_FLAGGED,
        metadata={
            "full_name": user.full_name,
            "reason": "Needs manual review",
        },
    )

    assert notification_id > 0
    mock_send_fcm.assert_awaited_once()


@pytest.mark.anyio
async def test_send_fcm_pushes_uses_mocked_httpx(monkeypatch):
    from app.services import fcm_push

    monkeypatch.setattr(settings, "FCM_PROJECT_ID", "test-project")
    monkeypatch.setattr(settings, "FCM_CLIENT_EMAIL", "fcm@example.com")
    monkeypatch.setattr(settings, "FCM_PRIVATE_KEY", "fake-private-key")
    monkeypatch.setattr(settings, "FCM_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(
        fcm_push,
        "_build_service_account_assertion",
        lambda: "signed-service-account-jwt",
    )

    calls = []

    class FakeResponse:
        def __init__(self, status_code=200, json_data=None):
            self.status_code = status_code
            self._json_data = json_data or {}

        def json(self):
            return self._json_data

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data=None, headers=None, json=None):
            calls.append(
                {
                    "url": url,
                    "data": data,
                    "headers": headers,
                    "json": json,
                }
            )

            if url == fcm_push.GOOGLE_TOKEN_URL:
                return FakeResponse(json_data={"access_token": "access-token-123"})

            return FakeResponse()

    monkeypatch.setattr(fcm_push.httpx, "AsyncClient", FakeAsyncClient)

    await fcm_push.send_fcm_pushes(
        tokens=["device-token-123"],
        title="NeoBank Lebanon",
        body="Your transfer was sent successfully.",
        data={"notification_id": 123, "type": "TX_SENT"},
    )

    assert calls[0]["url"] == fcm_push.GOOGLE_TOKEN_URL
    assert calls[0]["data"]["grant_type"] == fcm_push.JWT_GRANT_TYPE
    assert calls[0]["data"]["assertion"] == "signed-service-account-jwt"

    assert calls[1]["url"] == (
        "https://fcm.googleapis.com/v1/projects/test-project/messages:send"
    )
    assert calls[1]["headers"]["Authorization"] == "Bearer access-token-123"
    assert calls[1]["json"]["message"]["token"] == "device-token-123"
    assert calls[1]["json"]["message"]["data"]["type"] == "TX_SENT"


@pytest.mark.anyio
async def test_subscribe_push_notifications_requires_auth(client):
    response = await client.post(
        "/api/v1/notifications/push/subscribe",
        json={"token": "device-token-123"},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_subscribe_push_notifications_rejects_blank_token(client):
    tokens = await _register_user(client, "pushblank")

    response = await client.post(
        "/api/v1/notifications/push/subscribe",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"token": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Push token cannot be blank"


@pytest.mark.anyio
async def test_push_leg_db_failure_does_not_break_flow(monkeypatch):
    from app.services.notifications import _send_best_effort_push

    class FailingDb:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("push subscription lookup failed")

    mock_send_fcm = AsyncMock()
    monkeypatch.setattr(
        "app.services.notifications.send_fcm_pushes",
        mock_send_fcm,
    )

    await _send_best_effort_push(
        db=FailingDb(),
        user_id=123,
        notification_id=456,
        notification_type=NotificationType.KYC_APPROVED,
        title="KYC approved",
        message="Your KYC verification was approved.",
    )

    mock_send_fcm.assert_not_awaited()
