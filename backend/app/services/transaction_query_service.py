from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User


async def get_recent_transactions_for_user(
    user_id: int,
    db: AsyncSession,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Return the authenticated user's most recent transactions.

    Reused by the NBL-510 chatbot transaction tool.
    """
    safe_limit = max(1, min(limit, 100))

    result = await db.execute(
        select(Transaction)
        .where(
            or_(
                Transaction.sender_id == user_id,
                Transaction.receiver_id == user_id,
            )
        )
        .order_by(Transaction.created_at.desc())
        .limit(safe_limit)
    )

    transactions = result.scalars().all()

    counterparty_ids = {
        (
            transaction.receiver_id
            if transaction.sender_id == user_id
            else transaction.sender_id
        )
        for transaction in transactions
    }

    users_by_id: dict[int, User] = {}

    if counterparty_ids:
        users_result = await db.execute(
            select(User).where(
                User.id.in_(counterparty_ids)
            )
        )

        users_by_id = {
            user.id: user
            for user in users_result.scalars().all()
        }

    items: list[dict[str, Any]] = []

    for transaction in transactions:
        is_sender = transaction.sender_id == user_id

        counterparty_id = (
            transaction.receiver_id
            if is_sender
            else transaction.sender_id
        )

        counterparty = users_by_id.get(counterparty_id)

        items.append(
            {
                "id": transaction.id,
                "type": "send" if is_sender else "receive",
                "amount": float(transaction.amount),
                "currency": transaction.currency.value,
                "counterparty_name": (
                    counterparty.full_name
                    if counterparty
                    else None
                ),
                "category": transaction.category,
                "fraud_score": transaction.fraud_score,
                "status": transaction.status.value,
                "flagged": (
                    transaction.status
                    == TransactionStatus.flagged
                ),
                "created_at": transaction.created_at.isoformat(),
            }
        )

    return items