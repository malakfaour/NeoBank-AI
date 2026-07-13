from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: int
    type: NotificationType
    message: str
    read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class NotificationPageResponse(BaseModel):
    items: list[NotificationResponse]
    page: int
    page_size: int
    total: int


class ReadAllNotificationsResponse(BaseModel):
    updated_count: int


class PushSubscriptionCreate(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)


class PushSubscriptionResponse(BaseModel):
    id: int
    token: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
