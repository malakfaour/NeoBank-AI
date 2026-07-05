import asyncio
import io
from functools import partial
from time import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.storage import upload_file
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.user import CurrentUser
from app.schemas.users import (
    UserMeResponse,
    UserUpdateEmailRequest,
    UserUpdatePhoneRequest,
    UserUpdateProfileRequest,
)
from app.services.otp import verify_and_consume_otp

router = APIRouter()

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/jpg"}
SSE_S3_EXTRA_ARGS = {"ServerSideEncryption": "AES256", "ContentType": "image/jpeg"}


async def _get_user_or_404(db: AsyncSession, current_user: CurrentUser) -> User:
    user = await db.scalar(select(User).where(User.id == int(current_user.id)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


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
    )


@router.patch("/me", response_model=UserMeResponse)
async def patch_me(
    body: UserUpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, current_user)
    user.full_name = body.full_name
    await db.commit()
    await db.refresh(user)
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
    )


@router.patch("/me/email", response_model=UserMeResponse)
async def patch_my_email(
    body: UserUpdateEmailRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, current_user)
    if not await verify_and_consume_otp(current_user.id, body.otp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    existing = await db.scalar(
        select(User).where(
            User.email == body.email,
            User.id != user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user.email = body.email
    await db.commit()
    await db.refresh(user)
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
    )


@router.patch("/me/phone", response_model=UserMeResponse)
async def patch_my_phone(
    body: UserUpdatePhoneRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, current_user)
    if not await verify_and_consume_otp(current_user.id, body.otp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    existing = await db.scalar(
        select(User).where(
            User.phone == body.phone,
            User.id != user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone already exists")

    user.phone = body.phone
    await db.commit()
    await db.refresh(user)
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
    )


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
    avatar_bytes = await avatar.read()
    await avatar.close()

    loop = asyncio.get_running_loop()
    resized = await loop.run_in_executor(None, partial(_resize_avatar_to_jpeg, avatar_bytes))
    avatar_key = f"{user.id}/avatar_{int(time())}.jpg"
    await loop.run_in_executor(
        None,
        partial(
            upload_file,
            resized,
            avatar_key,
            extra_args=SSE_S3_EXTRA_ARGS,
        ),
    )

    user.avatar_url = avatar_key
    await db.commit()
    await db.refresh(user)
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
    )
