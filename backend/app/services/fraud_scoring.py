"""
DEVATTECH-84: fraud scoring for score_transaction.

Two entry points, both with the same (db, transaction) -> float signature
so score_transaction can call either one interchangeably:

  - score_with_isolation_forest: cold-start model (< 5 prior transactions),
    trained on synthetic data (see ml/fraud/train_isolation_forest.py).
  - score_with_xgboost: placeholder for M1's NBL-109. Not implemented yet
    -- XGBoost model/training code doesn't exist in the repo as of this
    ticket. Returns a safe non-flagged default until NBL-109 lands; M1
    should replace this function's internals, keeping the same signature.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import joblib
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "ml_models")
ISOLATION_FOREST_PATH = os.path.join(MODEL_DIR, "isolation_forest.pkl")
ISOLATION_FOREST_STATS_PATH = os.path.join(MODEL_DIR, "isolation_forest_stats.json")
FRAUD_XGB_PATH = os.path.join(MODEL_DIR, "fraud_xgb.pkl")
FRAUD_XGB_STATS_PATH = os.path.join(MODEL_DIR, "fraud_xgb_stats.json")

_isolation_forest_model = None
_isolation_forest_stats = None
_xgb_pipeline = None
_xgb_stats = None

logger = logging.getLogger(__name__)


def _load_isolation_forest():
    global _isolation_forest_model, _isolation_forest_stats
    if _isolation_forest_model is None:
        _isolation_forest_model = joblib.load(ISOLATION_FOREST_PATH)
        with open(ISOLATION_FOREST_STATS_PATH) as f:
            _isolation_forest_stats = json.load(f)
    return _isolation_forest_model, _isolation_forest_stats


def _load_xgb_model():
    """
    DEVATTECH-75: lazy-load + module-level cache for the XGBoost fraud
    pipeline, mirroring _load_isolation_forest()'s pattern.

    fraud_xgb.pkl contains a single sklearn Pipeline(StandardScaler,
    XGBClassifier) -- preprocessing and model together, so there's no
    separate scaler object to load here.

    Safe fallback: if the artifact doesn't exist yet (e.g. this code has
    shipped but train_fraud_xgb.py hasn't been run), log a warning and
    return (None, None) instead of raising. score_with_xgboost() below
    checks for this and returns a safe non-flagged score rather than
    crashing score_transaction for every non-cold-start user.
    """
    global _xgb_pipeline, _xgb_stats
    if _xgb_pipeline is None:
        try:
            _xgb_pipeline = joblib.load(FRAUD_XGB_PATH)
            with open(FRAUD_XGB_STATS_PATH) as f:
                _xgb_stats = json.load(f)
        except FileNotFoundError:
            logger.warning(
                "fraud_xgb.pkl not found at %s -- XGBoost fraud scoring is "
                "unavailable until train_fraud_xgb.py has been run. "
                "Falling back to a safe non-flagged score.",
                FRAUD_XGB_PATH,
            )
            return None, None
    return _xgb_pipeline, _xgb_stats


def get_sender_tx_count(db: Session, sender_id: int, exclude_transaction_id: int) -> int:
    """Count of the sender's PRIOR transactions, excluding the one currently
    being scored (it was already committed before scoring runs)."""
    result = db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.sender_id == sender_id,
            Transaction.id != exclude_transaction_id,
        )
    )
    return result.scalar_one()


def get_sender_tx_count_30d(db: Session, sender_id: int, exclude_transaction_id: int) -> int:
    """
    DEVATTECH-75: count of the sender's transactions in the trailing 30
    days, excluding the one currently being scored. Separate from
    get_sender_tx_count() above (all-time count, used for the cold-start
    gate) -- different window feeding a different model.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.sender_id == sender_id,
            Transaction.id != exclude_transaction_id,
            Transaction.created_at >= cutoff,
        )
    )
    return result.scalar_one()


def _compute_features(db: Session, transaction: Transaction) -> list[float]:
    _, stats = _load_isolation_forest()

    amount = float(transaction.amount)
    amount_zscore = (amount - stats["amount_mean"]) / stats["amount_std"]

    hour_of_day = transaction.created_at.hour

    result = db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.sender_id == transaction.sender_id,
            Transaction.receiver_id == transaction.receiver_id,
            Transaction.id != transaction.id,
        )
    )
    prior_to_this_receiver = result.scalar_one()
    is_new_recipient = 1 if prior_to_this_receiver == 0 else 0

    result = db.execute(
        select(Transaction.currency, func.count())
        .where(
            Transaction.sender_id == transaction.sender_id,
            Transaction.id != transaction.id,
        )
        .group_by(Transaction.currency)
        .order_by(func.count().desc())
    )
    rows = result.all()
    if rows:
        most_common_currency = rows[0][0]
        currency_flag = 0 if transaction.currency == most_common_currency else 1
    else:
        # No prior history to compare against -- nothing to flag as a
        # mismatch yet.
        currency_flag = 0

    return [amount_zscore, hour_of_day, is_new_recipient, currency_flag]


