from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_action_token
from app.db.session import get_db
from app.schemas.transfer import (
    TransferByIbanRequest,
    TransferByMobileRequest,
    TransferReceipt,
)
from app.schemas.user import CurrentUser
from app.services.transfer_service import (
    execute_transfer_by_iban,
    execute_transfer_by_mobile,
)

router = APIRouter(prefix="/transfer/neo", tags=["transfers"])


@router.post("/mobile", response_model=TransferReceipt)
async def transfer_by_mobile(
    payload: TransferByMobileRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(require_action_token),
    db: AsyncSession = Depends(get_db),
):
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
    payload: TransferByIbanRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(require_action_token),
    db: AsyncSession = Depends(get_db),
):
    return await execute_transfer_by_iban(
        sender_id=int(current_user.id),
        receiver_iban=payload.receiver_iban,
        amount=payload.amount,
        currency=payload.currency,
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )
