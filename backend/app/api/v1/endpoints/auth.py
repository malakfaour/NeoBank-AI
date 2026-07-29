import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.redis import (
    blacklist_token,
    is_blacklisted,
    refresh_jti_exists,
    revoke_all_user_tokens,
    rotate_refresh_jti,
    store_refresh_jti,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_async_db
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User, UserRole
from app.schemas.auth import AuthUserResponse, CurrentUser, UserRegisterRequest, UserRegisterResponse
from app.services.account_service import create_wallets_for_user
from app.services.email_service import send_welcome_email
from app.api.v1.endpoints.sessions import create_session
from app.services.otp import (
    consume_reset_authorization,
    generate_and_store_otp,
    generate_purpose_otp,
    issue_reset_authorization,
    verify_and_consume_otp,
    verify_purpose_otp,
)
from app.services.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    access_token: str
    refresh_token: str


class SendOTPRequest(BaseModel):
    user_id: str


class VerifyOTPRequest(BaseModel):
    user_id: str
    code: str


class EmailRequest(BaseModel):
    email: EmailStr


class PasswordOTPRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., pattern=r"^\d{6}$")


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


async def _onboarding_state(user: User, db: AsyncSession) -> dict:
    result = await db.execute(
        select(KYCRecord)
        .where(KYCRecord.user_id == user.id)
        .order_by(KYCRecord.created_at.desc())
    )
    record = result.scalars().first()
    if record is None:
        state = "not_submitted"
    elif record.status == KYCRecordStatus.approved:
        state = "approved"
    elif record.status == KYCRecordStatus.rejected:
        state = "rejected"
    elif record.status == KYCRecordStatus.flagged:
        state = "flagged"
    else:
        state = "pending"
    return {
        "kyc_onboarding_state": state,
        "kyc_rejection_reason": record.rejection_reason if record else None,
    }


def _auth_user(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        kyc_status=user.kyc_status,
        role=user.role,
        email_verified=user.email_verified_at is not None,
    )


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

    # Provision wallets through the accounts service so every wallet gets
    # an account number and IBAN — required for transfer-by-IBAN to
    # resolve recipients. (Commits the session.)
    await create_wallets_for_user(user.id, db)
    await db.refresh(user)

    try:
        await generate_purpose_otp("registration", user.email, user.email)
    except Exception as exc:
        logger.exception("Registration verification email delivery failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Your account was created, but the verification email could not "
                "be delivered. Please use resend code."
            ),
        ) from exc

    return UserRegisterResponse(
        message="Registration successful. Check your email for the verification code.",
        email=user.email,
    )

@router.post("/login", summary="Login with email and password")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_async_db),
):
    await check_rate_limit(request, key_prefix="login", max_requests=5, window_seconds=60)

    email = str(body.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended. Contact support for assistance.",
        )

    access_token, _ = create_access_token(str(user.id), role=user.role.value)
    refresh_token, refresh_jti = create_refresh_token(str(user.id), role=user.role.value)
    await store_refresh_jti(str(user.id), refresh_jti)
    await create_session(user_id=user.id, request=request, db=db)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "passcode_is_set": bool(user.passcode_hash),
        "user": _auth_user(user),
        **(await _onboarding_state(user, db)),
    }


