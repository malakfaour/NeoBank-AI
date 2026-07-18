from pydantic import BaseModel, EmailStr

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


class AuthUserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    kyc_status: KYCStatus


class UserRegisterResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AuthUserResponse