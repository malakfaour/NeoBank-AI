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
import os

import joblib
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "ml_models")
ISOLATION_FOREST_PATH = os.path.join(MODEL_DIR, "isolation_forest.pkl")
ISOLATION_FOREST_STATS_PATH = os.path.join(MODEL_DIR, "isolation_forest_stats.json")

_isolation_forest_model = None
_isolation_forest_stats = None


def _load_isolation_forest():
    global _isolation_forest_model, _isolation_forest_stats
    if _isolation_forest_model is None:
        _isolation_forest_model = joblib.load(ISOLATION_FOREST_PATH)
        with open(ISOLATION_FOREST_STATS_PATH) as f:
            _isolation_forest_stats = json.load(f)
    return _isolation_forest_model, _isolation_forest_stats


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

def score_with_xgboost(db: Session, transaction: Transaction) -> float:
    """
    DEVATTECH-75: real XGBoost inference, replacing the previous stub.
    ...
    """
    pipeline, _ = _load_xgb_model()