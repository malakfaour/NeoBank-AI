from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import KYCStatus, UserRole


class UserMeResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    kyc_status: KYCStatus
    avatar_url: str | None
    created_at: datetime
    role: UserRole
    unread_count: int

    model_config = ConfigDict(use_enum_values=True)


class UserUpdateProfileRequest(BaseModel):
    full_name: str


class UserUpdateEmailRequest(BaseModel):
    email: str
    otp_code: str


class UserUpdatePhoneRequest(BaseModel):
    phone: str
    otp_code: str
