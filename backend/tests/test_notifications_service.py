from unittest.mock import AsyncMock

import pytest

from app.services.notifications import EMAIL_WORTHY_TYPES, notify


class FakeUser:
    def __init__(
        self,
        email="user@example.com",
        phone="+96170123456",
        notification_preferences=None,
    ):
        self.email = email
        self.phone = phone
        self.notification_preferences = notification_preferences or {
            "email": True,
            "push": True,
            "sms": True,
        }


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeResult:
    def __init__(self, user=None, push_tokens=None):
        self.user = user or FakeUser()
        self.push_tokens = push_tokens or []

    def scalar_one_or_none(self):
        return self.user

    def scalars(self):
        return FakeScalars(self.push_tokens)


class FakeSession:
    def __init__(self, user=None, push_tokens=None):
        self.user = user or FakeUser()
        self.push_tokens = push_tokens or []

    def add(self, notification):
        notification.id = 123
        self.notification = notification

    async def flush(self):
        return None

    async def execute(self, statement):
        return FakeResult(user=self.user, push_tokens=self.push_tokens)

    async def commit(self):
        return None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "notification_type",
    sorted(EMAIL_WORTHY_TYPES),
)
async def test_notify_sends_email_for_email_worthy_types(
    monkeypatch,
    notification_type,
):
    sent_email = {}

    def fake_send_email(to_email, subject, body, html_body=None):
        sent_email["to_email"] = to_email
        sent_email["subject"] = subject
        sent_email["body"] = body
        sent_email["html_body"] = html_body

    monkeypatch.setattr(
        "app.services.notifications.send_email",
        fake_send_email,
    )
    monkeypatch.setattr(
        "app.services.notifications.send_fcm_pushes",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        AsyncMock(),
    )

    notification_id = await notify(
        user_id=1,
        notification_type=notification_type,
        metadata={
            "full_name": "Noura",
            "amount": 100,
            "currency": "USD",
            "transaction_id": "TX-123",
            "reason": "Test reason",
        },
        db=FakeSession(),
    )

    assert notification_id == 123
    assert sent_email["to_email"] == "user@example.com"
    assert sent_email["subject"]
    assert sent_email["body"]
    assert "Noura" in sent_email["body"]


@pytest.mark.anyio
async def test_notify_does_not_send_email_for_non_email_type(monkeypatch):
    email_called = False

    def fake_send_email(to_email, subject, body, html_body=None):
        nonlocal email_called
        email_called = True

    monkeypatch.setattr(
        "app.services.notifications.send_email",
        fake_send_email,
    )

    notification_id = await notify(
        user_id=1,
        notification_type="GENERAL",
        metadata={"message": "General notification"},
        db=FakeSession(),
    )

    assert notification_id == 123
    assert email_called is False


@pytest.mark.anyio
async def test_notify_publishes_to_user_redis_channel(monkeypatch):
    published = {}

    class FakeRedis:
        async def publish(self, channel, message):
            published["channel"] = channel
            published["message"] = message
            return 1

    monkeypatch.setattr(
        "app.services.notifications.get_redis_client",
        lambda: FakeRedis(),
    )

    notification_id = await notify(
        user_id=42,
        notification_type="GENERAL",
        metadata={"message": "Real-time notification"},
        db=FakeSession(),
    )

    assert notification_id == 123
    assert published["channel"] == "notifications:42"
    assert "Real-time notification" in published["message"]


@pytest.mark.anyio
async def test_notify_sends_sms_for_tx_flagged(monkeypatch):
    mock_sms = AsyncMock()

    monkeypatch.setattr("app.services.notifications.send_sms", mock_sms)
    monkeypatch.setattr("app.services.notifications.send_email", lambda **kwargs: None)
    monkeypatch.setattr("app.services.notifications.send_fcm_pushes", AsyncMock())

    notification_id = await notify(
        user_id=1,
        notification_type="TX_FLAGGED",
        metadata={"reason": "Suspicious transfer"},
        db=FakeSession(),
    )

    assert notification_id == 123
    mock_sms.assert_awaited_once()
    assert mock_sms.await_args.kwargs["to_number"] == "+96170123456"
    assert "flagged" in mock_sms.await_args.kwargs["body"]


