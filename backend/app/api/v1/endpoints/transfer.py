from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.transactions import send_money
from app.db.session import get_db
from app.models.transaction import Transaction
from app.models.user import KYCStatus, User
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.transaction import SendMoneyRequest
from app.schemas.transfer import TransferByMobileRequest, TransferReceipt
from app.schemas.user import CurrentUser

router = APIRouter(prefix="/transfer/neo", tags=["transfers"])


@router.post("/mobile", response_model=TransferReceipt)
async def transfer_by_mobile(
    payload: TransferByMobileRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sender_id = int(current_user.id)

    result = await db.execute(select(User).where(User.phone == payload.receiver_phone))
    receiver = result.scalar_one_or_none()

    if receiver is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "receiver_not_found"},
        )

    if receiver.kyc_status != KYCStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "receiver_kyc_not_approved"},
        )

    if receiver.id == sender_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send money to yourself",
        )

    try:
        wallet_currency = WalletCurrency(payload.currency)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported currency: {payload.currency}",
        )

    result = await db.execute(
        select(Wallet).where(
            Wallet.user_id == sender_id,
            Wallet.currency == wallet_currency,
        )
    )
    sender_wallet = result.scalar_one_or_none()

    if sender_wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"You have no {payload.currency} wallet",
        )

    if sender_wallet.balance < payload.amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "insufficient_balance",
                "available": str(sender_wallet.balance),
                "requested": str(payload.amount),
            },
        )

    send_result = await send_money(
        payload=SendMoneyRequest(
            receiver_id=str(receiver.id),
            amount=payload.amount,
            currency=payload.currency,
        ),
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )

    # NOTE (DEVATTECH-80 vs NBL-106 stub): the ticket asks us to enqueue a
    # fraud-scoring Celery task post-commit. send_money() above already
    # scores the transaction synchronously in-process before returning (see
    # app/api/v1/endpoints/transactions.py), against the same DEVATTECH-36
    # stub. Enqueuing score_transaction a second time here would double-
    # score against a no-op stub, so it is intentionally NOT enqueued again.
    # Revisit once DEVATTECH-75 makes scoring genuinely async - at that
    # point send_money's inline call likely goes away and this becomes the
    # real enqueue point. Flagged to M1 / lead.

    result = await db.execute(
        select(Wallet).where(
            Wallet.user_id == sender_id,
            Wallet.currency == wallet_currency,
        )
    )
    sender_wallet = result.scalar_one()

    result = await db.execute(
        select(Transaction).where(Transaction.id == send_result.transaction_id)
    )
    transaction = result.scalar_one()

    return TransferReceipt(
        transaction_id=send_result.transaction_id,
        amount=send_result.amount,
        currency=send_result.currency,
        receiver_display_name=receiver.full_name,
        sender_new_balance=sender_wallet.balance,
        timestamp=transaction.created_at,
    )
