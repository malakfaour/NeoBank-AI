import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis import get_redis_client
from app.models.notification import Notification, NotificationType
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.email_service import send_email
from app.services.fcm_push import send_fcm_pushes
from app.services.sms_gateway import send_sms

logger = logging.getLogger(__name__)

DEFAULT_NOTIFICATION_PREFERENCES = {"email": True, "push": True, "sms": True}
SECURITY_RELEVANT_TYPES = {"TX_FLAGGED", "KYC_REJECTED"}
HIGH_VALUE_TRANSFER_TYPES = {"TX_SENT", "TX_RECEIVED"}

EMAIL_WORTHY_TYPES = {
    "TX_SENT",
    "TX_RECEIVED",
    "TX_FLAGGED",
    "KYC_APPROVED",
    "KYC_FLAGGED",
    "KYC_REJECTED",
}


def _notification_preferences(user: User | None) -> dict[str, bool]:
    preferences = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    if user is not None and user.notification_preferences:
        preferences.update(user.notification_preferences)
    return preferences


def _channel_enabled(
    preferences: dict[str, bool],
    channel: str,
    notification_type: NotificationType | str,
) -> bool:
    if _notification_type_value(notification_type) in SECURITY_RELEVANT_TYPES:
        return True
    return preferences.get(channel, True)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _is_high_value_transfer(
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
) -> bool:
    if _notification_type_value(notification_type) not in HIGH_VALUE_TRANSFER_TYPES:
        return False

    amount = _to_decimal(metadata.get("amount"))
    if amount is None:
        return False

    return amount > settings.HIGH_VALUE_SMS_THRESHOLD


def _should_send_sms(
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
) -> bool:
    type_value = _notification_type_value(notification_type)
    return type_value == "TX_FLAGGED" or _is_high_value_transfer(
        notification_type,
        metadata,
    )


def _build_sms_body(
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
    message: str,
) -> str:
    type_value = _notification_type_value(notification_type)
    amount = metadata.get("amount", "")
    currency = metadata.get("currency", "")
    transaction_id = metadata.get("transaction_id", "")

    if type_value == "TX_FLAGGED":
        return "NeoBank alert: a transaction on your account was flagged for review."

    if _is_high_value_transfer(notification_type, metadata):
        return (
            f"NeoBank alert: high-value transfer of {amount} {currency} was processed. "
            f"Transaction ID: {transaction_id}"
        ).strip()

    return f"NeoBank alert: {message}"


def _notification_type_value(notification_type: NotificationType | str) -> str:
    if isinstance(notification_type, NotificationType):
        return notification_type.value
    return str(notification_type)


def _coerce_notification_type(
    notification_type: NotificationType | str,
) -> NotificationType | str:
    if isinstance(notification_type, NotificationType):
        return notification_type

    try:
        return NotificationType(notification_type)
    except ValueError:
        try:
            return NotificationType[notification_type]
        except KeyError:
            return notification_type


def _is_push_worthy_type(notification_type: NotificationType | str) -> bool:
    type_value = _notification_type_value(notification_type)
    return type_value.startswith("TX_") or type_value.startswith("KYC_")


async def _send_best_effort_push(
    db: AsyncSession,
    user_id: int,
    notification_id: int,
    notification_type: NotificationType | str,
    title: str,
    message: str,
    preferences: dict[str, bool] | None = None,
) -> None:
    if not _is_push_worthy_type(notification_type):
        return

    preferences = preferences or dict(DEFAULT_NOTIFICATION_PREFERENCES)

    if not _channel_enabled(preferences, "push", notification_type):
        return

    try:
        result = await db.execute(
            select(PushSubscription.token).where(
                PushSubscription.user_id == user_id,
            )
        )
        tokens = list(result.scalars().all())

        await send_fcm_pushes(
            tokens=tokens,
            title=title,
            body=message,
            data={
                "notification_id": notification_id,
                "type": _notification_type_value(notification_type),
                "user_id": user_id,
            },
        )
    except Exception:
        logger.exception(
            "Failed to send best-effort FCM push notification to user_id=%s",
            user_id,
        )


def _build_template(
    notification_type: NotificationType | str,
    metadata: dict[str, Any],
) -> tuple[str, str, str, str]:
    type_value = _notification_type_value(notification_type)

    amount = metadata.get("amount", "")
    if amount:
         amount = format(Decimal(str(amount)).normalize(), "f")
    currency = metadata.get("currency", "")
    transaction_id = metadata.get("transaction_id", "")
    reason = metadata.get("reason", "")
    full_name = metadata.get("full_name", "there")
    sender_name = metadata.get("sender_name", "the sender")

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
        message = f"You received {amount} {currency} from {sender_name}."
        subject = "Transaction received"
        body = (
            f"Hello {full_name},\n\n"
            f"You received {amount} {currency} from {sender_name} in your NeoBank account.\n"
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
        body = f"Hello {full_name},\n\n{message}\n\nNeoBank Lebanon Team"

    html_body = body.replace("\n", "<br>")

    return message, subject, body, html_body


async def _get_notification_user(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
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

    user = await _get_notification_user(db, user_id)
    preferences = _notification_preferences(user)

    if (
        type_value in EMAIL_WORTHY_TYPES
        and _channel_enabled(preferences, "email", notification_type)
        and user is not None
        and user.email
    ):
        try:
            send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                html_body=html_body,
            )
        except Exception:
            logger.exception(
                "Failed to send notification email to user_id=%s",
                user_id,
            )

    if (
        _should_send_sms(notification_type, metadata)
        and _channel_enabled(preferences, "sms", notification_type)
        and user is not None
        and user.phone
    ):
        try:
            await send_sms(
                to_number=user.phone,
                body=_build_sms_body(notification_type, metadata, message),
            )
        except Exception:
            logger.exception(
                "Failed to send notification SMS to user_id=%s",
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

    await _send_best_effort_push(
        db=db,
        user_id=user_id,
        notification_id=notification_id,
        notification_type=notification_type,
        title=subject,
        message=message,
        preferences=preferences,
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
