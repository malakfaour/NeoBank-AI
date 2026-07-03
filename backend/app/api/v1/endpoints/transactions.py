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
from app.services.audit_log import append_audit
from app.tasks.transaction_tasks import score_transaction

from datetime import date, timedelta

from fastapi import Query
from sqlalchemy import and_, func, or_

from app.models.transaction_audit_log import TransactionAuditLog
from app.models.user import User
from app.schemas.transaction import (
    CategorySummaryItem,
    TransactionAuditLogItem,
    TransactionDetailResponse,
    TransactionListItem,
    TransactionListResponse,
    TransactionSummaryResponse,
)
from app.utils.transaction_query_utils import compute_total_pages, parse_summary_month

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

    # --- fraud scoring ---
    # TODO(Sprint 3 / DEVATTECH-75): once real scoring is genuinely
    # asynchronous (calls an external model service, not instant), this
    # inline synchronous call must be replaced with a callback/webhook that
    # updates the transaction status once the Celery task actually
    # completes, instead of deciding status synchronously in this request.
    try:
        score_result = score_transaction(transaction.id)
        transaction.fraud_score = score_result["score"]
        transaction.scoring_model = score_result.get("model")
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

# --- DEVATTECH-73: transaction history / detail / summary ---
#
# Everything below this line is new. send_money() above is byte-for-byte
# unchanged from the base file. New imports needed only for the endpoints
# below are also placed here (after send_money), rather than added into the
# original import block above — Python resolves names inside a function
# body at call time, not at definition time, so module-level imports placed
# after a function's def are still valid before any request is served.

# Route registration order matters here: "/summary" is registered before
# "/{transaction_id}" so a request to GET /transactions/summary doesn't get
# swallowed by the {transaction_id} path parameter.

# The `transactions` table only models peer-to-peer transfers
# (sender_id/receiver_id). topup/bill/exchange belong to other features
# (bill payments, exchange execution) that don't write to this table yet.
# These values are accepted as valid filters (so the endpoint doesn't 400
# on a legitimate future value) but currently match zero rows.
VALID_TRANSACTION_TYPES = {"send", "receive", "topup", "bill", "exchange"}
TYPES_NOT_YET_SUPPORTED = {"topup", "bill", "exchange"}


