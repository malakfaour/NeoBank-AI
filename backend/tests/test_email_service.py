from unittest.mock import Mock

import pytest

from app.services import email_service


def test_send_email_uses_brevo(monkeypatch):
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(email_service.settings, "BREVO_API_KEY", "test-api-key")
    monkeypatch.setattr(
        email_service.settings,
        "EMAIL_FROM",
        "NeoBank Lebanon <sender@example.com>",
    )
    response = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr(email_service.httpx, "post", post)

    email_service.send_email(
        to_email="lana@gmail.com",
        subject="Your verification code",
        body="Your code is 123456",
        html_body="<p>Your code is <strong>123456</strong></p>",
    )

    post.assert_called_once_with(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": "test-api-key",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "sender": {
                "name": "NeoBank Lebanon",
                "email": "sender@example.com",
            },
            "to": [{"email": "lana@gmail.com"}],
            "subject": "Your verification code",
            "textContent": "Your code is 123456",
            "htmlContent": "<p>Your code is <strong>123456</strong></p>",
        },
        timeout=10,
    )
    response.raise_for_status.assert_called_once_with()


def test_brevo_requires_api_key(monkeypatch):
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(email_service.settings, "BREVO_API_KEY", None)

    with pytest.raises(
        ValueError,
        match="BREVO_API_KEY is required when EMAIL_PROVIDER=brevo",
    ):
        email_service.send_email(
            to_email="lana@gmail.com",
            subject="Your verification code",
            body="Your code is 123456",
        )
