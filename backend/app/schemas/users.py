from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import KYCStatus, UserRole


class NotificationPreferences(BaseModel):
    email: bool = True
    push: bool = True
    sms: bool = True


class NotificationPreferencesUpdate(BaseModel):
    email: bool | None = None
    push: bool | None = None
    sms: bool | None = None


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
    notification_preferences: NotificationPreferences = Field(
        default_factory=NotificationPreferences,
    )

    model_config = ConfigDict(use_enum_values=True)


class UserUpdateProfileRequest(BaseModel):
    full_name: str | None = None
    notification_preferences: NotificationPreferencesUpdate | None = None


class UserUpdateEmailRequest(BaseModel):
    email: str
    otp_code: str


class UserUpdatePhoneRequest(BaseModel):
    phone: str
    otp_code: str
