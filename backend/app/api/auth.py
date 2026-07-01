import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.redis import blacklist_token, is_blacklisted
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_async_db
from app.models.user import KYCStatus, User, UserRole
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.user import CurrentUser, UserRegisterRequest, UserRegisterResponse
from app.services.email_service import send_welcome_email
from app.services.otp import generate_and_store_otp, verify_and_consume_otp
from app.services.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    access_token: str


class SendOTPRequest(BaseModel):
    user_id: str


class VerifyOTPRequest(BaseModel):
    user_id: str
    code: str


@router.post("/register", response_model=UserRegisterResponse, summary="Register a new customer")
async def register(
    body: UserRegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(User).where(or_(User.email == body.email, User.phone == body.phone))
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        detail = (
            "Email already exists"
            if existing_user.email == body.email
            else "Phone already exists"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    user = User(
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        password_hash=hash_password(body.password),
        kyc_status=KYCStatus.pending,
        role=UserRole.customer,
    )
    db.add(user)
    await db.flush()

    db.add_all(
        [
            Wallet(user_id=user.id, currency=WalletCurrency.USD, balance=0.0),
            Wallet(user_id=user.id, currency=WalletCurrency.LBP, balance=0.0),
            Wallet(user_id=user.id, currency=WalletCurrency.USDT, balance=0.0),
        ]
    )
    await db.commit()
    await db.refresh(user)

    background_tasks.add_task(
        send_welcome_email,
        to_email=user.email,
        full_name=user.full_name,
    )

    access_token, _ = create_access_token(str(user.id), role=user.role.value)
    refresh_token, _ = create_refresh_token(str(user.id), role=user.role.value)

    return UserRegisterResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/login", summary="Login with email and password")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_async_db),
):
    await check_rate_limit(request, key_prefix="login", max_requests=5, window_seconds=60)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token, _ = create_access_token(str(user.id), role=user.role.value)
    refresh_token, _ = create_refresh_token(str(user.id), role=user.role.value)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", summary="Rotate refresh token")
async def refresh(body: RefreshRequest):
    try:
        payload = decode_token(body.refresh_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    jti = payload.get("jti")

    if await is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token already revoked",
        )

    await blacklist_token(jti, expire_minutes=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60)

    access_token, _ = create_access_token(payload["sub"], role=payload.get("role"))
    refresh_token, _ = create_refresh_token(payload["sub"], role=payload.get("role"))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout", summary="Logout and blacklist token")
async def logout(body: LogoutRequest):
    try:
        payload = decode_token(body.access_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    await blacklist_token(payload["jti"])

    return {"message": "Logged out successfully"}


@router.post("/send-otp", summary="Generate and send OTP to user")
async def send_otp(
    request: Request,
    body: SendOTPRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    await check_rate_limit(request, key_prefix="send_otp", max_requests=3, window_seconds=300)

    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await generate_and_store_otp(body.user_id, phone_number=user.phone)
    return {"message": f"OTP sent to user {body.user_id}"}


@router.post("/verify-otp", summary="Verify OTP code")
async def verify_otp(
    request: Request,
    body: VerifyOTPRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    await check_rate_limit(
        request,
        key_prefix="verify_otp",
        max_requests=5,
        window_seconds=300,
    )

    valid = await verify_and_consume_otp(body.user_id, body.code)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )

    return {"message": "OTP verified successfully"}