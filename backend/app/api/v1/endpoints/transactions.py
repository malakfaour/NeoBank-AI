from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.redis import (
    cache_idempotent_response,
    get_cached_idempotent_response,
    hash_idempotency_key,
)
from app.db.session import get_db
from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.transaction import SendMoneyRequest, SendMoneyResponse
from app.schemas.user import CurrentUser
from app.core.cache_utils import invalidate_balance_cache
from app.services.audit_log import append_audit
from app.tasks.transaction_tasks import score_transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])

# Fraud score threshold: at/above this, the transaction is held for review
# instead of completing automatically. Stub score is always 0.0 (never
# flagged) until the real model lands in Sprint 3 (DEVATTECH-75).
FRAUD_FLAG_THRESHOLD = 0.75


@router.post("/send", response_model=SendMoneyResponse)
async def send_money(
    payload: SendMoneyRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sender_id = int(current_user.id)

    # receiver_id arrives as str on the wire (schema), but the DB column is
    # Integer — validate/convert explicitly rather than let it fail deep in
    # a query.
    try:
        receiver_id = int(payload.receiver_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="receiver_id must be a valid integer user id",
        )

    if receiver_id == sender_id:
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

    # --- idempotency: replay cached response if this key was already used ---
    cached_response = await get_cached_idempotent_response(sender_id, x_idempotency_key)
    if cached_response is not None:
        return SendMoneyResponse(**cached_response)

    # --- locked wallet fetch ---
    # Both wallets are locked in ONE statement, ordered by Wallet.id. Any two
    # concurrent transfers (even in opposite directions between the same two
    # users) acquire row locks in the same global order, so this cannot
    # deadlock against another call to this same endpoint.
    result = await db.execute(
        select(Wallet)
        .where(Wallet.user_id.in_([sender_id, receiver_id]))
        .where(Wallet.currency == wallet_currency)
        .order_by(Wallet.id.asc())
        .with_for_update()
    )
    wallets_by_user = {w.user_id: w for w in result.scalars().all()}

    sender_wallet = wallets_by_user.get(sender_id)
    receiver_wallet = wallets_by_user.get(receiver_id)

    if sender_wallet is None or receiver_wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sender or receiver has no {payload.currency} wallet",
        )

    if sender_wallet.balance < payload.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient balance",
        )

    # --- debit / credit + insert transaction row, all in one commit ---
    sender_wallet.balance -= payload.amount
    receiver_wallet.balance += payload.amount

    transaction = Transaction(
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=payload.amount,
        currency=TransactionCurrency(wallet_currency.value),
        status=TransactionStatus.pending,
        idempotency_key=hash_idempotency_key(sender_id, x_idempotency_key),
    )
    db.add(transaction)

    try:
        await db.commit()
    except IntegrityError:
        # Redis-level idempotency check raced and both requests got past it
        # (see NOTE in app/core/redis.py) — the DB's unique constraint on
        # idempotency_key is the real safety net. Roll back so the debit/
        # credit we staged above never lands.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate request: this idempotency key is already being processed",
        )

    await db.refresh(transaction)

    # Invalidate cached balances (NBL-403) now that the debit/credit has
    # landed, so the next GET /accounts/balance for either party reads
    # fresh data instead of a stale pre-transfer value.
    await invalidate_balance_cache(sender_id)
    await invalidate_balance_cache(receiver_id)

    # --- fraud scoring ---
    # TODO(Sprint 3 / DEVATTECH-75): once real scoring is genuinely
    # asynchronous (calls an external model service, not instant), this
    # inline synchronous call must be replaced with a callback/webhook that
    # updates the transaction status once the Celery task actually
    # completes, instead of deciding status synchronously in this request.
    try:
        score_result = score_transaction(transaction.id)
        transaction.fraud_score = score_result["score"]
        transaction.status = (
            TransactionStatus.flagged
            if score_result["score"] >= FRAUD_FLAG_THRESHOLD
            else TransactionStatus.completed
        )
    except Exception:
        # Scoring failed after money already moved — don't silently leave
        # this as `pending`. Flag it for manual review instead.
        transaction.status = TransactionStatus.flagged

    await db.commit()
    await db.refresh(transaction)

    await append_audit(
        db,
        transaction_id=transaction.id,
        action="created",
        actor_id=sender_id,
        metadata={
            "amount": str(payload.amount),
            "currency": payload.currency,
            "receiver_id": receiver_id,
            "fraud_score": transaction.fraud_score,
        },
    )

    response = SendMoneyResponse(
        transaction_id=transaction.id,
        status=transaction.status.value,
        amount=transaction.amount,
        currency=transaction.currency.value,
        sender_id=sender_id,
        receiver_id=receiver_id,
        fraud_score=transaction.fraud_score,
    )

    await cache_idempotent_response(sender_id, x_idempotency_key, response.model_dump(mode="json"))

    return response