@router.get("/status", summary="Validate the current authenticated session")
async def auth_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(User).where(User.id == int(current_user.id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return {
        "authenticated": True,
        "user": _auth_user(user),
        "email_verified": user.email_verified_at is not None,
        "passcode_is_set": bool(user.passcode_hash),
        **(await _onboarding_state(user, db)),
    }


@router.post("/registration/verify-otp", summary="Verify registration email")
async def verify_registration(
    body: PasswordOTPRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
):
    email = str(body.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not await verify_purpose_otp("registration", email, body.code):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    if user.email_verified_at is None:
        from datetime import datetime, timezone
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()
    background_tasks.add_task(send_welcome_email, user.email, user.full_name)
    access_token, _ = create_access_token(str(user.id), role=user.role.value)
    refresh_token, refresh_jti = create_refresh_token(str(user.id), role=user.role.value)
    await store_refresh_jti(str(user.id), refresh_jti)
    return {
        "message": "Email verified successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "passcode_is_set": bool(user.passcode_hash),
        "user": _auth_user(user),
        **(await _onboarding_state(user, db)),
    }


@router.post("/registration/resend-otp", summary="Resend registration email OTP")
async def resend_registration_otp(
    request: Request,
    body: EmailRequest,
    db: AsyncSession = Depends(get_async_db),
):
    await check_rate_limit(
        request,
        key_prefix="registration_resend",
        max_requests=1,
        window_seconds=30,
    )
    email = str(body.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and user.email_verified_at is None:
        try:
            await generate_purpose_otp("registration", email, user.email)
        except Exception as exc:
            logger.exception("Registration verification email resend failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The verification email could not be delivered. Please try again.",
            ) from exc
    return {"message": "If verification is still required, a new code has been sent."}


@router.post("/password/forgot", summary="Request password reset OTP")
async def forgot_password(
    request: Request,
    body: EmailRequest,
    db: AsyncSession = Depends(get_async_db),
):
    await check_rate_limit(request, key_prefix="password_forgot", max_requests=3, window_seconds=300)
    email = str(body.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        await generate_purpose_otp("password", email, user.email)
    return {"message": "If an account exists for this email, a verification code has been sent."}


@router.post("/password/verify-otp", summary="Verify password reset OTP")
async def verify_password_reset_otp(request: Request, body: PasswordOTPRequest):
    await check_rate_limit(request, key_prefix="password_verify", max_requests=5, window_seconds=300)
    email = str(body.email).strip().lower()
    if not await verify_purpose_otp("password", email, body.code):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    token = await issue_reset_authorization("password", email)
    return {"reset_token": token, "expires_in": settings.OTP_EXPIRE_MINUTES * 60}


@router.post("/password/reset", summary="Reset account password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_async_db)):
    from app.schemas.auth import UserRegisterRequest
    try:
        UserRegisterRequest.validate_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    email = await consume_reset_authorization("password", body.reset_token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset authorization")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset authorization")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    await revoke_all_user_tokens(str(user.id))
    return {"message": "Password reset successfully"}


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
    user_id = payload.get("sub")
    role = payload.get("role")

    # Check if already blacklisted
    if await is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token already revoked",
        )

    # Check if JTI exists in registry — if not, replay attack detected
    if not await refresh_jti_exists(jti):
        # Replay attack — revoke everything for this user
        await revoke_all_user_tokens(user_id, jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already used. All sessions revoked.",
        )

    # Issue new tokens and atomically rotate
    new_access_token, _ = create_access_token(user_id, role=role)
    new_refresh_token, new_refresh_jti = create_refresh_token(user_id, role=role)
    await rotate_refresh_jti(user_id, old_jti=jti, new_jti=new_refresh_jti)

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout", summary="Logout and blacklist both tokens")
async def logout(body: LogoutRequest):
    try:
        access_payload = decode_token(body.access_token)
    except Exception:
        access_payload = None

    try:
        refresh_payload = decode_token(body.refresh_token)
    except Exception:
        refresh_payload = None

    if access_payload:
        await blacklist_token(access_payload["jti"])

    if refresh_payload:
        refresh_jti = refresh_payload["jti"]
        user_id = refresh_payload.get("sub")
        await blacklist_token(
            refresh_jti,
            expire_minutes=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60,
        )
        await revoke_all_user_tokens(user_id, refresh_jti)

    return {"message": "Logged out successfully"}


@router.post("/send-otp", summary="Generate and send OTP to user")
async def send_otp(
    request: Request,
    body: SendOTPRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    await check_rate_limit(request, key_prefix="send_otp", max_requests=3, window_seconds=300)

    result = await db.execute(select(User).where(User.id == int(body.user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await generate_and_store_otp(body.user_id, email=user.email)
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
