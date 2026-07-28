from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import settings
from app.core.redis import consume_action_token, is_blacklisted
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.models.kyc_record import KYCRecord
from app.schemas.auth import CurrentUser, UserRole
from app.services.kyc_access import assert_approved_kyc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    """
    FastAPI dependency — validates Bearer token and returns current user.
    Raises 401 on missing, invalid, expired, or blacklisted tokens.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    user_id = payload.get("sub")

    if not jti or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if await is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = payload.get("role", UserRole.customer)

    return CurrentUser(id=user_id, token_jti=jti, role=role)


def require_role(*roles: UserRole):
    """
    FastAPI dependency factory — restricts route access to specified roles.
    Usage: Depends(require_role(UserRole.admin))
    """
    async def role_checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in roles]}",
            )
        return current_user
    return role_checker

async def require_action_token(
    x_action_token: str | None = Header(default=None, alias="X-Action-Token"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    FastAPI dependency -- gates money-movement endpoints behind a
    short-lived, single-use action_token issued by POST /auth/passcode/verify.

    Controlled by settings.REQUIRE_ACTION_TOKEN (default True in prod,
    False in tests via conftest.py) so this can be soft-launched.
    Missing, invalid, replayed, or another user's token all return 403.
    """
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    submitted = bool(
        await db.scalar(
            select(KYCRecord.is_submitted)
            .where(KYCRecord.user_id == user.id)
            .order_by(KYCRecord.id.desc())
        )
    )
    assert_approved_kyc(user, submitted=submitted)

    if not settings.REQUIRE_ACTION_TOKEN:
        return current_user

    if not x_action_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Action-Token header",
        )

    is_valid = await consume_action_token(current_user.id, x_action_token)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired action token",
        )

    return current_user


async def require_approved_kyc(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    submitted = bool(
        await db.scalar(
            select(KYCRecord.is_submitted)
            .where(KYCRecord.user_id == user.id)
            .order_by(KYCRecord.id.desc())
        )
    )
    assert_approved_kyc(user, submitted=submitted)
    return current_user
