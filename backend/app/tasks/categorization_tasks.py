import logging

import httpx
from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.bill_payment import BillPayment
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3-8b"

CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Entertainment",
    "Transfer",
    "TopUp",
    "Exchange",
    "Other",
)
VALID_CATEGORIES = set(CATEGORIES)


def _is_bill_transaction(db, transaction_id: int) -> bool:
    result = db.execute(
        select(BillPayment.id)
        .where(BillPayment.transaction_id == transaction_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _transaction_text(transaction: Transaction) -> str:
    return (
        f"Transfer of {transaction.amount} "
        f"{transaction.currency.value} to {transaction.receiver.full_name}"
    )


def _call_groq(transaction_text: str) -> str:
    prompt = (
        "Classify this bank transaction into exactly one category. "
        f"Categories: {', '.join(CATEGORIES)}. "
        f"Transaction: {transaction_text}. "
        "Respond only with the category name."
    )

    payload = {
        "model": GROQ_MODEL,
        "max_tokens": 100,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            GROQ_API_URL,
            json=payload,
            headers=headers,
        )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


@celery_app.task(
    name="app.tasks.categorization_tasks.categorize_transaction"
)
def categorize_transaction(transaction_id: int) -> str | None:
    """
    Categorize a completed transaction and persist transactions.category.

    Bill payments are always categorized as Bills without calling Groq.
    Unexpected Groq responses or Groq failures fall back to Other.
    """
    with SyncSessionLocal() as db:
        transaction = db.get(Transaction, transaction_id)

        if transaction is None:
            logger.warning(
                "Transaction %s not found for categorization",
                transaction_id,
            )
            return None

        if _is_bill_transaction(db, transaction.id):
            category = "Bills"
        else:
            try:
                raw_category = _call_groq(
                    _transaction_text(transaction)
                )
            except Exception:
                logger.warning(
                    "Groq categorization failed for transaction %s; "
                    "defaulting to Other",
                    transaction_id,
                    exc_info=True,
                )
                raw_category = "Other"

            category = (
                raw_category.strip()
                if isinstance(raw_category, str)
                else ""
            )

            if category not in VALID_CATEGORIES:
                category = "Other"

        transaction.category = category
        db.commit()

        logger.info(
            "Transaction %s categorized as %s",
            transaction_id,
            category,
        )

        return category
