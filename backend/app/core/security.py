from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(subject: str, token_type: str, expire_delta: timedelta, role: str | None = None) -> tuple[str, str]:
    jti = str(uuid4())
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {
        "sub": subject,
        "jti": jti,
        "exp": expire,
        "type": token_type,
    }
    if role:
        payload["role"] = role
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM), jti


def create_access_token(subject: str, role: str | None = None) -> tuple[str, str]:
    return _create_token(
        subject=subject,
        token_type="access",
        expire_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        role=role,
    )


def create_refresh_token(subject: str, role: str | None = None) -> tuple[str, str]:
    return _create_token(
        subject=subject,
        token_type="refresh",
        expire_delta=timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        role=role,
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
