"""
DEVATTECH-75 tests.

app.services.fraud_scoring does NOT import app.db.session (it only takes
a SQLAlchemy Session as a function parameter -- it never constructs an
engine itself), so this module is safe to import directly under the test
environment without triggering the async-engine issue seen with
app.api.v1.endpoints.transactions in earlier tickets.

That also means one real (non-mocked-away) behavior is testable here: the
missing-model-artifact fallback in score_with_xgboost(). That code path
returns before ever touching its `db` or `transaction` arguments, so it
can be exercised with db=None / transaction=None -- no DB, no fixtures.

What's NOT covered here, and why: _compute_xgb_features() and the
"happy path" through score_with_xgboost() (real model loaded, real
features computed) both need actual Transaction rows in a database and,
for the "happy path" specifically, an actual fraud_xgb.pkl on disk
(produced by running ml/fraud/train_fraud_xgb.py, which requires xgboost
-- not available in this sandbox, per the earlier flagged limitation).

TODO: once there's a Postgres-backed DB fixture AND a trained
fraud_xgb.pkl available in the test environment:
  - test_compute_xgb_features_returns_correct_length_and_order
  - test_compute_xgb_features_new_recipient_flag
  - test_compute_xgb_features_amount_to_avg_ratio_no_history_fallback
  - test_get_sender_tx_count_30d_excludes_older_transactions
  - test_score_with_xgboost_happy_path_returns_value_in_0_1_range
"""
import importlib

import pytest

from app.services import fraud_scoring


def test_score_with_xgboost_missing_model_returns_safe_default(monkeypatch, tmp_path):
    """
    Core safety requirement: if fraud_xgb.pkl doesn't exist, scoring must
    not crash -- it should log a warning and return 0.0.
    """
    # Force a clean cache state and point at a path that can't exist.
    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(tmp_path / "does_not_exist.pkl"))

    # score_with_xgboost returns before touching db/transaction when the
    # model is missing, so None is safe to pass here.
    score = fraud_scoring.score_with_xgboost(db=None, transaction=None)

    assert score == 0.0


def test_load_xgb_model_missing_returns_none_none(monkeypatch, tmp_path):
    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(tmp_path / "does_not_exist.pkl"))

    pipeline, stats = fraud_scoring._load_xgb_model()

    assert pipeline is None
    assert stats is None


def test_load_xgb_model_missing_logs_warning(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(tmp_path / "does_not_exist.pkl"))

    with caplog.at_level("WARNING"):
        fraud_scoring._load_xgb_model()

    assert any("fraud_xgb.pkl not found" in record.message for record in caplog.records)


def test_isolation_forest_paths_untouched_by_xgb_additions():
    """
    Sanity check that this ticket's additions didn't change the existing
    isolation-forest constants -- guards against a future accidental edit,
    not a functional test of the isolation forest itself.
    """
    assert fraud_scoring.ISOLATION_FOREST_PATH.endswith("isolation_forest.pkl")
    assert fraud_scoring.ISOLATION_FOREST_STATS_PATH.endswith("isolation_forest_stats.json")


def test_fraud_xgb_paths_point_to_expected_filenames():
    assert fraud_scoring.FRAUD_XGB_PATH.endswith("fraud_xgb.pkl")
    assert fraud_scoring.FRAUD_XGB_STATS_PATH.endswith("fraud_xgb_stats.json")


def test_train_fraud_xgb_feature_order_matches_ticket_spec():
    """
    Confirms FEATURE_ORDER in the training script matches this ticket's
    required feature list, in the specified order. Guards against the
    training script and _compute_xgb_features() silently drifting apart.

    Skipped if xgboost isn't installed in this environment (the training
    script imports it at module level) -- this test still runs fine in a
    real dev/CI environment where xgboost is a listed dependency.
    """
    xgboost = pytest.importorskip("xgboost")
    del xgboost  # only used to trigger the skip; not needed further

    train_module = importlib.import_module("ml.fraud.train_fraud_xgb")

    assert train_module.FEATURE_ORDER == [
        "amount",
        "amount_to_user_avg_ratio",
        "is_new_recipient",
        "hour_of_day",
        "day_of_week",
        "sender_tx_count_30d",
        "currency_match",
    ]
    