import asyncio
import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

TWILIO_API_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"


async def send_sms(to_number: str, body: str) -> str:
    """
    Sends an SMS via the Twilio Messages API.
    Retries once after 5s on a 5xx response, then raises 503.
    Returns the Twilio message_sid on success.
    """
    url = TWILIO_API_URL.format(account_sid=settings.TWILIO_ACCOUNT_SID)
    auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    data = {
        "To": to_number,
        "From": settings.TWILIO_FROM_NUMBER,
        "Body": body,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in (1, 2):
            try:
                response = await client.post(url, auth=auth, data=data)
            except httpx.RequestError as exc:
                logger.error(f"Twilio request failed (attempt {attempt}): {exc}")
                if attempt == 2:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="SMS gateway unavailable",
                    ) from exc
                await asyncio.sleep(5)
                continue

            if response.status_code >= 500:
                logger.warning(f"Twilio returned {response.status_code} (attempt {attempt})")
                if attempt == 2:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="SMS gateway unavailable",
                    )
                await asyncio.sleep(5)
                continue

            if response.status_code >= 400:
                logger.error(f"Twilio rejected request: {response.status_code} {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="SMS gateway rejected the request",
                )

            return response.json()["sid"]

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="SMS gateway unavailable",
    )