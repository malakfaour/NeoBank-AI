from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.kyc_record import KYCRecordStatus
from app.models.user import KYCStatus


class AdminKYCQueueItem(BaseModel):
    id: int
    user_id: int
    full_name: str
    status: KYCRecordStatus
    created_at: datetime
    match_score: float | None
    liveness_score: float | None
    rejection_reason: str | None
    reviewed_at: datetime | None
    reviewed_by: int | None
    selfie_url: str | None
    id_photo_url: str | None
    selfie_presigned_url: str | None
    id_photo_presigned_url: str | None

    model_config = ConfigDict(use_enum_values=True)


class AdminKYCQueueResponse(BaseModel):
    items: list[AdminKYCQueueItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminKYCDecisionResponse(BaseModel):
    kyc_record_id: int
    user_id: int
    status: KYCRecordStatus
    user_kyc_status: KYCStatus
    rejection_reason: str | None
    reviewed_at: datetime | None
    reviewed_by: int | None

    model_config = ConfigDict(use_enum_values=True)


class AdminKYCRejectRequest(BaseModel):
    rejection_reason: str
