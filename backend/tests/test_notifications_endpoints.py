from uuid import uuid4

import pytest
from sqlalchemy import select
from starlette.requests import Request

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.notification import Notification, NotificationType
from app.models.user import User


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
        return await session.scalar(
            select(User).where(User.email == email)
        )


@pytest.mark.anyio
async def test_list_notifications_unread_only(client):
    tokens = await _register_user(client, "notifications")
    user = await _get_user_by_email(tokens["email"])

    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                Notification(
                    user_id=user.id,
                    type=NotificationType.ALERT,
                    message="Unread one",
                    read=False,
                ),
                Notification(
                    user_id=user.id,
                    type=NotificationType.ALERT,
                    message="Unread two",
                    read=False,
                ),
                Notification(
                    user_id=user.id,
                    type=NotificationType.ALERT,
                    message="Already read",
                    read=True,
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/notifications",
        params={"unread_only": "true"},
        headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(item["read"] is False for item in body["items"])


@pytest.mark.anyio
async def test_stream_notifications_rejects_invalid_token(client):
    response = await client.get(
        "/api/v1/notifications/stream",
        params={"token": "invalid-token"},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_stream_query_token_helper_accepts_valid_access_token():
    access_token, _ = create_access_token(subject="42")

    from app.api.v1.endpoints.notifications import (
        get_current_user_from_query_token,
    )

    current_user = await get_current_user_from_query_token(access_token)

    assert str(current_user.id) == "42"


@pytest.mark.anyio
async def test_stream_notifications_subscribes_to_user_channel(monkeypatch):
    from app.api.v1.endpoints.notifications import stream_notifications

    access_token, _ = create_access_token(subject="42")

    subscribed = []
    unsubscribed = []
    closed = []

    class FakePubSub:
        async def subscribe(self, channel):
            subscribed.append(channel)

        async def get_message(
            self,
            ignore_subscribe_messages=True,
            timeout=1.0,
        ):
            return {
                "type": "message",
                "channel": "notifications:42",
                "data": '{"message":"hello"}',
            }

        async def unsubscribe(self, channel):
            unsubscribed.append(channel)

        async def aclose(self):
            closed.append(True)

    class FakeRedis:
        def pubsub(self):
            return FakePubSub()

    monkeypatch.setattr(
        "app.api.v1.endpoints.notifications.get_redis_client",
        lambda: FakeRedis(),
    )

    disconnected = False

    async def receive():
        nonlocal disconnected

        if disconnected:
            return {"type": "http.disconnect"}

        disconnected = True

        return {
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/notifications/stream",
        "headers": [],
    }

    request = Request(scope, receive)

    response = await stream_notifications(
        request=request,
        token=access_token,
    )

    iterator = response.body_iterator

    first_event = await anext(iterator)

    assert first_event == 'data: {"message":"hello"}\n\n'
    assert subscribed == ["notifications:42"]

    await iterator.aclose()

    assert unsubscribed == ["notifications:42"]
    assert closed == [True]