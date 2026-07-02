import re

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
from app.schemas.transfer import (
    TransferByIbanRequest,
    TransferByMobileRequest,
    TransferReceipt,
)
from app.schemas.user import CurrentUser

router = APIRouter(prefix="/transfer/neo", tags=["transfers"])

LEBANESE_IBAN_PATTERN = re.compile(r"^LB[A-Za-z0-9]{26}$")


async def _execute_transfer(
    *,
    sender_id: int,
    receiver: User,
    amount,
    currency: str,
    x_idempotency_key: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> TransferReceipt:
    """
    Shared post-lookup transfer logic for both mobile- and IBAN-based
    transfers (DEVATTECH-80 / DEVATTECH-82). Everything after "we know who
    the receiver is" is identical between the two entry points, so it lives
    here once instead of being duplicated per lookup method.
    """
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
        wallet_currency = WalletCurrency(currency)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported currency: {currency}",
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
            detail=f"You have no {currency} wallet",
        )

    if sender_wallet.balance < amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "insufficient_balance",
                "available": str(sender_wallet.balance),
                "requested": str(amount),
            },
        )

    send_result = await send_money(
        payload=SendMoneyRequest(
            receiver_id=str(receiver.id),
            amount=amount,
            currency=currency,
        ),
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )

    # NOTE (DEVATTECH-80/82 vs NBL-106 stub): see transactions.py TODO re:
    # DEVATTECH-75. send_money() already scores synchronously in-process;
    # not enqueuing score_transaction again here to avoid double-scoring
    # against the stub. Revisit when DEVATTECH-75 lands the real model.

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

    return await _execute_transfer(
        sender_id=sender_id,
        receiver=receiver,
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
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sender_id = int(current_user.id)

    if not LEBANESE_IBAN_PATTERN.match(payload.receiver_iban):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Lebanese IBAN format (expected LB + 26 alphanumeric characters)",
        )

    result = await db.execute(
        select(Wallet, User)
        .join(User, User.id == Wallet.user_id)
        .where(Wallet.iban == payload.receiver_iban)
    )
    row = result.first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "receiver_not_found"},
        )

    receiver_wallet, receiver = row

    if payload.currency != receiver_wallet.currency.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Currency mismatch: requested {payload.currency}, "
                f"but this IBAN's wallet is {receiver_wallet.currency.value}"
            ),
        )

    return await _execute_transfer(
        sender_id=sender_id,
        receiver=receiver,
        amount=payload.amount,
        currency=receiver_wallet.currency.value,
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )
