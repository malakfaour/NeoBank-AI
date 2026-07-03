import logging

from app.celery_app import celery_app
from app.db.sync_session import SyncSessionLocal
from app.models.transaction import Transaction
from app.services.fraud_scoring import (
    get_sender_tx_count,
    score_with_isolation_forest,
    score_with_xgboost,
)

logger = logging.getLogger(__name__)

COLD_START_TX_THRESHOLD = 5


@celery_app.task(name="app.tasks.transaction_tasks.ping")
def ping():
    return "pong"


@celery_app.task(name="app.tasks.transaction_tasks.score_transaction")
def score_transaction(transaction_id):
    """
    DEVATTECH-84: cold-start-aware fraud scoring.

    Users with fewer than COLD_START_TX_THRESHOLD prior transactions don't
    have enough history for XGBoost (NBL-109) to score meaningfully, so an
    Isolation Forest trained on synthetic data is used instead. Users past
    the threshold fall through to XGBoost -- currently a stub, since
    NBL-109 hasn't been built yet (see app/services/fraud_scoring.py).

    Uses a dedicated sync DB session (app.db.sync_session) rather than the
    app's async engine, since Celery tasks run synchronously and asyncpg
    connections are bound to the event loop they were created on.
    """
    with SyncSessionLocal() as db:
        transaction = db.get(Transaction, transaction_id)
        if transaction is None:
            logger.warning("Transaction %s not found for scoring", transaction_id)
            return {"score": 0.0, "flagged": False, "model": None}

        tx_count = get_sender_tx_count(db, transaction.sender_id, transaction.id)

        if tx_count < COLD_START_TX_THRESHOLD:
            model_name = "isolation_forest"
            score = score_with_isolation_forest(db, transaction)
        else:
            model_name = "xgboost"
            score = score_with_xgboost(db, transaction)

    logger.info(
        "Transaction %s scored %.4f by %s (sender tx_count=%d)",
        transaction_id, score, model_name, tx_count,
    )

    return {"score": score, "flagged": score >= 0.75, "model": model_name}