@router.get("/summary", response_model=TransactionSummaryResponse)
async def get_transaction_summary(
    month: str = Query(..., description="Format YYYY-MM, e.g. 2026-07"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Total amount spent (outgoing only — current user as sender) per
    category, for the given month. Used by the dashboard spending chart.

    Grouped by (category, currency), not category alone — summing amounts
    across different currencies (USD/LBP/USDT) into one total would be
    financially meaningless. currency is included in each row as a result.
    """
    try:
        year, month_num = parse_summary_month(month)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month must be in YYYY-MM format",
        )

    sender_id = int(current_user.id)

    month_start = date(year, month_num, 1)
    month_end = date(year + 1, 1, 1) if month_num == 12 else date(year, month_num + 1, 1)

    result = await db.execute(
        select(
            Transaction.category,
            Transaction.currency,
            func.sum(Transaction.amount).label("total_amount"),
            func.count(Transaction.id).label("transaction_count"),
        )
        .where(Transaction.sender_id == sender_id)
        .where(Transaction.created_at >= month_start)
        .where(Transaction.created_at < month_end)
        .group_by(Transaction.category, Transaction.currency)
    )
    summary_items = [
        CategorySummaryItem(
            category=row.category,
            currency=row.currency.value,
            total_amount=row.total_amount,
            transaction_count=row.transaction_count,
        )
        for row in result.all()
    ]

    return TransactionSummaryResponse(month=month, summary=summary_items)


@router.get("/{transaction_id}", response_model=TransactionDetailResponse)
async def get_transaction_detail(
    transaction_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    NOTE: restricted to transactions the authenticated user is a party to
    (sender or receiver) — not explicit in the ticket text, but returning
    any user's transaction + audit trail to anyone with a guessable id
    would be a data leak. Added as a security default.
    """
    user_id = int(current_user.id)

    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()

    if transaction is None or user_id not in (transaction.sender_id, transaction.receiver_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    is_sender = transaction.sender_id == user_id
    counterparty_id = transaction.receiver_id if is_sender else transaction.sender_id

    counterparty_result = await db.execute(select(User).where(User.id == counterparty_id))
    counterparty = counterparty_result.scalar_one_or_none()

    audit_result = await db.execute(
        select(TransactionAuditLog)
        .where(TransactionAuditLog.transaction_id == transaction_id)
        .order_by(TransactionAuditLog.timestamp.asc())
    )
    audit_logs = audit_result.scalars().all()

    return TransactionDetailResponse(
        id=transaction.id,
        sender_id=transaction.sender_id,
        receiver_id=transaction.receiver_id,
        type="send" if is_sender else "receive",
        amount=transaction.amount,
        currency=transaction.currency.value,
        counterparty_name=counterparty.full_name if counterparty else None,
        category=transaction.category,
        fraud_score=transaction.fraud_score,
        rule_triggered=None,  # fraud_flags table doesn't exist yet — see DEVATTECH-73 notes
        status=transaction.status.value,
        flagged=transaction.status == TransactionStatus.flagged,
        created_at=transaction.created_at,
        audit_logs=[
            TransactionAuditLogItem(
                id=log.id,
                action=log.action,
                actor_id=log.actor_id,
                timestamp=log.timestamp,
                metadata=log.event_metadata,
            )
            for log in audit_logs
        ],
    )


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    start_date: date | None = None,
    end_date: date | None = None,
    type: str | None = Query(default=None),
    category: str | None = None,
    currency: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user.id)

    if type is not None and type not in VALID_TRANSACTION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"type must be one of {sorted(VALID_TRANSACTION_TYPES)}",
        )

    # topup/bill/exchange can't be produced by this table yet (see notes
    # above) — return a correctly-shaped empty page instead of querying.
    if type in TYPES_NOT_YET_SUPPORTED:
        return TransactionListResponse(items=[], page=page, page_size=page_size, total=0, total_pages=0)

    currency_enum = None
    if currency is not None:
        try:
            currency_enum = TransactionCurrency(currency)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported currency: {currency}",
            )

    filters = [or_(Transaction.sender_id == user_id, Transaction.receiver_id == user_id)]

    if type == "send":
        filters.append(Transaction.sender_id == user_id)
    elif type == "receive":
        filters.append(Transaction.receiver_id == user_id)

    if start_date is not None:
        filters.append(Transaction.created_at >= start_date)
    if end_date is not None:
        filters.append(Transaction.created_at < end_date + timedelta(days=1))
    if category is not None:
        filters.append(Transaction.category == category)
    if currency_enum is not None:
        filters.append(Transaction.currency == currency_enum)

    count_result = await db.execute(select(func.count(Transaction.id)).where(and_(*filters)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Transaction)
        .where(and_(*filters))
        .order_by(Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    transactions = result.scalars().all()

    # Batch-resolve counterparty names in one query, instead of one query
    # per row.
    counterparty_ids = {
        (tx.receiver_id if tx.sender_id == user_id else tx.sender_id) for tx in transactions
    }
    users_by_id = {}
    if counterparty_ids:
        users_result = await db.execute(select(User).where(User.id.in_(counterparty_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    items = []
    for tx in transactions:
        is_sender = tx.sender_id == user_id
        counterparty_id = tx.receiver_id if is_sender else tx.sender_id
        counterparty = users_by_id.get(counterparty_id)

        items.append(
            TransactionListItem(
                id=tx.id,
                type="send" if is_sender else "receive",
                amount=tx.amount,
                currency=tx.currency.value,
                counterparty_name=counterparty.full_name if counterparty else None,
                category=tx.category,
                fraud_score=tx.fraud_score,
                rule_triggered=None,  # fraud_flags table doesn't exist yet
                status=tx.status.value,
                flagged=tx.status == TransactionStatus.flagged,
                created_at=tx.created_at,
            )
        )

    return TransactionListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=compute_total_pages(total, page_size),
    )
