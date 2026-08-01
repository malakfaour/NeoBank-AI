import logging
import random
import hashlib
import hmac
from uuid import uuid4

from app.core.config import settings
from app.core.redis import redis_client
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

# Retained as a no-op patch target for older callers and tests.
send_sms = None


def _otp_key(user_id: str) -> str:
    return f"otp:{user_id}"


def _purpose_key(purpose: str, subject: str) -> str:
    digest = hashlib.sha256(subject.strip().lower().encode()).hexdigest()
    return f"otp:{purpose}:{digest}"


def _otp_digest(code: str) -> str:
    return hmac.new(
        settings.JWT_SECRET.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


async def generate_and_store_otp(user_id: str, email: str) -> str:
    otp = f"{random.randint(0, 999999):06d}"
    ttl = settings.OTP_EXPIRE_MINUTES * 60
    send_email(
        to_email=email,
        subject="Your NeoBank Lebanon verification code",
        body=f"Your NeoBank Lebanon verification code is {otp}. It expires in {settings.OTP_EXPIRE_MINUTES} minutes.",
    )
    await redis_client.setex(_otp_key(user_id), ttl, otp)
    return otp


async def verify_and_consume_otp(user_id: str, code: str) -> bool:
    key = _otp_key(user_id)
    stored = await redis_client.get(key)
    if stored is None:
        return False
    if stored != code:
        return False
    await redis_client.delete(key)
    return True


async def generate_purpose_otp(purpose: str, subject: str, email: str) -> str:
    code = f"{random.randint(0, 999999):06d}"
    ttl = settings.OTP_EXPIRE_MINUTES * 60
    key = _purpose_key(purpose, subject)
    send_email(
        to_email=email,
        subject="Your NeoBank Lebanon verification code",
        body=(
            "Use this one-time code to continue: "
            f"{code}. It expires in {settings.OTP_EXPIRE_MINUTES} minutes."
        ),
    )
    await redis_client.hset(
        key, mapping={"digest": _otp_digest(code), "attempts": "0"}
    )
    await redis_client.expire(key, ttl)
    return code


async def verify_purpose_otp(purpose: str, subject: str, code: str) -> bool:
    key = _purpose_key(purpose, subject)
    record = await redis_client.hgetall(key)
    if not record or int(record.get("attempts", "0")) >= 5:
        return False
    if not hmac.compare_digest(record.get("digest", ""), _otp_digest(code)):
        await redis_client.hincrby(key, "attempts", 1)
        return False
    await redis_client.delete(key)
    return True


async def issue_reset_authorization(purpose: str, subject: str) -> str:
    token = str(uuid4())
    await redis_client.setex(
        f"reset:{purpose}:{token}",
        settings.OTP_EXPIRE_MINUTES * 60,
        subject.strip().lower(),
    )
    return token


async def consume_reset_authorization(purpose: str, token: str) -> str | None:
    key = f"reset:{purpose}:{token}"
    subject = await redis_client.get(key)
    if subject:
        await redis_client.delete(key)
    return subject
