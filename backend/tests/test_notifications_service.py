import pytest

from app.services.notifications import EMAIL_WORTHY_TYPES, notify


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def add(self, notification):
        notification.id = 123
        self.notification = notification

    async def flush(self):
        return None

    async def execute(self, statement):
        return FakeResult("user@example.com")

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