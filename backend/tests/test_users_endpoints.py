from datetime import datetime, timezone
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
    phone_suffix = f"{int(uuid4().hex[:8], 16) % 1_000_000:06d}"
    email = f"{label.lower()}-{suffix}@example.com"
    password = "TestPass123"

    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96170{phone_suffix}",
            "password": password,
        },
    )
    assert register_response.status_code == 200, register_response.text

    # Registration now requires email verification before login.
    user = await _get_user_by_email(email)
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        assert db_user is not None
        db_user.email_verified_at = datetime.now(timezone.utc)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200, login_response.text

    result = login_response.json()
    result["email"] = email
    return result

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
async def test_send_profile_email_otp_uses_authenticated_user(client, monkeypatch):
    tokens = await _register_user(client, "profile-email-otp")
    user = await _get_user_by_email(tokens["email"])
    calls = []

    async def fake_generate_purpose_otp(purpose, subject, email):
        calls.append((purpose, subject, email))
        return "123456"

    monkeypatch.setattr(
        "app.api.v1.endpoints.users.generate_purpose_otp",
        fake_generate_purpose_otp,
    )

    response = await client.post(
        "/api/v1/users/me/email/otp",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200, response.text
    assert calls == [("profile_email_change", str(user.id), tokens["email"])]


@pytest.mark.anyio
async def test_send_profile_phone_otp_uses_authenticated_user(client, monkeypatch):
    tokens = await _register_user(client, "profile-phone-otp")
    user = await _get_user_by_email(tokens["email"])
    calls = []

    async def fake_generate_purpose_otp(purpose, subject, email):
        calls.append((purpose, subject, email))
        return "123456"

    monkeypatch.setattr(
        "app.api.v1.endpoints.users.generate_purpose_otp",
        fake_generate_purpose_otp,
    )

    response = await client.post(
        "/api/v1/users/me/phone/otp",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200, response.text
    assert calls == [("profile_phone_change", str(user.id), tokens["email"])]


@pytest.mark.anyio
async def test_patch_my_email_uses_otp_verification(client, monkeypatch):
    tokens = await _register_user(client, "emailchange")

    async def fake_verify_purpose_otp(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.api.v1.endpoints.users.verify_purpose_otp",
        fake_verify_purpose_otp,
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

    async def fake_verify_purpose_otp(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.api.v1.endpoints.users.verify_purpose_otp",
        fake_verify_purpose_otp,
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
    monkeypatch.setattr(
        "app.api.v1.endpoints.users.get_presigned_url",
        lambda key: f"https://storage.test/{key}",
    )

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
async def test_upload_avatar_deletes_previous_avatar_after_replacement(
    client, monkeypatch
):
    tokens = await _register_user(client, "avatar-replacement")
    uploaded_keys = []
    deleted_keys = []
    timestamps = iter([1000, 2000])

    def fake_upload_file(
        file_source, destination_key, bucket_name=None, extra_args=None
    ):
        uploaded_keys.append(destination_key)
        return destination_key

    def fake_delete_file(s3_key, bucket_name=None):
        deleted_keys.append(s3_key)

    monkeypatch.setattr("app.api.v1.endpoints.users.upload_file", fake_upload_file)
    monkeypatch.setattr("app.api.v1.endpoints.users.delete_file", fake_delete_file)
    monkeypatch.setattr(
        "app.api.v1.endpoints.users.get_presigned_url",
        lambda key: f"https://storage.test/{key}",
    )
    monkeypatch.setattr("app.api.v1.endpoints.users.time", lambda: next(timestamps))

    image = Image.new("RGB", (32, 32), color="red")
    payload = BytesIO()
    image.save(payload, format="PNG")
    request_files = {"avatar": ("avatar.png", payload.getvalue(), "image/png")}
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    first_response = await client.post(
        "/api/v1/users/me/avatar", headers=headers, files=request_files
    )
    second_response = await client.post(
        "/api/v1/users/me/avatar", headers=headers, files=request_files
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    assert len(uploaded_keys) == 2
    assert uploaded_keys[0].endswith("/avatar_1000.jpg")
    assert uploaded_keys[1].endswith("/avatar_2000.jpg")
    assert deleted_keys == [uploaded_keys[0]]
    assert deleted_keys[0] != uploaded_keys[1]


@pytest.mark.anyio
async def test_users_me_requires_authentication(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code in {401, 403}
