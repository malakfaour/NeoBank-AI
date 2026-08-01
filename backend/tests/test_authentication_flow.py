from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import User
from app.models.kyc_record import KYCRecord


async def create_verified_user(db_session, *, email: str, phone: str, passcode: str | None = None):
    user = User(
        full_name="Auth Test",
        email=email,
        phone=phone,
        password_hash=hash_password("StrongPass1!"),
        email_verified_at=datetime.now(timezone.utc),
        passcode_hash=hash_password(passcode) if passcode else None,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_registration_normalizes_identity_and_rejects_duplicate(client):
    payload = {
        "full_name": "Test Person",
        "email": " PERSON@Example.COM ",
        "phone": "70 123 456",
        "password": "StrongPass1!",
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    duplicate = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 200
    assert first.json()["email"] == "person@example.com"
    assert "access_token" not in first.json()
    assert duplicate.status_code == 400


@pytest.mark.asyncio
async def test_registration_otp_verifies_email_and_establishes_session(
    client, db_session, monkeypatch
):
    sent = []
    monkeypatch.setattr("app.services.otp.random.randint", lambda *_: 246810)
    monkeypatch.setattr(
        "app.services.otp.send_email",
        lambda **kwargs: sent.append(kwargs),
    )
    payload = {
        "full_name": "OTP Person",
        "email": "otp-person@example.com",
        "phone": "+96178123456",
        "password": "StrongPass1!",
    }
    registration = await client.post("/api/v1/auth/register", json=payload)
    blocked_login = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    invalid = await client.post(
        "/api/v1/auth/registration/verify-otp",
        json={"email": payload["email"], "code": "000000"},
    )
    verified = await client.post(
        "/api/v1/auth/registration/verify-otp",
        json={"email": payload["email"], "code": "246810"},
    )
    user = await db_session.scalar(select(User).where(User.email == payload["email"]))
    assert registration.status_code == 200
    assert len(sent) == 1
    assert blocked_login.status_code == 403
    assert invalid.status_code == 400
    assert verified.status_code == 200
    assert verified.json()["access_token"]
    assert user.email_verified_at is not None


@pytest.mark.asyncio
async def test_registration_resend_has_cooldown(client, monkeypatch):
    monkeypatch.setattr("app.services.otp.send_email", lambda **_: None)
    payload = {
        "full_name": "Resend Person",
        "email": "resend-person@example.com",
        "phone": "+96179123456",
        "password": "StrongPass1!",
    }
    await client.post("/api/v1/auth/register", json=payload)
    first = await client.post(
        "/api/v1/auth/registration/resend-otp", json={"email": payload["email"]}
    )
    second = await client.post(
        "/api/v1/auth/registration/resend-otp", json={"email": payload["email"]}
    )
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_login_is_email_password_only_and_reports_passcode(client, db_session):
    await create_verified_user(
        db_session, email="login-flow@example.com", phone="+96171123456", passcode="294806"
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "LOGIN-FLOW@example.com", "password": "StrongPass1!"},
    )
    phone_login = await client.post(
        "/api/v1/auth/login", json={"phone": "+96171123456", "passcode": "294806"}
    )
    assert response.status_code == 200
    assert response.json()["passcode_is_set"] is True
    assert phone_login.status_code == 422


@pytest.mark.asyncio
async def test_weak_passcode_rejected(client, db_session):
    user = await create_verified_user(
        db_session, email="passcode@example.com", phone="+96176123456"
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "StrongPass1!"},
    )
    response = await client.post(
        "/api/v1/auth/passcode/set",
        json={"passcode": "123456"},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_forgot_password_is_neutral_for_unknown_email(client):
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "missing@example.com"}
    )
    assert response.status_code == 200
    assert response.json()["message"].startswith("If an account exists")


@pytest.mark.asyncio
async def test_registered_email_receives_password_reset_otp(
    client, db_session, monkeypatch
):
    user = await create_verified_user(
        db_session,
        email="forgot-delivery@example.com",
        phone="+96170111222",
    )
    sent = []
    monkeypatch.setattr(
        "app.services.otp.send_email",
        lambda **kwargs: sent.append(kwargs),
    )
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": user.email}
    )
    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0]["to_email"] == user.email
    assert "verification code" in sent[0]["subject"].lower()


@pytest.mark.asyncio
async def test_password_reset_otp_changes_password_and_revokes_session(
    client, db_session, monkeypatch
):
    user = await create_verified_user(
        db_session,
        email="forgot-flow@example.com",
        phone="+96170111333",
    )
    monkeypatch.setattr("app.services.otp.random.randint", lambda *_: 135790)
    monkeypatch.setattr("app.services.otp.send_email", lambda **_: None)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "StrongPass1!"},
    )
    await client.post("/api/v1/auth/password/forgot", json={"email": user.email})
    verification = await client.post(
        "/api/v1/auth/password/verify-otp",
        json={"email": user.email, "code": "135790"},
    )
    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={
            "reset_token": verification.json()["reset_token"],
            "new_password": "NewStrongPass2!",
        },
    )
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "StrongPass1!"},
    )
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "NewStrongPass2!"},
    )
    old_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert reset.status_code == 200
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert old_refresh.status_code == 401


@pytest.mark.asyncio
async def test_auth_status_distinguishes_unsubmitted_and_pending_kyc(client, db_session):
    user = await create_verified_user(
        db_session, email="kyc-state@example.com", phone="+96181123456", passcode="294806"
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "StrongPass1!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    unsubmitted = await client.get("/api/v1/auth/status", headers=headers)
    db_session.add(KYCRecord(user_id=user.id))
    await db_session.commit()
    pending = await client.get("/api/v1/auth/status", headers=headers)
    assert unsubmitted.json()["kyc_onboarding_state"] == "not_submitted"
    assert pending.json()["kyc_onboarding_state"] == "pending"
