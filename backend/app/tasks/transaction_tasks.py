import logging
import asyncio

from app.celery_app import celery_app
from app.db.sync_session import SyncSessionLocal
from app.models.transaction import Transaction
from app.services.fraud_scoring import (
    get_sender_tx_count,
    score_with_isolation_forest,
    score_with_xgboost,
)

FRAUD_FLAG_THRESHOLD = 0.75

logger = logging.getLogger(__name__)

COLD_START_TX_THRESHOLD = 5


@celery_app.task(name="app.tasks.transaction_tasks.ping")
def ping():
    return "pong"


@celery_app.task(name="app.tasks.transaction_tasks.score_transaction")
def score_transaction(transaction_id):
    with SyncSessionLocal() as db:
        try:
            transaction = db.get(Transaction, transaction_id)

            if transaction is None:
                logger.warning("Transaction %s not found for scoring", transaction_id)
                return

            # -----------------------------
            # ML SCORING
            # -----------------------------
            tx_count = get_sender_tx_count(
                db, transaction.sender_id, transaction.id
            )

            if tx_count < COLD_START_TX_THRESHOLD:
                model_name = "isolation_forest"
                score = score_with_isolation_forest(db, transaction)
            else:
                model_name = "xgboost"
                score = score_with_xgboost(db, transaction)

            # -----------------------------
            # FRAUD RULE ENGINE
            # -----------------------------
            from app.services.fraud_rules import check_fraud_rules

            rule_result = asyncio.run(check_fraud_rules(transaction, db))

            rule_triggered = rule_result.get("triggered", False)
            rule_name = rule_result.get("rule_name")

            # -----------------------------
            # DECISION LOGIC
            # -----------------------------
            is_flagged = (
                score >= FRAUD_FLAG_THRESHOLD or rule_triggered
            )

            transaction.fraud_score = score
            transaction.scoring_model = model_name
            transaction.rule_triggered = rule_triggered
            transaction.status = "flagged" if is_flagged else "completed"

            # -----------------------------
            # AUDIT LOGS
            # -----------------------------
            from app.services.audit_log import append_audit

            asyncio.run(
                append_audit(
                    transaction.id,
                    "fraud_scored",
                    {
                        "fraud_score": score,
                        "rule_triggered": rule_triggered,
                        "rule_name": rule_name,
                    },
                )
            )

            if is_flagged:
                asyncio.run(
                    append_audit(
                        transaction.id,
                        "status_changed",
                        {"from": "completed", "to": "flagged"},
                    )
                )

            db.commit()

            logger.info(
                "Transaction %s scored %.4f by %s (flagged=%s)",
                transaction_id,
                score,
                model_name,
                is_flagged,
            )

        except Exception as e:
            logger.exception("Fraud scoring failed for tx %s", transaction_id)

            transaction = db.get(Transaction, transaction_id)

            if transaction:
                transaction.status = "manual_review"
                db.commit()

            raise