import random

from app.core.config import settings
from app.core.redis import redis_client
from app.services.sms_gateway import send_sms


def _otp_key(user_id: str) -> str:
    return f"otp:{user_id}"


def _otp_sid_key(user_id: str) -> str:
    return f"otp_sid:{user_id}"


async def generate_and_store_otp(user_id: str, phone_number: str) -> str:
    """
    Generates a 6-digit OTP, stores it in Redis with TTL, and sends it via Twilio SMS.
    Stores the returned Twilio message_sid alongside the OTP for delivery tracking.
    """
    otp = f"{random.randint(0, 999999):06d}"
    ttl = settings.OTP_EXPIRE_MINUTES * 60

    message_sid = await send_sms(
        to_number=phone_number,
        body=f"Your NeoBank Lebanon verification code is {otp}. It expires in {settings.OTP_EXPIRE_MINUTES} minutes.",
    )

    await redis_client.setex(_otp_key(user_id), ttl, otp)
    await redis_client.setex(_otp_sid_key(user_id), ttl, message_sid)

    return otp


async def verify_and_consume_otp(user_id: str, code: str) -> bool:
    """
    Validates the OTP for the given user.
    Deletes it immediately after a successful match (single use).
    Returns True if valid, False otherwise.
    """
    key = _otp_key(user_id)
    stored = await redis_client.get(key)

    if stored is None:
        return False  # Expired or never issued

    if stored != code:
        return False  # Wrong code

    await redis_client.delete(key)
    await redis_client.delete(_otp_sid_key(user_id))
    return True