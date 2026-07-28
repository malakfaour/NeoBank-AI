import asyncio
import logging
from functools import partial
from typing import Literal

from app.core.storage import get_presigned_url, upload_file
from app.schemas.transaction import StatementResponse
from app.services.statement_generation import (
    generate_csv_bytes,
    generate_pdf_bytes,
    reconstruct_currency_statements,
)

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_action_token
from app.core.cache_utils import invalidate_balance_cache
from app.core.config import settings
from app.core.redis import (
    cache_idempotent_response,
    get_cached_idempotent_response,
    get_transfer_daily_total,
    hash_idempotency_key,
    increment_transfer_daily,
)
from app.db.session import get_db
from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
from app.models.wallet import Wallet, WalletCurrency
from app.schemas.transaction import SendMoneyRequest, SendMoneyResponse
from app.schemas.auth import CurrentUser
from app.services.audit_log import append_audit
from app.services.currency_conversion import to_usd_equivalent
from app.services.fraud_rules import CurrencyMismatchError, check_currency_match
from app.services.notifications import notify
from app.services.rate_limiter import check_rate_limit
from app.services.wallet_status import WalletClosedError, WalletFrozenError, assert_wallet_active
from app.tasks.transaction_tasks import score_transaction
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
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/send", response_model=SendMoneyResponse)
async def send_money(
    request: Request,
    payload: SendMoneyRequest,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: CurrentUser = Depends(require_action_token),
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

    # --- DEVATTECH-107: velocity guard -- >5 transfers/min per user.
    # key_prefix includes sender_id so check_rate_limit's key
    # (f"sliding:{key_prefix}:{ip}") is scoped per user+IP, not purely
    # per-IP like the pre-auth login/send_otp usages elsewhere in this
    # file -- check_rate_limit always folds in request.client.host too,
    # so a user switching networks mid-burst gets independent counters
    # per IP. That's a known characteristic of reusing this shared
    # limiter unchanged (ticket requires zero new limiting logic), not
    # something fixed here.
    await check_rate_limit(
        request,
        key_prefix=f"transfer:{sender_id}",
        max_requests=5,
        window_seconds=60,
    )

    # --- DEVATTECH-107: daily transfer cap. Placed after the
    # idempotency replay check above so a retried idempotent request
    # never consumes rate-limit or daily-cap budget for a transfer
    # that already happened. ---
    usd_equivalent = await to_usd_equivalent(payload.amount, wallet_currency.value, db)

    daily_total = await get_transfer_daily_total(sender_id)
    if daily_total + usd_equivalent > settings.DAILY_TRANSFER_LIMIT_USD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "daily_limit_exceeded",
                "remaining": str(max(settings.DAILY_TRANSFER_LIMIT_USD - daily_total, Decimal("0"))),
            },
        )

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

    for _w in (sender_wallet, receiver_wallet):
        try:
            assert_wallet_active(_w)
        except (WalletFrozenError, WalletClosedError) as e:
            reason = "wallet_frozen" if isinstance(e, WalletFrozenError) else "wallet_closed"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": reason},
            )

    try:
        check_currency_match(payload.currency, sender_wallet)
    except CurrencyMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "currency_mismatch", "detail": str(e)},
        )

    if sender_wallet.balance < payload.amount:
        # NBL-411: aligned to the same 422 {error, available, requested} shape
        # transfer.py already uses for its own pre-check -- send_money() is
        # called internally by transfer.py's _execute_transfer, so a stale
        # 400/string-detail response here could otherwise leak through in a
        # race where balance changes between transfer.py's pre-check and
        # this locked re-check.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "insufficient_balance",
                "available": str(sender_wallet.balance),
                "requested": str(payload.amount),
            },
        )

    # --- debit / credit + insert transaction row, all in one commit ---
    sender_wallet.balance -= payload.amount
    receiver_wallet.balance += payload.amount

    transaction = Transaction(
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=payload.amount,
        currency=TransactionCurrency(wallet_currency.value),
        category="Transfer",
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

    # --- DEVATTECH-107: daily transfer total, incremented only after a
    # real (non-replayed) transfer actually commits ---
    await increment_transfer_daily(sender_id, usd_equivalent)

    # --- DEVATTECH-74: audit trail — "created" fires first, right after the
    # transaction row exists, before fraud scoring runs. fraud_score is
    # intentionally omitted here (not known yet) — it's recorded on the
    # "fraud_scored" event below instead.
    await append_audit(
        db,
        transaction_id=transaction.id,
        action="created",
        actor_id=sender_id,
        metadata={
            "amount": str(payload.amount),
            "currency": payload.currency,
            "receiver_id": receiver_id,
        },
    )

    # --- fraud scoring (async) ---
    # DEVATTECH-48: fraud scoring is now dispatched as a background Celery
    # task. The transfer completes immediately; the worker flags/holds
    # after write-back.
    transaction.status = TransactionStatus.completed
    await db.commit()
    await db.refresh(transaction)

    score_transaction.delay(transaction.id)

    await append_audit(
        db,
        transaction_id=transaction.id,
        action="fraud_scoring_queued",
        actor_id=sender_id,
        metadata={"fraud_status": "pending"},
    )

    await append_audit(
        db,
        transaction_id=transaction.id,
        action="status_changed",
        actor_id=sender_id,
        metadata={
            "from": TransactionStatus.pending.value,
            "to": transaction.status.value,
        },
    )

    await append_audit(
        db,
        transaction_id=transaction.id,
        action=transaction.status.value,
        actor_id=sender_id,
        metadata={"fraud_status": "pending"},
    )

    await db.commit()
    await db.refresh(transaction)

     # --- notify both parties (email, plus whatever other channels the
    # existing notify() service already supports -- SMS for high-value
    # transfers, push, in-app) ---
    # By this point the transfer has fully committed and the money has
    # already moved -- a failure here must never surface as an error to
    # the caller (that would make a successful transfer look failed to
    # the frontend, and could prompt a confused retry/duplicate attempt).
    # notify()'s own internals already treat individual channels
    # (email/push/SMS) as best-effort, but the notification row + Redis
    # publish are not themselves guarded -- wrap the whole call here so
    # nothing about notifying can affect this endpoint's response.
    try:
        names_result = await db.execute(
            select(User.id, User.full_name).where(User.id.in_([sender_id, receiver_id]))
        )
        full_name_by_user_id = {uid: name for uid, name in names_result.all()}

        await notify(
            sender_id,
            "TX_SENT",
            {
                "amount": str(transaction.amount),
                "currency": transaction.currency.value,
                "transaction_id": transaction.id,
                "full_name": full_name_by_user_id.get(sender_id, "there"),
            },
            db=db,
        )
        await notify(
            receiver_id,
            "TX_RECEIVED",
            {
                "amount": str(transaction.amount),
                "currency": transaction.currency.value,
                "transaction_id": transaction.id,
                "full_name": full_name_by_user_id.get(receiver_id, "there"),
            },
            db=db,
        )
    except Exception:
        logger.exception(
            "Failed to send transfer notifications for transaction_id=%s "
            "(transfer itself already succeeded)",
            transaction.id,
        )

    response = SendMoneyResponse(
        transaction_id=transaction.id,
        status=transaction.status.value,
        amount=transaction.amount,
        currency=transaction.currency.value,
        sender_id=sender_id,
        receiver_id=receiver_id,
        fraud_score=None,
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
VALID_TRANSACTION_TYPES = {"send", "receive", "topup", "bill", "exchange", "adjustment", "reversal"}
TYPES_NOT_YET_SUPPORTED = {"bill"}


def _derive_transaction_type(transaction: Transaction, user_id: int) -> str:
    if transaction.sender_id == transaction.receiver_id:
        if transaction.category == "Exchange":
            return "exchange"
        if transaction.category == "Bills":
            return "bill"
        if transaction.category == "Adjustment":
            return "adjustment"
        if transaction.category == "Reversal":
            return "reversal"
        return "topup"
    return "send" if transaction.sender_id == user_id else "receive"


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
        # NBL-411: top-ups are stored as sender_id == receiver_id and are not
        # spend -- exclude them from the monthly spend summary.
        .where(Transaction.sender_id != Transaction.receiver_id)
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


@router.get("/statement", response_model=StatementResponse)
async def get_transaction_statement(
    month: str = Query(..., description="Format YYYY-MM, e.g. 2026-07"),
    format: Literal["csv", "pdf"] = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    DEVATTECH-94: monthly account statement (CSV or PDF), uploaded to
    S3 under the existing bucket's "neobank-statements/{user_id}/
    {month}.{ext}" key prefix, presigned URL returned. Reuses
    app/core/storage.py as-is -- no new boto3 code; storage.upload_file
    already applies server-side encryption automatically.

    Registered before "/{transaction_id}" -- same route-ordering
    requirement already documented above for "/summary".

    Generation is synchronous, in-memory, CPU-only (stdlib csv /
    reportlab) -- meets the ticket's "<1s, no Celery" requirement.
    storage.upload_file/get_presigned_url are SYNCHRONOUS functions
    (confirmed from the current file -- no async/await in
    app/core/storage.py); calling either directly here would block the
    event loop during real S3 network I/O. Wrapped in
    loop.run_in_executor, same pattern already established in
    admin.py's get_kyc_queue for this exact same storage helper.

    Balance reconstruction (app/services/statement_generation.py) is
    guaranteed exact only for a currency with no pre-ledger-fix
    Exchange/Reversal/Adjustment rows (missing exchange_leg/
    ledger_direction) -- see that module's docstring. Such a currency's
    opening/closing balance is omitted from the generated file (never
    silently defaulted to 0), with its transaction rows still shown.
    This is entirely internal to the generated file's content -- the
    API response contract below is unaffected either way.
    """
    try:
        year, month_num = parse_summary_month(month)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month must be in YYYY-MM format",
        )

    user_id = int(current_user.id)
    month_start = date(year, month_num, 1)
    month_end = date(year + 1, 1, 1) if month_num == 12 else date(year, month_num + 1, 1)

    currency_statements = await reconstruct_currency_statements(db, user_id, month_start, month_end)

    if format == "csv":
        file_bytes = generate_csv_bytes(month, currency_statements)
        content_type = "text/csv"
        ext = "csv"
    else:
        file_bytes = generate_pdf_bytes(month, currency_statements)
        content_type = "application/pdf"
        ext = "pdf"

    s3_key = f"neobank-statements/{user_id}/{month}.{ext}"

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(upload_file, file_bytes, s3_key, extra_args={"ContentType": content_type}),
    )
    presigned_url = await loop.run_in_executor(None, partial(get_presigned_url, s3_key))

    return StatementResponse(month=month, s3_key=s3_key, presigned_url=presigned_url)


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

    transaction_type = _derive_transaction_type(transaction, user_id)
    is_self_transaction = transaction.sender_id == transaction.receiver_id
    is_sender = transaction.sender_id == user_id

    if is_self_transaction:
        counterparty = None
    else:
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
        type=transaction_type,
        amount=transaction.amount,
        currency=transaction.currency.value,
        counterparty_name=counterparty.full_name if counterparty else None,
        category=transaction.category,
        fraud_score=transaction.fraud_score,
        rule_triggered=None,
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
    elif type == "topup":
        filters.append(Transaction.category == "TopUp")
    elif type == "exchange":
        filters.append(Transaction.category == "Exchange")
    elif type == "adjustment":
        filters.append(Transaction.category == "Adjustment")
    elif type == "reversal":
        filters.append(Transaction.category == "Reversal")

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

    counterparty_ids = {
        (tx.receiver_id if tx.sender_id == user_id else tx.sender_id) for tx in transactions
    }
    users_by_id = {}
    if counterparty_ids:
        users_result = await db.execute(select(User).where(User.id.in_(counterparty_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    items = []
    for tx in transactions:
        transaction_type = _derive_transaction_type(tx, user_id)
        is_self_transaction = tx.sender_id == tx.receiver_id
        is_sender = tx.sender_id == user_id
        counterparty = None if is_self_transaction else users_by_id.get(tx.receiver_id if is_sender else tx.sender_id)

        items.append(
            TransactionListItem(
                id=tx.id,
                type=transaction_type,
                amount=tx.amount,
                currency=tx.currency.value,
                counterparty_name=counterparty.full_name if counterparty else None,
                category=tx.category,
                fraud_score=tx.fraud_score,
                rule_triggered=None,
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
