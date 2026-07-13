from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select

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
        return await session.scalar(select(User).where(User.email == email))


@pytest.mark.anyio
async def test_get_me_returns_profile_with_unread_count(client):
    tokens = await _register_user(client, "profile")
    user = await _get_user_by_email(tokens["email"])

    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                Notification(
                    user_id=user.id,
                    type=NotificationType.ALERT,
                    message="one",
                    read=False,
                ),
                Notification(
                    user_id=user.id,
                    type=NotificationType.ALERT,
                    message="two",
                    read=False,
                ),
                Notification(
                    user_id=user.id,
                    type=NotificationType.ALERT,
                    message="three",
                    read=True,
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == tokens["email"]
    assert body["full_name"] == "profile User"
    assert body["unread_count"] == 2
    assert body["avatar_url"] is None
    assert body["notification_preferences"] == {
        "email": True,
        "push": True,
        "sms": True,
    }


@pytest.mark.anyio
async def test_patch_me_updates_full_name(client):
    tokens = await _register_user(client, "rename")

    response = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"full_name": "Updated Name"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "Updated Name"


@pytest.mark.anyio
async def test_patch_me_updates_notification_preferences(client):
    tokens = await _register_user(client, "prefs")

    response = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "notification_preferences": {
                "email": False,
                "sms": False,
            }
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["notification_preferences"] == {
        "email": False,
        "push": True,
        "sms": False,
    }

    get_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["notification_preferences"] == {
        "email": False,
        "push": True,
        "sms": False,
    }


@pytest.mark.anyio
async def test_patch_my_email_uses_otp_verification(client, monkeypatch):
    tokens = await _register_user(client, "emailchange")

    async def fake_verify_and_consume_otp(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.api.v1.endpoints.users.verify_and_consume_otp", fake_verify_and_consume_otp
    )

    response = await client.patch(
        "/api/v1/users/me/email",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"email": "new-email@example.com", "otp_code": "123456"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "new-email@example.com"


@pytest.mark.anyio
async def test_patch_my_phone_uses_otp_verification(client, monkeypatch):
    tokens = await _register_user(client, "phonechange")

    async def fake_verify_and_consume_otp(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.api.v1.endpoints.users.verify_and_consume_otp", fake_verify_and_consume_otp
    )

    response = await client.patch(
        "/api/v1/users/me/phone",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"phone": "+96170111222", "otp_code": "123456"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["phone"] == "+96170111222"


@pytest.mark.anyio
async def test_upload_avatar_resizes_and_stores_avatar(client, monkeypatch):
    tokens = await _register_user(client, "avatar")
    uploads = []

    def fake_upload_file(
        file_source, destination_key, bucket_name=None, extra_args=None
    ):
        uploads.append(
            {
                "destination_key": destination_key,
                "size": len(file_source),
                "extra_args": extra_args,
            }
        )
        return destination_key

    image = Image.new("RGB", (32, 32), color="red")
    payload = BytesIO()
    image.save(payload, format="PNG")

    monkeypatch.setattr("app.api.v1.endpoints.users.upload_file", fake_upload_file)

    response = await client.post(
        "/api/v1/users/me/avatar",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        files={"avatar": ("avatar.png", payload.getvalue(), "image/png")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["avatar_url"].endswith(".jpg")
    assert len(uploads) == 1
    assert uploads[0]["extra_args"]["ContentType"] == "image/jpeg"


@pytest.mark.anyio
async def test_users_me_requires_authentication(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code in {401, 403}
