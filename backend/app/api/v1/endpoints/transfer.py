from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_action_token
from app.db.session import get_db
from app.schemas.transfer import (
    TransferByIbanRequest,
    TransferByMobileRequest,
    TransferReceipt,
)
from app.schemas.auth import CurrentUser
from app.services.rate_limiter import check_rate_limit
from app.services.transfer_service import (
    execute_transfer_by_iban,
    execute_transfer_by_mobile,
)

router = APIRouter(prefix="/transfer/neo", tags=["transfers"])

# Write-endpoint rate-limiting gap flagged in the engineering gap analysis.
# Same shape as the DEVATTECH-107 velocity guard on /transactions/send
# (transactions.py): scoped per user+IP, since these are also direct
# money-moving transfers.
_TRANSFER_MAX_REQUESTS = 5
_TRANSFER_WINDOW_SECONDS = 60


@router.post("/mobile", response_model=TransferReceipt)
async def transfer_by_mobile(
    request: Request,
    payload: TransferByMobileRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(require_action_token),
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        request,
        key_prefix=f"transfer_neo:{current_user.id}",
        max_requests=_TRANSFER_MAX_REQUESTS,
        window_seconds=_TRANSFER_WINDOW_SECONDS,
    )
    return await execute_transfer_by_mobile(
        sender_id=int(current_user.id),
        receiver_phone=payload.receiver_phone,
        amount=payload.amount,
        currency=payload.currency,
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )


@router.post("/iban", response_model=TransferReceipt)
async def transfer_by_iban(
    request: Request,
    payload: TransferByIbanRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(require_action_token),
    db: AsyncSession = Depends(get_db),
):
    # Shared budget with /mobile above -- same underlying risk (direct
    # intra-neo transfer), just a different lookup key.
    await check_rate_limit(
        request,
        key_prefix=f"transfer_neo:{current_user.id}",
        max_requests=_TRANSFER_MAX_REQUESTS,
        window_seconds=_TRANSFER_WINDOW_SECONDS,
    )
    return await execute_transfer_by_iban(
        sender_id=int(current_user.id),
        receiver_iban=payload.receiver_iban,
        amount=payload.amount,
        currency=payload.currency,
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )
