import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.redis import (
    increment_passcode_attempts,
    is_passcode_locked,
    reset_passcode_attempts,
    store_action_token,
)
from app.services.otp import (
    consume_reset_authorization,
    issue_reset_authorization,
)
from app.core.security import hash_password, verify_password
from app.db.session import get_async_db
from app.models.user import User
from app.schemas.auth import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter()


class SetPasscodeRequest(BaseModel):
    passcode: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class ChangePasscodeRequest(BaseModel):
    current_passcode: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_passcode: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class ReauthenticateRequest(BaseModel):
    password: str = Field(..., min_length=1)


class ResetPasscodeRequest(BaseModel):
    reset_token: str
    passcode: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyPasscodeRequest(BaseModel):
    passcode: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


async def _get_user(user_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _reject_weak_passcode(passcode: str) -> None:
    if (
        len(set(passcode)) == 1
        or passcode in {"123456", "654321"}
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a less predictable passcode",
        )


@router.post("/set", summary="Set passcode for the first time")
async def set_passcode(
    body: SetPasscodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """First-time passcode setup for an authenticated, verified account."""
    user = await _get_user(current_user.id, db)

    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )

    if user.passcode_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passcode already set. Use /passcode/change to update it.",
        )

    _reject_weak_passcode(body.passcode)
    user.passcode_hash = hash_password(body.passcode)
    await db.commit()

    return {"message": "Passcode set successfully"}


@router.post("/change", summary="Change existing passcode")
async def change_passcode(
    body: ChangePasscodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Change passcode — requires current passcode verification and new OTP."""
    user = await _get_user(current_user.id, db)

    if not user.passcode_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No passcode set. Use /passcode/set first.",
        )

    if not verify_password(body.current_passcode, user.passcode_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current passcode is incorrect",
        )

    _reject_weak_passcode(body.new_passcode)
    user.passcode_hash = hash_password(body.new_passcode)
    await db.commit()

    return {"message": "Passcode changed successfully"}


@router.post("/verify", summary="Verify passcode and get action token")
async def verify_passcode(
    body: VerifyPasscodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Validates passcode and returns a short-lived action_token (5 min TTL).
    Locks for 10 min after 3 wrong attempts.
    """
    user_id = current_user.id

    if await is_passcode_locked(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Passcode locked for 10 minutes due to too many failed attempts.",
        )

    user = await _get_user(user_id, db)

    if not user.passcode_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No passcode set. Use /passcode/set first.",
        )

    if not verify_password(body.passcode, user.passcode_hash):
        attempts = await increment_passcode_attempts(user_id)
        remaining = 3 - attempts
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Passcode locked for 10 minutes due to too many failed attempts.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Incorrect passcode. {remaining} attempt(s) remaining.",
        )

    await reset_passcode_attempts(user_id)

    action_token = str(uuid4())
    await store_action_token(user_id, action_token)

    return {
        "action_token": action_token,
        "expires_in": 300,
    }


@router.post("/reset/reauthenticate", summary="Authorize passcode reset")
async def authorize_passcode_reset(
    body: ReauthenticateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user = await _get_user(current_user.id, db)
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = await issue_reset_authorization("passcode", current_user.id)
    return {"reset_token": token, "expires_in": 300}


@router.post("/reset", summary="Replace passcode after reauthentication")
async def reset_passcode(
    body: ResetPasscodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    authorized_user = await consume_reset_authorization("passcode", body.reset_token)
    if authorized_user != current_user.id:
        raise HTTPException(status_code=403, detail="Invalid or expired reset authorization")
    _reject_weak_passcode(body.passcode)
    user = await _get_user(current_user.id, db)
    user.passcode_hash = hash_password(body.passcode)
    await db.commit()
    await reset_passcode_attempts(current_user.id)
    return {"message": "Passcode reset successfully"}
