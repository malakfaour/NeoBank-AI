from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.beneficiary import BeneficiaryType


class BeneficiaryCreateRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=100)
    type: BeneficiaryType
    value: str = Field(..., min_length=1, max_length=255)


class BeneficiaryUpdateRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=100)


class BeneficiaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    nickname: str
    type: BeneficiaryType
    value: str
    created_at: datetime


class BeneficiaryPageResponse(BaseModel):
    items: list[BeneficiaryResponse]
    page: int
    page_size: int
    total: int


class DeleteBeneficiaryResponse(BaseModel):
    message: str