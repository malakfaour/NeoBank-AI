import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.beneficiary import Beneficiary, BeneficiaryType
from app.schemas.beneficiary import (
    BeneficiaryCreateRequest,
    BeneficiaryPageResponse,
    BeneficiaryResponse,
    BeneficiaryUpdateRequest,
    DeleteBeneficiaryResponse,
)
from app.schemas.auth import CurrentUser
from app.services.rate_limiter import check_rate_limit

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])

LEBANESE_MOBILE_PATTERN = re.compile(r"^\+961\d{7,8}$")
LEBANESE_IBAN_PATTERN = re.compile(r"^LB\d{2}[A-Z0-9]{24}$")

# Write-endpoint rate-limiting gap flagged in the engineering gap analysis.
# Lower money-risk than transfers/top-up/exchange, so a looser budget --
# still enough to stop scripted create/delete abuse.
_BENEFICIARY_WRITE_MAX_REQUESTS = 10
_BENEFICIARY_WRITE_WINDOW_SECONDS = 60


def get_user_id(current_user: CurrentUser) -> int:
    try:
        return int(current_user.id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user id in token",
        ) from exc


def normalize_value(value: str) -> str:
    return value.strip().replace(" ", "").upper()


def validate_mobile(value: str) -> None:
    if not LEBANESE_MOBILE_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mobile beneficiary must match Lebanese format, example: +96170111222",
        )


def validate_iban(value: str) -> None:
    if not LEBANESE_IBAN_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IBAN beneficiary must match Lebanese IBAN format starting with LB.",
        )

    rearranged = value[4:] + value[:4]
    numeric_iban = ""

    for char in rearranged:
        if char.isdigit():
            numeric_iban += char
        else:
            numeric_iban += str(ord(char) - 55)

    if int(numeric_iban) % 97 != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid IBAN checksum.",
        )


def validate_beneficiary_value(
    beneficiary_type: BeneficiaryType,
    value: str,
) -> None:
    if beneficiary_type == BeneficiaryType.MOBILE:
        validate_mobile(value)

    if beneficiary_type == BeneficiaryType.IBAN:
        validate_iban(value)


@router.post(
    "",
    response_model=BeneficiaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_beneficiary(
    request: Request,
    body: BeneficiaryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    await check_rate_limit(
        request,
        key_prefix=f"beneficiary_write:{user_id}",
        max_requests=_BENEFICIARY_WRITE_MAX_REQUESTS,
        window_seconds=_BENEFICIARY_WRITE_WINDOW_SECONDS,
    )
    nickname = body.nickname.strip()
    value = normalize_value(body.value)

    validate_beneficiary_value(body.type, value)

    existing_result = await db.execute(
        select(Beneficiary).where(
            Beneficiary.user_id == user_id,
            Beneficiary.type == body.type,
            Beneficiary.value == value,
            Beneficiary.deleted_at.is_(None),
        )
    )
    existing_beneficiary = existing_result.scalar_one_or_none()

    if existing_beneficiary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Beneficiary already exists.",
        )

    beneficiary = Beneficiary(
        user_id=user_id,
        nickname=nickname,
        type=body.type,
        value=value,
    )

    db.add(beneficiary)
    await db.commit()
    await db.refresh(beneficiary)

    return beneficiary


@router.get("", response_model=BeneficiaryPageResponse)
async def list_beneficiaries(
    search: str | None = Query(None),
    beneficiary_type: BeneficiaryType | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    offset = (page - 1) * page_size

    filters = [
        Beneficiary.user_id == user_id,
        Beneficiary.deleted_at.is_(None),
    ]

    if beneficiary_type is not None:
        filters.append(Beneficiary.type == beneficiary_type)

    if search:
        search_pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Beneficiary.nickname.ilike(search_pattern),
                Beneficiary.value.ilike(search_pattern),
            )
        )

    total_result = await db.execute(
        select(func.count(Beneficiary.id)).where(*filters)
    )
    total = total_result.scalar_one()

    beneficiaries_result = await db.execute(
        select(Beneficiary)
        .where(*filters)
        .order_by(Beneficiary.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    beneficiaries = beneficiaries_result.scalars().all()

    return {
        "items": beneficiaries,
        "page": page,
        "page_size": page_size,
        "total": total or 0,
    }


@router.get("/{beneficiary_id}", response_model=BeneficiaryResponse)
async def get_beneficiary(
    beneficiary_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)

    result = await db.execute(
        select(Beneficiary).where(
            Beneficiary.id == beneficiary_id,
            Beneficiary.user_id == user_id,
            Beneficiary.deleted_at.is_(None),
        )
    )
    beneficiary = result.scalar_one_or_none()

    if beneficiary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Beneficiary not found.",
        )

    return beneficiary


@router.patch("/{beneficiary_id}", response_model=BeneficiaryResponse)
async def update_beneficiary(
    request: Request,
    beneficiary_id: int,
    body: BeneficiaryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    await check_rate_limit(
        request,
        key_prefix=f"beneficiary_write:{user_id}",
        max_requests=_BENEFICIARY_WRITE_MAX_REQUESTS,
        window_seconds=_BENEFICIARY_WRITE_WINDOW_SECONDS,
    )

    result = await db.execute(
        select(Beneficiary).where(
            Beneficiary.id == beneficiary_id,
            Beneficiary.user_id == user_id,
            Beneficiary.deleted_at.is_(None),
        )
    )
    beneficiary = result.scalar_one_or_none()

    if beneficiary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Beneficiary not found.",
        )

    beneficiary.nickname = body.nickname.strip()

    await db.commit()
    await db.refresh(beneficiary)

    return beneficiary


@router.delete("/{beneficiary_id}", response_model=DeleteBeneficiaryResponse)
async def delete_beneficiary(
    request: Request,
    beneficiary_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = get_user_id(current_user)
    await check_rate_limit(
        request,
        key_prefix=f"beneficiary_write:{user_id}",
        max_requests=_BENEFICIARY_WRITE_MAX_REQUESTS,
        window_seconds=_BENEFICIARY_WRITE_WINDOW_SECONDS,
    )

    result = await db.execute(
        select(Beneficiary).where(
            Beneficiary.id == beneficiary_id,
            Beneficiary.user_id == user_id,
            Beneficiary.deleted_at.is_(None),
        )
    )
    beneficiary = result.scalar_one_or_none()

    if beneficiary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Beneficiary not found.",
        )

    beneficiary.deleted_at = datetime.now(timezone.utc)

    await db.commit()

    return {"message": "Beneficiary deleted successfully."}