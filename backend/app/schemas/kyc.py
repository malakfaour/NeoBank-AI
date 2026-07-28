from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.user import KYCStatus
from app.models.kyc_record import KYCDocumentType, KYCRecordStatus


class KYCStatusResponse(BaseModel):
    user_id: int
    kyc_status: KYCStatus


class KYCStatusUpdateRequest(BaseModel):
    user_id: int
    status: KYCStatus


class KYCUploadResponse(BaseModel):
    kyc_record_id: int
    selfie_url: str
    id_photo_url: str
    document_type: KYCDocumentType
    status: KYCRecordStatus


class KYCSelfieUploadResponse(BaseModel):
    kyc_record_id: int
    selfie_url: str
    status: KYCRecordStatus


class KYCDocumentAccessResponse(BaseModel):
    kyc_record_id: int
    selfie_key: str | None
    id_photo_key: str | None
    back_id_photo_key: str | None
    selfie_presigned_url: str | None
    id_photo_presigned_url: str | None
    back_id_photo_presigned_url: str | None


class KYCProfileData(BaseModel):
    first_name: str | None = None
    fathers_name: str | None = None
    mothers_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    place_of_birth: str | None = None
    gender: str | None = None
    marital_status: str | None = None
    nationality: str | None = None
    other_nationality: str | None = None
    identification_type: Literal["national_id", "passport"] | None = None
    identification_number: str | None = None
    record_number: str | None = None
    register_place: str | None = None
    id_expiry_date: date | None = None
    country_of_residence: str | None = None
    governorate: str | None = None
    district: str | None = None
    state: str | None = None
    city: str | None = None
    street: str | None = None
    building: str | None = None
    floor: str | None = None
    neighbourhood: str | None = None
    residential_address: str | None = None
    occupation: str | None = None
    employer_name: str | None = None
    position: str | None = None
    employment_address: str | None = None
    employer_phone: str | None = None
    education_institution: str | None = None
    source_of_funds: str | None = None
    annual_income_usd: float | None = Field(default=None, ge=0)
    other_source_of_income: str | None = None


class KYCDraftUpdateRequest(BaseModel):
    current_step: int = Field(ge=1, le=6)
    profile_data: KYCProfileData


class KYCConsentRequest(BaseModel):
    terms_accepted: bool
    information_confirmed: bool
    privacy_consent: bool


class KYCProfileResponse(BaseModel):
    kyc_record_id: int
    kyc_status: KYCStatus
    workflow_status: Literal[
        "not_started", "in_progress", "pending", "approved", "rejected"
    ]
    current_step: int
    profile_data: KYCProfileData
    has_front_id: bool
    has_back_id: bool
    has_selfie: bool
    rejection_reason: str | None
    submitted_at: datetime | None
