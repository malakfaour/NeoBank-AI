import base64
import binascii
import secrets
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.sessions import create_session
from app.core.redis import (
    consume_biometric_challenge,
    store_biometric_challenge,
    store_refresh_jti,
)
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_async_db
from app.models.device_credential import DeviceCredential
from app.models.user import User
from app.schemas.user import CurrentUser

router = APIRouter()
INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
)


class BiometricEnrollRequest(BaseModel):
    device_id: str
    public_key: str


class BiometricLoginRequest(BaseModel):
    user_id: int | None = None
    device_id: str | None = None
    signed_nonce: str

    @model_validator(mode="after")
    def require_one_selector(self):
        if (self.user_id is None) == (self.device_id is None):
            raise ValueError("Provide exactly one of user_id or device_id")
        return self


def _valid_signature(public_key_pem: str, nonce: str, signed_nonce: str) -> bool:
    """Verify an Ed25519 signature; clients send PEM public keys and base64 signatures."""
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(base64.b64decode(signed_nonce, validate=True), nonce.encode("utf-8"))
        return True
    except (ValueError, TypeError, binascii.Error, InvalidSignature):
        return False


@router.get("/challenge")
async def biometric_challenge(
    current_user: CurrentUser = Depends(get_current_user),
):
    nonce = secrets.token_urlsafe(32)
    await store_biometric_challenge(current_user.id, nonce)
    return {"nonce": nonce}


@router.post("/enroll")
async def biometric_enroll(
    body: BiometricEnrollRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    # Validate and restrict enrollment to Ed25519 public keys.
    try:
        key = serialization.load_pem_public_key(body.public_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid Ed25519 public key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise HTTPException(status_code=422, detail="Invalid Ed25519 public key")

    device_owner = (
        await db.execute(
            select(DeviceCredential).where(DeviceCredential.device_id == body.device_id)
        )
    ).scalar_one_or_none()
    if device_owner is not None and device_owner.user_id != int(current_user.id):
        raise HTTPException(status_code=409, detail="Device is already enrolled")

    result = await db.execute(
        select(DeviceCredential).where(
            DeviceCredential.user_id == int(current_user.id),
            DeviceCredential.device_id == body.device_id,
        )
    )
    credential = result.scalar_one_or_none()
    if credential is None:
        credential = DeviceCredential(
            user_id=int(current_user.id),
            device_id=body.device_id,
            public_key=body.public_key,
        )
        db.add(credential)
    else:
        credential.public_key = body.public_key
    await db.commit()
    await db.refresh(credential)
    return {
        "id": credential.id,
        "user_id": credential.user_id,
        "device_id": credential.device_id,
        "public_key": credential.public_key,
        "created_at": credential.created_at,
        "last_used_at": credential.last_used_at,
    }


@router.post("/login")
async def biometric_login(
    request: Request,
    body: BiometricLoginRequest,
    db: AsyncSession = Depends(get_async_db),
):
    query = select(DeviceCredential)
    if body.device_id is not None:
        query = query.where(DeviceCredential.device_id == body.device_id)
    else:
        query = query.where(DeviceCredential.user_id == body.user_id)
    credentials = (await db.execute(query)).scalars().all()
    if not credentials:
        raise INVALID_CREDENTIALS

    user_id = credentials[0].user_id
    nonce = await consume_biometric_challenge(str(user_id))
    if nonce is None:
        raise INVALID_CREDENTIALS

    credential = next(
        (c for c in credentials if _valid_signature(c.public_key, nonce, body.signed_nonce)),
        None,
    )
    if credential is None:
        raise INVALID_CREDENTIALS

    user = await db.get(User, user_id)
    if user is None:
        raise INVALID_CREDENTIALS
    credential.last_used_at = datetime.now(timezone.utc)
    await db.flush()

    access_token, _ = create_access_token(str(user.id), role=user.role.value)
    refresh_token, refresh_jti = create_refresh_token(str(user.id), role=user.role.value)
    await store_refresh_jti(str(user.id), refresh_jti)
    await create_session(user_id=user.id, request=request, db=db)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }
