from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
JWT_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"


def _fcm_configured() -> bool:
    return bool(
        settings.FCM_PROJECT_ID
        and settings.FCM_CLIENT_EMAIL
        and settings.FCM_PRIVATE_KEY
    )


def _clean_private_key() -> str:
    return settings.FCM_PRIVATE_KEY.replace("\\n", "\n")


def _build_service_account_assertion() -> str:
    now = int(time.time())
    payload = {
        "iss": settings.FCM_CLIENT_EMAIL,
        "scope": FCM_SCOPE,
        "aud": GOOGLE_TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }

    return jwt.encode(
        payload,
        _clean_private_key(),
        algorithm="RS256",
    )


async def _get_access_token(client: httpx.AsyncClient) -> str | None:
    try:
        assertion = _build_service_account_assertion()
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": JWT_GRANT_TYPE,
                "assertion": assertion,
            },
        )
    except Exception:
        logger.exception("Failed to request FCM access token")
        return None

    if response.status_code >= 400:
        logger.warning(
            "FCM access token request failed with status_code=%s",
            response.status_code,
        )
        return None

    try:
        token = response.json().get("access_token")
    except Exception:
        logger.exception("Failed to parse FCM access token response")
        return None

    if not token:
        logger.warning("FCM access token response did not include access_token")
        return None

    return str(token)


def _stringify_data(data: dict[str, Any]) -> dict[str, str]:
    return {key: "" if value is None else str(value) for key, value in data.items()}


async def send_fcm_pushes(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, Any],
) -> None:
    if not tokens:
        return

    if not _fcm_configured():
        logger.info("FCM push skipped because FCM settings are not configured")
        return

    endpoint = (
        "https://fcm.googleapis.com/v1/projects/"
        f"{settings.FCM_PROJECT_ID}/messages:send"
    )

    try:
        async with httpx.AsyncClient(
            timeout=settings.FCM_TIMEOUT_SECONDS,
        ) as client:
            access_token = await _get_access_token(client)

            if not access_token:
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            for token in tokens:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json={
                        "message": {
                            "token": token,
                            "notification": {
                                "title": title,
                                "body": body,
                            },
                            "data": _stringify_data(data),
                        }
                    },
                )

                if response.status_code >= 400:
                    logger.warning(
                        "FCM push failed with status_code=%s",
                        response.status_code,
                    )

    except Exception:
        logger.exception("FCM push failed")
