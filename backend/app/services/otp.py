import logging
import random

from app.core.config import settings
from app.core.redis import redis_client
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

# Retained as a no-op patch target for older callers and tests.
send_sms = None


def _otp_key(user_id: str) -> str:
    return f"otp:{user_id}"


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
