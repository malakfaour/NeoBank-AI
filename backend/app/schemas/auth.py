import re

from pydantic import BaseModel, EmailStr, field_validator

from app.models.user import KYCStatus, UserRole


class TokenPayload(BaseModel):
    sub: str
    jti: str
    type: str


class CurrentUser(BaseModel):
    id: str
    token_jti: str
    role: UserRole = UserRole.customer


class UserRegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = re.sub(r"[\s()-]", "", value)
        if normalized.startswith("00961"):
            normalized = f"+961{normalized[5:]}"
        elif not normalized.startswith("+961"):
            normalized = f"+961{normalized.lstrip('0')}"
        if not re.fullmatch(r"\+961(?:3\d{6}|(?:70|71|76|78|79|81)\d{6})", normalized):
            raise ValueError("Enter a valid Lebanese mobile number")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class AuthUserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    kyc_status: KYCStatus
    role: UserRole
    email_verified: bool = False


class UserRegisterResponse(BaseModel):
    message: str
    email: EmailStr
