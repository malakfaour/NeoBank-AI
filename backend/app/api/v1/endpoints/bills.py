import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.cache_utils import invalidate_balance_cache
from app.db.session import get_db
from app.models.bill_payment import BillPayment, BillPaymentStatus, BillType
from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.bill import BillHistoryItem, BillHistoryResponse, BillPayRequest, BillPayResponse
from app.schemas.user import CurrentUser
from app.services.audit_log import append_audit
from app.services.biller_client import call_mock_biller
from app.services.wallet_locking import lock_and_debit_wallet
from app.tasks.transaction_tasks import score_transaction

router = APIRouter(prefix="/bills", tags=["bills"])
logger = logging.getLogger(__name__)


def _compute_total_pages(total: int, page_size: int) -> int:
    if total == 0:
        return 0
    return (total + page_size - 1) // page_size


@router.post("/pay", response_model=BillPayResponse)
async def pay_bill(
    payload: BillPayRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user.id)

    wallet_currency = WalletCurrency(payload.currency)

    # --- ownership + advisory balance check, WITHOUT a row lock ---
    # Lock is deliberately not held across the biller call below --
    # holding a row lock across an external HTTP call is an anti-pattern.
    # Balance is re-checked under lock right before the actual debit, via
    # lock_and_debit_wallet() further down.
    result = await db.execute(
        select(Wallet).where(Wallet.id == payload.from_wallet_id).where(Wallet.user_id == user_id)
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found or does not belong to you",
        )

    if wallet.currency != wallet_currency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="currency does not match the selected wallet's currency",
        )

    if wallet.balance < payload.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")

    # --- call biller (no lock held during this network call) ---
    biller_result = await call_mock_biller(payload.bill_type, payload.bill_reference, payload.amount)

    if not biller_result.success:
        bill_payment = BillPayment(
            user_id=user_id,
            wallet_id=wallet.id,
            bill_type=BillType(payload.bill_type),
            bill_reference=payload.bill_reference,
            amount=payload.amount,
            currency=wallet_currency,
            status=BillPaymentStatus.failed,
            biller_error=biller_result.biller_error,
        )
        db.add(bill_payment)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"biller_error": biller_result.biller_error},
        )

    # --- success: lock + re-check + debit ---
    try:
        wallet = await lock_and_debit_wallet(db, wallet.id, payload.amount)
    except ValueError:
        # Balance changed between the advisory check and now (e.g. a
        # concurrent spend) -- the biller already reported success, so
        # this is a genuine reconciliation problem, not a normal
        # validation failure. Out of scope for this ticket to resolve
        # automatically; logged for manual follow-up.
        logger.error(
            "Bill payment reconciliation issue: biller succeeded for user %s "
            "(%s %s) but wallet %s balance is now insufficient.",
            user_id, payload.bill_type, payload.bill_reference, wallet.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment could not be completed due to a balance conflict. Contact support.",
        )

    # NOTE (documented, accepted limitation -- not solved in this ticket):
    # Transaction.sender_id/receiver_id are both NOT NULL FKs to users.id --
    # there's no external-biller concept in this schema. Using
    # receiver_id = sender_id as a placeholder. This causes
    # GET /transactions (untouched) to resolve counterparty_name to the
    # payer's own name for bill payments.
    transaction = Transaction(
        sender_id=user_id,
        receiver_id=user_id,
        amount=payload.amount,
        currency=TransactionCurrency(payload.currency),
        category="Bills",
        status=TransactionStatus.pending,
        # Random, not derived from bill details -- a deterministic key
        # here would incorrectly block a legitimate second payment of the
        # same bill/amount (e.g. two months of the same top-up amount).
        idempotency_key=f"bill:{uuid.uuid4().hex}",
    )
    db.add(transaction)
    await db.flush()  # populate transaction.id before creating bill_payment's FK

    bill_payment = BillPayment(
        user_id=user_id,
        wallet_id=wallet.id,
        bill_type=BillType(payload.bill_type),
        bill_reference=payload.bill_reference,
        amount=payload.amount,
        currency=wallet_currency,
        status=BillPaymentStatus.success,
        transaction_id=transaction.id,
    )
    db.add(bill_payment)

    await db.commit()
    await db.refresh(transaction)
    await db.refresh(bill_payment)

    # Required by engineering rules: no wallet mutation without an audit
    # entry. Using the existing append_audit() helper -- never hand-writing
    # audit inserts.
    #
    # IMPORTANT: by this point the payment has already succeeded and is
    # durably committed (wallet debited, transaction + bill_payment rows
    # persisted). append_audit(), score_transaction.delay(), and
    # invalidate_balance_cache() below are best-effort follow-ups -- if any
    # of them raises (a transient DB/Redis/broker hiccup), that must NOT
    # surface as a 500 to the client for a payment that actually succeeded.
    # An uncaught exception here would tell the user their payment failed
    # when it didn't, inviting a duplicate payment attempt. Each is logged
    # at ERROR level for manual follow-up instead of propagating.
    try:
        await append_audit(
            db,
            transaction_id=transaction.id,
            action="created",
            actor_id=user_id,
            metadata={
                "amount": str(payload.amount),
                "currency": payload.currency,
                "bill_type": payload.bill_type,
                "bill_reference": payload.bill_reference,
            },
        )
    except Exception:
        logger.error(
            "Bill payment succeeded but audit log write failed for transaction %s "
            "(user %s, %s %s). Manual audit backfill may be required.",
            transaction.id, user_id, payload.bill_type, payload.bill_reference,
            exc_info=True,
        )

    # NOTE (documented, accepted limitation -- not solved in this ticket):
    # per instruction, only .delay() is used here, after commit -- no
    # synchronous score_transaction() call like send_money has. Nothing
    # currently consumes this task's result and writes it back, so this
    # transaction's fraud_score/scoring_model/status will remain
    # NULL/NULL/"pending" indefinitely. Closing that gap (a callback/
    # webhook from the Celery task back to the transaction row) is out of
    # scope for this ticket.
    try:
        score_transaction.delay(transaction.id)
    except Exception:
        logger.error(
            "Bill payment succeeded but fraud-scoring enqueue failed for "
            "transaction %s (user %s). Transaction will remain unscored "
            "until manually re-enqueued.",
            transaction.id, user_id,
            exc_info=True,
        )

    try:
        await invalidate_balance_cache(user_id)
    except Exception:
        logger.error(
            "Bill payment succeeded but balance cache invalidation failed "
            "for user %s. Cached balance may be stale until next natural "
            "invalidation or TTL expiry.",
            user_id,
            exc_info=True,
        )

    return BillPayResponse(
        bill_payment_id=bill_payment.id,
        status=bill_payment.status.value,
        bill_type=bill_payment.bill_type.value,
        bill_reference=bill_payment.bill_reference,
        amount=bill_payment.amount,
        currency=bill_payment.currency.value,
        transaction_id=transaction.id,
    )


@router.get("/history", response_model=BillHistoryResponse)
async def get_bill_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user.id)

    count_result = await db.execute(
        select(func.count()).select_from(BillPayment).where(BillPayment.user_id == user_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(BillPayment)
        .where(BillPayment.user_id == user_id)
        .order_by(BillPayment.paid_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    bill_payments = result.scalars().all()

    items = [
        BillHistoryItem(
            id=bp.id,
            bill_type=bp.bill_type.value,
            bill_reference=bp.bill_reference,
            amount=bp.amount,
            currency=bp.currency.value,
            status=bp.status.value,
            biller_error=bp.biller_error,
            paid_at=bp.paid_at,
        )
        for bp in bill_payments
    ]

    return BillHistoryResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=_compute_total_pages(total, page_size),
    )
