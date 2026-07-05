from datetime import datetime

from pydantic import BaseModel, ConfigDict

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