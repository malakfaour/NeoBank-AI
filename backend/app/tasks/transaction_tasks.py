import logging

from app.celery_app import celery_app
from app.db.sync_session import SyncSessionLocal
from app.models.transaction import Transaction, TransactionStatus
from app.services.audit_log import append_audit_sync
from app.services.fraud_rules import check_fraud_rules_sync
from app.services.fraud_scoring import (
    FRAUD_FLAG_THRESHOLD,
    get_sender_tx_count,
    score_with_isolation_forest,
    score_with_xgboost,
)
from app.tasks.categorization_tasks import categorize_transaction

logger = logging.getLogger(__name__)

COLD_START_TX_THRESHOLD = 5


@celery_app.task(name="app.tasks.transaction_tasks.ping")
def ping():
    return "pong"


@celery_app.task(name="app.tasks.transaction_tasks.score_transaction")
def score_transaction(transaction_id):
    """
    DEVATTECH-84/87: persist fraud scoring and rule-check outcomes.

    Users with fewer than COLD_START_TX_THRESHOLD prior transactions don't
    have enough history for XGBoost (NBL-109) to score meaningfully, so an
    Isolation Forest trained on synthetic data is used instead. Users past
    the threshold fall through to the real XGBoost model path.

    Uses a dedicated sync DB session (app.db.sync_session) rather than the
    app's async engine, since Celery tasks run synchronously and asyncpg
    connections are bound to the event loop they were created on.
    """
    with SyncSessionLocal() as db:
        transaction = db.get(Transaction, transaction_id)
        if transaction is None:
            logger.warning("Transaction %s not found for scoring", transaction_id)
            return {"score": 0.0, "flagged": False, "model": None}

        actor_id = transaction.sender_id

        try:
            tx_count = get_sender_tx_count(db, transaction.sender_id, transaction.id)

            if tx_count < COLD_START_TX_THRESHOLD:
                model_name = "isolation_forest"
                score = score_with_isolation_forest(db, transaction)
            else:
                model_name = "xgboost"
                score = score_with_xgboost(db, transaction)

            rule_result = check_fraud_rules_sync(db, transaction)
            flagged = score >= FRAUD_FLAG_THRESHOLD or rule_result.triggered

            transaction.fraud_score = score
            transaction.scoring_model = model_name
            transaction.rule_triggered = rule_result.triggered
            transaction.status = (
                TransactionStatus.flagged if flagged else TransactionStatus.completed
            )
            db.commit()
            db.refresh(transaction)

            if transaction.status == TransactionStatus.completed:
                try:
                    categorize_transaction.delay(transaction.id)
                except Exception:
                    logger.exception(
                        "Categorization enqueue failed for transaction %s",
                        transaction.id,
                    )

            append_audit_sync(
                db,
                transaction_id=transaction.id,
                action="fraud_scored",
                actor_id=actor_id,
                metadata={
                    "fraud_score": transaction.fraud_score,
                    "rule_triggered": transaction.rule_triggered,
                    "rule_name": rule_result.rule_name,
                },
            )
            if flagged:
                append_audit_sync(
                    db,
                    transaction_id=transaction.id,
                    action="status_changed",
                    actor_id=actor_id,
                    metadata={
                        "from": TransactionStatus.completed.value,
                        "to": TransactionStatus.flagged.value,
                    },
                )
        except Exception:
            db.rollback()
            logger.exception("Fraud scoring failed for transaction %s", transaction_id)

            transaction = db.get(Transaction, transaction_id)
            if transaction is None:
                return {"score": 0.0, "flagged": True, "model": None}

            if transaction.status != TransactionStatus.flagged:
                previous_status = transaction.status
                transaction.status = TransactionStatus.flagged
                db.commit()
                if previous_status == TransactionStatus.completed:
                    append_audit_sync(
                        db,
                        transaction_id=transaction.id,
                        action="status_changed",
                        actor_id=actor_id,
                        metadata={
                            "from": TransactionStatus.completed.value,
                            "to": TransactionStatus.flagged.value,
                        },
                    )
            return {
                "score": transaction.fraud_score or 0.0,
                "flagged": True,
                "model": transaction.scoring_model,
            }

    logger.info(
        "Transaction %s scored %.4f by %s (sender tx_count=%d, rule_triggered=%s)",
        transaction_id, score, model_name, tx_count, rule_result.triggered,
    )

    return {"score": score, "flagged": flagged, "model": model_name}
