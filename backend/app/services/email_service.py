import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "console":
        logger.info("Console email provider enabled.")
        logger.info("To: %s", to_email)
        logger.info("From: %s", settings.EMAIL_FROM)
        logger.info("Subject: %s", subject)
        logger.info("Body: %s", body)
        return

    if provider == "smtp":
        _send_email_smtp(
            to_email=to_email,
            subject=subject,
            body=body,
            html_body=html_body,
        )
        return

    if provider == "sendgrid":
        _send_email_sendgrid(
            to_email=to_email,
            subject=subject,
            body=body,
            html_body=html_body,
        )
        return

    raise ValueError(f"Unsupported EMAIL_PROVIDER: {settings.EMAIL_PROVIDER}")


def _send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    if not settings.SMTP_HOST:
        raise ValueError("SMTP_HOST is required when EMAIL_PROVIDER=smtp")

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject

    message.set_content(body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()

        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        server.send_message(message)


def _send_email_sendgrid(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    if not settings.SENDGRID_API_KEY:
        raise ValueError("SENDGRID_API_KEY is required when EMAIL_PROVIDER=sendgrid")

    from_name, from_email = parseaddr(settings.EMAIL_FROM)

    if not from_email:
        from_email = "no-reply@neobank.local"

    payload = {
        "personalizations": [
            {
                "to": [{"email": to_email}],
            }
        ],
        "from": {
            "email": from_email,
            "name": from_name or "NeoBank Lebanon",
        },
        "subject": subject,
        "content": [
            {
                "type": "text/plain",
                "value": body,
            }
        ],
    }

    if html_body:
        payload["content"].append(
            {
                "type": "text/html",
                "value": html_body,
            }
        )

    response = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


def send_welcome_email(to_email: str, full_name: str | None = None) -> None:
    display_name = full_name or "there"

    subject = "Welcome to NeoBank Lebanon"

    body = (
        f"Hello {display_name},\n\n"
        "Welcome to NeoBank Lebanon. Your account has been created successfully.\n\n"
        "You can now log in and start using your digital banking features.\n\n"
        "Best regards,\n"
        "NeoBank Lebanon Team"
    )

    html_body = f"""
    <html>
        <body>
            <p>Hello {display_name},</p>
            <p>Welcome to <strong>NeoBank Lebanon</strong>.</p>
            <p>Your account has been created successfully.</p>
            <p>You can now log in and start using your digital banking features.</p>
            <p>Best regards,<br>NeoBank Lebanon Team</p>
        </body>
    </html>
    """

    try:
        send_email(
            to_email=to_email,
            subject=subject,
            body=body,
            html_body=html_body,
        )
    except Exception:
        logger.exception("Failed to send welcome email to %s", to_email)