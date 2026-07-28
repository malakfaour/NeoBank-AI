"""
DEVATTECH-84: fraud scoring for score_transaction.

Two entry points, both with the same (db, transaction) -> float signature
so score_transaction can call either one interchangeably:

  - score_with_isolation_forest: cold-start model (< 5 prior transactions),
    trained on synthetic data (see ml/fraud/train_isolation_forest.py).
  - score_with_xgboost: real inference (DEVATTECH-75) using a trained
    sklearn Pipeline(StandardScaler, XGBClassifier) loaded from
    fraud_xgb.pkl via joblib. Used for users past the cold-start
    threshold. If fraud_xgb.pkl hasn't been generated yet (train_fraud_xgb.py
    not run), _load_xgb_model() logs a warning and returns (None, None),
    and score_with_xgboost() falls back to a safe non-flagged score (0.0)
    rather than raising.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import joblib
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.core.storage import download_file

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

# DEVATTECH-143: S3 fallback for the two relocated .pkl artifacts only.
# ISOLATION_FOREST_STATS_PATH / FRAUD_XGB_STATS_PATH stay locally
# git-tracked and untouched -- only these two paths were approved for
# relocation.

# Tracks which local paths have already had an S3 fetch attempted in this
# process, so a down/misconfigured S3 doesn't get re-hit on every single
# transaction scored -- one attempt per path per process, matching the
# existing module-level model-caching pattern below.
_s3_fetch_attempted: set[str] = set()


def _ensure_model_file_available(local_path: str, s3_key: str) -> None:
    """
    DEVATTECH-143: if local_path doesn't exist, attempt one S3 fetch into
    that exact same path before the caller's existing joblib.load() runs.

    s3_key is passed explicitly by the caller rather than looked up from
    local_path in a module-level dict -- a path-keyed dict would silently
    stop matching (and silently skip the S3 fetch) whenever local_path is
    monkeypatched to a different value, e.g. in tests. Passing it
    explicitly avoids that fragility entirely.

    Best-effort only: any failure (S3 unavailable, credentials missing,
    key not found) is logged and swallowed here -- the caller's existing
    load code then runs exactly as it does today when the file is
    genuinely absent. This function does NOT change either loader's
    existing error-handling behavior:
      - _load_isolation_forest(): joblib.load() still raises
        FileNotFoundError uncaught if the file is still missing after
        this best-effort fetch, unchanged from current behavior.
      - _load_xgb_model(): its existing try/except FileNotFoundError ->
        (None, None) fallback still applies unchanged.

    This is purely a "give the local file a chance to exist first" step,
    not a new failure mode.
    """
    if local_path in _s3_fetch_attempted:
        return
    _s3_fetch_attempted.add(local_path)

    if os.path.exists(local_path):
        return

    try:
        download_file(s3_key, local_path)
        logger.info("Fetched %s from S3 key %s", local_path, s3_key)
    except Exception:
        logger.warning(
            "Could not fetch %s from S3 (key=%s) -- falling back to "
            "local-file-missing behavior.",
            local_path,
            s3_key,
            exc_info=True,
        )

# DEVATTECH-90: justified from ml/fraud/tune_threshold.py's holdout
# evaluation (evaluation-only pipeline, never touched fraud_xgb.pkl) --
# precision=0.9909, recall=0.9083, F1=0.9478, flagged_rate=4.58% at this
# threshold (max-F1 among 14 candidates swept 0.30-0.95). Full sweep
# results: ml/fraud/threshold_tuning.json.
FRAUD_FLAG_THRESHOLD = 0.45

# The hour_of_day feature is meant to represent local time-of-day risk
# ("is this a normal hour to be transacting"), not an arbitrary UTC
# offset. transaction.created_at is stored as TIMESTAMPTZ (UTC) --
# same Asia/Beirut convention already used correctly elsewhere in this
# codebase (see market_hours.py's MARKET_TIMEZONE).
FRAUD_TIMEZONE = "Asia/Beirut"


def _load_isolation_forest():
    global _isolation_forest_model, _isolation_forest_stats
    if _isolation_forest_model is None:
        _ensure_model_file_available(ISOLATION_FOREST_PATH, "ml-models/fraud/isolation_forest.pkl")
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
        _ensure_model_file_available(FRAUD_XGB_PATH, "ml-models/fraud/fraud_xgb.pkl")
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
            # NBL-411: exclude self-transfers (top-ups) from the cold-start
            # transaction count -- otherwise top-ups graduate a user from
            # Isolation Forest to XGBoost scoring early.
            Transaction.sender_id != Transaction.receiver_id,
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
            # NBL-411: exclude self-transfers (top-ups) -- same reasoning as
            # get_sender_tx_count above.
            Transaction.sender_id != Transaction.receiver_id,
            Transaction.id != exclude_transaction_id,
            Transaction.created_at >= cutoff,
        )
    )
    return result.scalar_one()


def _compute_features(db: Session, transaction: Transaction) -> list[float]:
    _, stats = _load_isolation_forest()

    amount = float(transaction.amount)
    amount_zscore = (amount - stats["amount_mean"]) / stats["amount_std"]

    local_created_at = transaction.created_at.astimezone(ZoneInfo(FRAUD_TIMEZONE))
    hour_of_day = local_created_at.hour

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
    # fraud_score = more suspicious, matching the FRAUD_FLAG_THRESHOLD
    # contract defined in this module and consumed by
    # app/tasks/transaction_tasks.py's score_transaction task.
    raw_score = model.decision_function([features])[0]
    fraud_score = float(max(0.0, min(1.0, 0.5 - raw_score)))
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
            # NBL-411: exclude self-transfers (top-ups) -- otherwise a large
            # top-up inflates this user's average and skews the ratio feature.
            Transaction.sender_id != Transaction.receiver_id,
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

    hour_of_day = transaction.created_at.astimezone(ZoneInfo(FRAUD_TIMEZONE)).hour
    day_of_week = transaction.created_at.astimezone(ZoneInfo(FRAUD_TIMEZONE)).weekday()  # Monday=0 .. Sunday=6

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
    