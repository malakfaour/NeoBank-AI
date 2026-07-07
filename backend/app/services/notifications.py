import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.redis import get_redis_client
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

EMAIL_WORTHY_TYPES = {
    "TX_SENT",
    "TX_RECEIVED",
    "TX_FLAGGED",
    "KYC_APPROVED",
    "KYC_FLAGGED",
    "KYC_REJECTED",
}


def _notification_type_value(notification_type: NotificationType | str) -> str:
    if isinstance(notification_type, NotificationType):
        return notification_type.value
    return str(notification_type)


def _coerce_notification_type(notification_type: NotificationType | str) -> NotificationType | str:
    if isinstance(notification_type, NotificationType):
        return notification_type

    try:
        return NotificationType(notification_type)
    except ValueError:
        try:
            return NotificationType[notification_type]
        except KeyError:
            return notification_type


def _build_template(
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
) -> tuple[str, str, str, str]:
    type_value = _notification_type_value(notification_type)

    amount = metadata.get("amount", "")
    currency = metadata.get("currency", "")
    transaction_id = metadata.get("transaction_id", "")
    reason = metadata.get("reason", "")
    full_name = metadata.get("full_name", "there")

    if type_value == "TX_SENT":
        message = f"Your transfer of {amount} {currency} was sent successfully."
        subject = "Transaction sent"
        body = (
            f"Hello {full_name},\n\n"
            f"Your transfer of {amount} {currency} was sent successfully.\n"
            f"Transaction ID: {transaction_id}\n\n"
            "NeoBank Lebanon Team"
        )

    elif type_value == "TX_RECEIVED":
        message = f"You received {amount} {currency}."
        subject = "Transaction received"
        body = (
            f"Hello {full_name},\n\n"
            f"You received {amount} {currency} in your NeoBank account.\n"
            f"Transaction ID: {transaction_id}\n\n"
            "NeoBank Lebanon Team"
        )

    elif type_value == "TX_FLAGGED":
        message = "A transaction was flagged for review."
        subject = "Transaction flagged for review"
        body = (
            f"Hello {full_name},\n\n"
            "A transaction on your account was flagged for review.\n"
            f"Reason: {reason or 'Pending review'}\n\n"
            "NeoBank Lebanon Team"
        )

    elif type_value == "KYC_APPROVED":
        message = "Your KYC verification was approved."
        subject = "KYC approved"
        body = (
            f"Hello {full_name},\n\n"
            "Your KYC verification was approved successfully.\n\n"
            "NeoBank Lebanon Team"
        )

    elif type_value == "KYC_FLAGGED":
        message = "Your KYC verification requires additional review."
        subject = "KYC requires review"
        body = (
            f"Hello {full_name},\n\n"
            "Your KYC verification requires additional review.\n"
            f"Reason: {reason or 'Additional verification needed'}\n\n"
            "NeoBank Lebanon Team"
        )

    elif type_value == "KYC_REJECTED":
        message = "Your KYC verification was rejected."
        subject = "KYC rejected"
        body = (
            f"Hello {full_name},\n\n"
            "Your KYC verification was rejected.\n"
            f"Reason: {reason or 'Please contact support for more details'}\n\n"
            "NeoBank Lebanon Team"
        )

    else:
        message = metadata.get("message", "You have a new notification.")
        subject = "New notification"
        body = (
            f"Hello {full_name},\n\n"
            f"{message}\n\n"
            "NeoBank Lebanon Team"
        )

    html_body = body.replace("\n", "<br>")

    return message, subject, body, html_body


async def _get_user_email(db: AsyncSession, user_id: int) -> str | None:
    result = await db.execute(select(User.email).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _notify_with_session(
    db: AsyncSession,
    user_id: int,
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
) -> int:
    stored_type = _coerce_notification_type(notification_type)
    type_value = _notification_type_value(notification_type)

    message, subject, body, html_body = _build_template(notification_type, metadata)

    notification = Notification(
        user_id=user_id,
        type=stored_type,
        message=message,
        read=False,
    )

    db.add(notification)
    await db.flush()

    notification_id = int(notification.id)

    if type_value in EMAIL_WORTHY_TYPES:
        user_email = await _get_user_email(db, user_id)

        if user_email:
            try:
                send_email(
                    to_email=user_email,
                    subject=subject,
                    body=body,
                    html_body=html_body,
                )
            except Exception:
                logger.exception(
                    "Failed to send notification email to user_id=%s",
                    user_id,
                )

    await db.commit()

    payload = {
        "id": notification_id,
        "user_id": user_id,
        "type": type_value,
        "message": message,
        "read": False,
        "created_at": (
            notification.created_at.isoformat()
            if notification.created_at is not None
            else None
        ),
    }

    redis_client = get_redis_client()
    await redis_client.publish(
        f"notifications:{user_id}",
        json.dumps(payload),
    )

    return notification_id


def notify_sync(
    db: Session,
    user_id: int,
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
) -> int:
    stored_type = _coerce_notification_type(notification_type)
    message, _, _, _ = _build_template(notification_type, metadata)

    notification = Notification(
        user_id=user_id,
        type=stored_type,
        message=message,
        read=False,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return int(notification.id)


async def notify(
    user_id: int,
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
    db: AsyncSession | None = None,
) -> int:
    if db is not None:
        return await _notify_with_session(
            db=db,
            user_id=user_id,
            notification_type=notification_type,
            metadata=metadata,
        )

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await _notify_with_session(
            db=session,
            user_id=user_id,
            notification_type=notification_type,
            metadata=metadata,
        )
