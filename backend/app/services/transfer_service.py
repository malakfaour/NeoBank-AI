import re
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.transactions import send_money
from app.models.transaction import Transaction
from app.models.user import KYCStatus, User
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.transaction import SendMoneyRequest
from app.schemas.transfer import TransferReceipt
from app.schemas.user import CurrentUser

LEBANESE_IBAN_PATTERN = re.compile(r"^LB[A-Za-z0-9]{26}$")


async def execute_transfer(
    *,
    sender_id: int,
    receiver: User,
    amount: Decimal,
    currency: str,
    x_idempotency_key: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> TransferReceipt:
    """
    Shared transfer execution path.

    Used by the transfer endpoints and the chatbot confirmation flow.
    This is the only Neo transfer execution path: validate receiver/wallet
    state, then delegate to send_money().
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


async def execute_transfer_by_mobile(
    *,
    sender_id: int,
    receiver_phone: str,
    amount: Decimal,
    currency: str,
    x_idempotency_key: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> TransferReceipt:
    result = await db.execute(select(User).where(User.phone == receiver_phone))
    receiver = result.scalar_one_or_none()

    if receiver is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "receiver_not_found"},
        )

    return await execute_transfer(
        sender_id=sender_id,
        receiver=receiver,
        amount=amount,
        currency=currency,
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )


async def execute_transfer_by_iban(
    *,
    sender_id: int,
    receiver_iban: str,
    amount: Decimal,
    currency: str,
    x_idempotency_key: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> TransferReceipt:
    if not LEBANESE_IBAN_PATTERN.match(receiver_iban):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Lebanese IBAN format (expected LB + 26 alphanumeric characters)",
        )

    result = await db.execute(
        select(Wallet, User)
        .join(User, User.id == Wallet.user_id)
        .where(Wallet.iban == receiver_iban)
    )
    row = result.first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "receiver_not_found"},
        )

    receiver_wallet, receiver = row

    if currency != receiver_wallet.currency.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Currency mismatch: requested {currency}, "
                f"but this IBAN's wallet is {receiver_wallet.currency.value}"
            ),
        )

    return await execute_transfer(
        sender_id=sender_id,
        receiver=receiver,
        amount=amount,
        currency=receiver_wallet.currency.value,
        x_idempotency_key=x_idempotency_key,
        current_user=current_user,
        db=db,
    )
