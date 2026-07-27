import asyncio
import io
from functools import partial
from time import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.storage import delete_file, upload_file
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.schemas.user_profile import (
    NotificationPreferences,
    UserMeResponse,
    UserUpdateEmailRequest,
    UserUpdatePhoneRequest,
    UserUpdateProfileRequest,
)
from app.services.otp import verify_and_consume_otp

router = APIRouter()

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/jpg"}


async def _get_user_or_404(db: AsyncSession, current_user: CurrentUser) -> User:
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


def _user_notification_preferences(user: User) -> NotificationPreferences:
    return NotificationPreferences(**(user.notification_preferences or {}))


async def _build_user_me_response(
    db: AsyncSession,
    user: User,
) -> UserMeResponse:
    unread_count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.read.is_(False),
        )
    )

    return UserMeResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        kyc_status=user.kyc_status,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        role=user.role,
        unread_count=unread_count or 0,
        notification_preferences=_user_notification_preferences(user),
    )


def _resize_avatar_to_jpeg(image_bytes: bytes) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    image = image.convert("RGB")
    image = image.resize((256, 256))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, current_user)
    return await _build_user_me_response(db, user)


@router.patch("/me", response_model=UserMeResponse)
async def patch_me(
    body: UserUpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, current_user)

    if body.full_name is not None:
        user.full_name = body.full_name

    if body.notification_preferences is not None:
        current_preferences = dict(user.notification_preferences or {})
        preference_updates = body.notification_preferences.model_dump(
            exclude_none=True,
        )
        user.notification_preferences = {
            "email": current_preferences.get("email", True),
            "push": current_preferences.get("push", True),
            "sms": current_preferences.get("sms", True),
            **preference_updates,
        }

    await db.commit()
    await db.refresh(user)
    return await _build_user_me_response(db, user)


@router.patch("/me/email", response_model=UserMeResponse)
async def patch_my_email(
    body: UserUpdateEmailRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, current_user)
    if not await verify_and_consume_otp(current_user.id, body.otp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP"
        )

    existing = await db.scalar(
        select(User).where(
            User.email == body.email,
            User.id != user.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists"
        )

    user.email = body.email
    await db.commit()
    await db.refresh(user)
    return await _build_user_me_response(db, user)


@router.patch("/me/phone", response_model=UserMeResponse)
async def patch_my_phone(
    body: UserUpdatePhoneRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, current_user)
    if not await verify_and_consume_otp(current_user.id, body.otp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP"
        )

    existing = await db.scalar(
        select(User).where(
            User.phone == body.phone,
            User.id != user.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Phone already exists"
        )

    user.phone = body.phone
    await db.commit()
    await db.refresh(user)
    return await _build_user_me_response(db, user)


@router.post("/me/avatar", response_model=UserMeResponse)
async def upload_avatar(
    avatar: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if avatar.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="avatar must be a JPEG or PNG image",
        )

    user = await _get_user_or_404(db, current_user)
    previous_avatar_key = user.avatar_url
    avatar_bytes = await avatar.read()
    await avatar.close()

    loop = asyncio.get_running_loop()
    resized = await loop.run_in_executor(
        None, partial(_resize_avatar_to_jpeg, avatar_bytes)
    )
    avatar_key = f"{user.id}/avatar_{int(time())}.jpg"
    await loop.run_in_executor(
        None,
        partial(
            upload_file,
            resized,
            avatar_key,
            extra_args={"ContentType": "image/jpeg"},
        ),
    )

    user.avatar_url = avatar_key
    await db.commit()
    if previous_avatar_key:
        await loop.run_in_executor(None, delete_file, previous_avatar_key)
    await db.refresh(user)
    return await _build_user_me_response(db, user)