def score_with_isolation_forest(db: Session, transaction: Transaction) -> float:
    model, _ = _load_isolation_forest()
    features = _compute_features(db, transaction)

    # decision_function: higher = more normal, lower/negative = more
    # anomalous (roughly in [-0.5, 0.5]). Invert and clip to 0..1 so higher
    # fraud_score = more suspicious, matching the existing
    # FRAUD_FLAG_THRESHOLD contract in transactions.py.
    raw_score = model.decision_function([features])[0]
    fraud_score = max(0.0, min(1.0, 0.5 - raw_score))
    return fraud_score


def _compute_xgb_features(db: Session, transaction: Transaction) -> list[float]:
    """
    DEVATTECH-75: feature vector for the XGBoost model. Separate from the
    isolation forest's _compute_features() above -- different model,
    different feature set, kept independent so a future change to one
    model's features can't silently affect the other.

    Feature order MUST match fraud_xgb_stats.json's "feature_order" and
    the order used in train_fraud_xgb.py.
    """
    amount = float(transaction.amount)

    result = db.execute(
        select(func.avg(Transaction.amount))
        .where(
            Transaction.sender_id == transaction.sender_id,
            Transaction.id != transaction.id,
        )
    )
    sender_avg_amount = result.scalar_one()
    if sender_avg_amount is None or float(sender_avg_amount) == 0.0:
        # No prior history (or a zero average, which shouldn't happen in
        # practice) -- fall back to a neutral ratio of 1.0 rather than
        # divide by zero.
        amount_to_user_avg_ratio = 1.0
    else:
        amount_to_user_avg_ratio = amount / float(sender_avg_amount)

    result = db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.sender_id == transaction.sender_id,
            Transaction.receiver_id == transaction.receiver_id,
            Transaction.id != transaction.id,
        )
    )
    prior_to_this_receiver = result.scalar_one()
    is_new_recipient = 1 if prior_to_this_receiver == 0 else 0

    hour_of_day = transaction.created_at.hour
    day_of_week = transaction.created_at.weekday()  # Monday=0 .. Sunday=6

    sender_tx_count_30d = get_sender_tx_count_30d(db, transaction.sender_id, transaction.id)

    result = db.execute(
        select(Transaction.currency, func.count())
        .where(
            Transaction.sender_id == transaction.sender_id,
            Transaction.id != transaction.id,
        )
        .group_by(Transaction.currency)
        .order_by(func.count().desc())
    )
    rows = result.all()
    if rows:
        most_common_currency = rows[0][0]
        currency_match = 1 if transaction.currency == most_common_currency else 0
    else:
        # No prior history -- nothing to compare against. Treat as a match
        # (neutral) rather than a mismatch, since there's no basis to flag it.
        currency_match = 1

    return [
        amount,
        amount_to_user_avg_ratio,
        is_new_recipient,
        hour_of_day,
        day_of_week,
        sender_tx_count_30d,
        currency_match,
    ]


def score_with_xgboost(db: Session, transaction: Transaction) -> float:
    """
    DEVATTECH-75: real XGBoost inference, replacing the previous stub.

    fraud_xgb.pkl is a single sklearn Pipeline(StandardScaler,
    XGBClassifier) -- scaling happens inside predict_proba(), so raw
    feature values are passed in directly (same convention as
    score_with_isolation_forest(), which also passes model-ready features).

    Safe fallback: if the model artifact isn't available yet,
    _load_xgb_model() returns (None, None) instead of raising -- return a
    safe non-flagged score (0.0) instead of crashing. NOTE: the caller
    (app/tasks/transaction_tasks.py, out of scope for this ticket) still
    reports model="xgboost" in this case, since it decides the model name
    before calling this function -- it does not know a fallback occurred.
    """
    pipeline, _ = _load_xgb_model()
    if pipeline is None:
        return 0.0

    features = _compute_xgb_features(db, transaction)

    # predict_proba returns [[P(class=0), P(class=1)]]; class 1 = fraud.
    fraud_score = float(pipeline.predict_proba([features])[0][1])
    return fraud_score