@pytest.mark.anyio
async def test_notify_sends_sms_for_high_value_transfer(monkeypatch):
    mock_sms = AsyncMock()

    monkeypatch.setattr("app.services.notifications.send_sms", mock_sms)
    monkeypatch.setattr("app.services.notifications.send_email", lambda **kwargs: None)
    monkeypatch.setattr("app.services.notifications.send_fcm_pushes", AsyncMock())

    notification_id = await notify(
        user_id=1,
        notification_type="TX_SENT",
        metadata={
            "amount": "501",
            "currency": "USD",
            "transaction_id": "TX-501",
        },
        db=FakeSession(),
    )

    assert notification_id == 123
    mock_sms.assert_awaited_once()
    assert "501 USD" in mock_sms.await_args.kwargs["body"]


@pytest.mark.anyio
async def test_notify_does_not_send_sms_for_low_value_transfer(monkeypatch):
    mock_sms = AsyncMock()

    monkeypatch.setattr("app.services.notifications.send_sms", mock_sms)
    monkeypatch.setattr("app.services.notifications.send_email", lambda **kwargs: None)
    monkeypatch.setattr("app.services.notifications.send_fcm_pushes", AsyncMock())

    notification_id = await notify(
        user_id=1,
        notification_type="TX_SENT",
        metadata={
            "amount": "500",
            "currency": "USD",
            "transaction_id": "TX-500",
        },
        db=FakeSession(),
    )

    assert notification_id == 123
    mock_sms.assert_not_awaited()


@pytest.mark.anyio
async def test_notify_respects_email_preference_off(monkeypatch):
    email_called = False

    def fake_send_email(to_email, subject, body, html_body=None):
        nonlocal email_called
        email_called = True

    monkeypatch.setattr("app.services.notifications.send_email", fake_send_email)
    monkeypatch.setattr("app.services.notifications.send_fcm_pushes", AsyncMock())
    monkeypatch.setattr("app.services.notifications.send_sms", AsyncMock())

    user = FakeUser(
        notification_preferences={"email": False, "push": True, "sms": True}
    )

    notification_id = await notify(
        user_id=1,
        notification_type="KYC_APPROVED",
        metadata={"full_name": "Noura"},
        db=FakeSession(user=user),
    )

    assert notification_id == 123
    assert email_called is False


@pytest.mark.anyio
async def test_notify_respects_push_preference_off(monkeypatch):
    mock_push = AsyncMock()

    monkeypatch.setattr("app.services.notifications.send_fcm_pushes", mock_push)
    monkeypatch.setattr("app.services.notifications.send_email", lambda **kwargs: None)
    monkeypatch.setattr("app.services.notifications.send_sms", AsyncMock())

    user = FakeUser(
        notification_preferences={"email": True, "push": False, "sms": True}
    )

    notification_id = await notify(
        user_id=1,
        notification_type="KYC_APPROVED",
        metadata={"full_name": "Noura"},
        db=FakeSession(user=user, push_tokens=["fcm-token"]),
    )

    assert notification_id == 123
    mock_push.assert_not_awaited()


@pytest.mark.anyio
async def test_notify_respects_sms_preference_off_for_high_value_transfer(monkeypatch):
    mock_sms = AsyncMock()

    monkeypatch.setattr("app.services.notifications.send_sms", mock_sms)
    monkeypatch.setattr("app.services.notifications.send_email", lambda **kwargs: None)
    monkeypatch.setattr("app.services.notifications.send_fcm_pushes", AsyncMock())

    user = FakeUser(
        notification_preferences={"email": True, "push": True, "sms": False}
    )

    notification_id = await notify(
        user_id=1,
        notification_type="TX_SENT",
        metadata={
            "amount": "700",
            "currency": "USD",
            "transaction_id": "TX-700",
        },
        db=FakeSession(user=user),
    )

    assert notification_id == 123
    mock_sms.assert_not_awaited()


@pytest.mark.anyio
async def test_tx_flagged_ignores_sms_preference_off(monkeypatch):
    mock_sms = AsyncMock()

    monkeypatch.setattr("app.services.notifications.send_sms", mock_sms)
    monkeypatch.setattr("app.services.notifications.send_email", lambda **kwargs: None)
    monkeypatch.setattr("app.services.notifications.send_fcm_pushes", AsyncMock())

    user = FakeUser(
        notification_preferences={"email": False, "push": False, "sms": False}
    )

    notification_id = await notify(
        user_id=1,
        notification_type="TX_FLAGGED",
        metadata={"reason": "Security review"},
        db=FakeSession(user=user),
    )

    assert notification_id == 123
    mock_sms.assert_awaited_once()
