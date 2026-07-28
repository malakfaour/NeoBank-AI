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
import json

import joblib
import pytest

from app.services import fraud_scoring


@pytest.fixture(autouse=True)
def _reset_s3_fetch_state(monkeypatch):
    """DEVATTECH-143: reset the single-attempt-per-process S3 fetch guard
    before every test in this file, so tests don't leak state."""
    monkeypatch.setattr(fraud_scoring, "_s3_fetch_attempted", set())


def test_score_with_xgboost_missing_model_returns_safe_default(monkeypatch, tmp_path):
    """
    Core safety requirement: if fraud_xgb.pkl doesn't exist, scoring must
    not crash -- it should log a warning and return 0.0.

    DEVATTECH-143: download_file mocked to raise -- must never reach
    real S3/network in tests (ENGINEERING_RULES section 6).
    """
    # Force a clean cache state and point at a path that can't exist.
    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(tmp_path / "does_not_exist.pkl"))
    monkeypatch.setattr(
        fraud_scoring,
        "download_file",
        lambda source_key, destination_path: (_ for _ in ()).throw(
            FileNotFoundError("mocked: S3 object not found")
        ),
    )

    # score_with_xgboost returns before touching db/transaction when the
    # model is missing, so None is safe to pass here.
    score = fraud_scoring.score_with_xgboost(db=None, transaction=None)

    assert score == 0.0


def test_load_xgb_model_missing_returns_none_none(monkeypatch, tmp_path):
    """DEVATTECH-143: download_file mocked to raise -- see above."""
    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(tmp_path / "does_not_exist.pkl"))
    monkeypatch.setattr(
        fraud_scoring,
        "download_file",
        lambda source_key, destination_path: (_ for _ in ()).throw(
            FileNotFoundError("mocked: S3 object not found")
        ),
    )

    pipeline, stats = fraud_scoring._load_xgb_model()

    assert pipeline is None
    assert stats is None


def test_load_xgb_model_missing_logs_warning(monkeypatch, tmp_path, caplog):
    """DEVATTECH-143: download_file mocked to raise -- see above."""
    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(tmp_path / "does_not_exist.pkl"))
    monkeypatch.setattr(
        fraud_scoring,
        "download_file",
        lambda source_key, destination_path: (_ for _ in ()).throw(
            FileNotFoundError("mocked: S3 object not found")
        ),
    )

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
    


# --- DEVATTECH-143: S3 fallback tests ---
# download_file is mocked at fraud_scoring's own namespace -- never
# reaches app.core.storage or boto3.


def test_ensure_model_file_available_skips_download_when_file_exists(monkeypatch, tmp_path):
    """download_file must NEVER be called when the local file already exists."""
    existing_file = tmp_path / "already_here.pkl"
    existing_file.write_bytes(b"not a real model, just needs to exist")

    def _fail_if_called(source_key, destination_path):
        raise AssertionError("download_file must not be called when the local file exists")

    monkeypatch.setattr(fraud_scoring, "download_file", _fail_if_called)

    fraud_scoring._ensure_model_file_available(str(existing_file), "ml-models/fraud/whatever.pkl")


def test_ensure_model_file_available_calls_download_when_file_missing(monkeypatch, tmp_path):
    missing_path = str(tmp_path / "missing.pkl")
    calls = []

    def _record_call(source_key, destination_path):
        calls.append((source_key, destination_path))
        raise FileNotFoundError("mocked: S3 object not found")

    monkeypatch.setattr(fraud_scoring, "download_file", _record_call)

    fraud_scoring._ensure_model_file_available(missing_path, "ml-models/fraud/whatever.pkl")

    assert calls == [("ml-models/fraud/whatever.pkl", missing_path)]


def test_ensure_model_file_available_does_not_retry_after_failure(monkeypatch, tmp_path):
    missing_path = str(tmp_path / "missing.pkl")
    call_count = {"count": 0}

    def _count_and_fail(source_key, destination_path):
        call_count["count"] += 1
        raise FileNotFoundError("mocked: S3 object not found")

    monkeypatch.setattr(fraud_scoring, "download_file", _count_and_fail)

    fraud_scoring._ensure_model_file_available(missing_path, "ml-models/fraud/whatever.pkl")
    fraud_scoring._ensure_model_file_available(missing_path, "ml-models/fraud/whatever.pkl")

    assert call_count["count"] == 1


def test_load_xgb_model_falls_back_to_s3_and_succeeds(monkeypatch, tmp_path):
    """
    Fully self-contained: both the .pkl and the _stats.json are written
    to tmp_path by the mocks below -- no reliance on real repo files.
    Uses a REAL, minimally-fitted sklearn Pipeline(StandardScaler,
    XGBClassifier), matching _load_xgb_model()'s own documented artifact
    shape, not an arbitrary placeholder object. Skipped if xgboost isn't
    installed, same convention as this file's existing
    test_train_fraud_xgb_feature_order_matches_ticket_spec.
    """
    pytest.importorskip("xgboost")
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier

    model_path = tmp_path / "fraud_xgb.pkl"
    stats_path = tmp_path / "fraud_xgb_stats.json"
    stats_path.write_text(json.dumps({"feature_order": ["amount"], "note": "test-stub"}))

    def _fake_successful_download(source_key, destination_path):
        real_pipeline = Pipeline(
            [("scaler", StandardScaler()), ("clf", XGBClassifier(n_estimators=5, max_depth=2))]
        )
        real_pipeline.fit(
            [[10, 1.0, 0, 12, 2, 3, 1], [20, 1.5, 1, 14, 3, 1, 0], [5, 0.5, 0, 9, 5, 10, 1]],
            [0, 1, 0],
        )
        joblib.dump(real_pipeline, destination_path)

    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(model_path))
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_STATS_PATH", str(stats_path))
    monkeypatch.setattr(fraud_scoring, "download_file", _fake_successful_download)

    pipeline, stats = fraud_scoring._load_xgb_model()

    assert isinstance(pipeline, Pipeline)
    predictions = pipeline.predict_proba([[10.0, 1.0, 0, 12, 2, 3, 1]])
    assert predictions.shape == (1, 2)
    assert stats == {"feature_order": ["amount"], "note": "test-stub"}


def test_load_isolation_forest_falls_back_to_s3_and_succeeds(monkeypatch, tmp_path):
    """
    Fully self-contained, real fitted sklearn.ensemble.IsolationForest
    (scikit-learn is a hard backend dependency, unlike xgboost -- no
    importorskip needed). Mirrors the XGBoost success test above.
    """
    from sklearn.ensemble import IsolationForest

    model_path = tmp_path / "isolation_forest.pkl"
    stats_path = tmp_path / "isolation_forest_stats.json"
    stats_path.write_text(json.dumps({"amount_mean": 100.0, "amount_std": 25.0}))

    def _fake_successful_download(source_key, destination_path):
        real_model = IsolationForest(n_estimators=10, random_state=42)
        real_model.fit([[1.0, 2.0, 0, 0], [1.1, 3.0, 0, 1], [0.9, 1.0, 1, 0]])
        joblib.dump(real_model, destination_path)

    monkeypatch.setattr(fraud_scoring, "_isolation_forest_model", None)
    monkeypatch.setattr(fraud_scoring, "_isolation_forest_stats", None)
    monkeypatch.setattr(fraud_scoring, "ISOLATION_FOREST_PATH", str(model_path))
    monkeypatch.setattr(fraud_scoring, "ISOLATION_FOREST_STATS_PATH", str(stats_path))
    monkeypatch.setattr(fraud_scoring, "download_file", _fake_successful_download)

    model, stats = fraud_scoring._load_isolation_forest()

    assert isinstance(model, IsolationForest)
    decision = model.decision_function([[1.0, 2.0, 0, 0]])
    assert len(decision) == 1
    assert stats == {"amount_mean": 100.0, "amount_std": 25.0}


def test_load_xgb_model_s3_failure_falls_back_to_missing_model_behavior(monkeypatch, tmp_path, caplog):
    """Local file missing AND S3 fails -> identical to today's plain
    missing-file case (None, None + warning), no new failure mode."""
    monkeypatch.setattr(fraud_scoring, "_xgb_pipeline", None)
    monkeypatch.setattr(fraud_scoring, "_xgb_stats", None)
    monkeypatch.setattr(fraud_scoring, "FRAUD_XGB_PATH", str(tmp_path / "does_not_exist.pkl"))
    monkeypatch.setattr(
        fraud_scoring,
        "download_file",
        lambda source_key, destination_path: (_ for _ in ()).throw(
            FileNotFoundError("mocked: S3 object not found")
        ),
    )

    with caplog.at_level("WARNING"):
        pipeline, stats = fraud_scoring._load_xgb_model()

    assert pipeline is None
    assert stats is None
    assert any("fraud_xgb.pkl not found" in record.message for record in caplog.records)


def test_load_isolation_forest_s3_failure_raises_file_not_found(monkeypatch, tmp_path):
    """
    _load_isolation_forest() has no try/except today (unlike
    _load_xgb_model()) -- a still-missing file after a failed S3 fetch
    raises FileNotFoundError uncaught, exactly as it does today when the
    file is simply absent. Proves the fallback doesn't change that.
    """
    monkeypatch.setattr(fraud_scoring, "_isolation_forest_model", None)
    monkeypatch.setattr(fraud_scoring, "_isolation_forest_stats", None)
    monkeypatch.setattr(fraud_scoring, "ISOLATION_FOREST_PATH", str(tmp_path / "does_not_exist.pkl"))
    monkeypatch.setattr(
        fraud_scoring,
        "download_file",
        lambda source_key, destination_path: (_ for _ in ()).throw(
            FileNotFoundError("mocked: S3 object not found")
        ),
    )

    with pytest.raises(FileNotFoundError):
        fraud_scoring._load_isolation_forest()

def test_compute_xgb_features_hour_and_day_use_beirut_local_time():
    """
    Regression test: hour_of_day and day_of_week are meant to represent
    LOCAL time-of-day/day-of-week risk ("is this an unusual hour to be
    transacting"), not an arbitrary UTC offset -- same Asia/Beirut
    convention already used correctly elsewhere in this codebase (see
    market_hours.py's MARKET_TIMEZONE). transaction.created_at is stored
    as TIMESTAMPTZ (UTC); _compute_xgb_features() used to read
    transaction.created_at.hour / .weekday() directly, which is the UTC
    hour/weekday, not the Beirut one.

    Uses a UTC timestamp deliberately chosen to cross both a day AND an
    hour boundary once converted to Beirut time (UTC+3 in July, DST):
    2026-07-25 23:30 UTC (a Saturday) is 2026-07-26 02:30 Beirut time (a
    Sunday) -- so a bug here would show up as both a wrong hour (23 vs 2)
    and a wrong weekday (Saturday=5 vs Sunday=6), not just an off-by-a-
    few-hours hour value that could be mistaken for something else.
    """
    from datetime import datetime, timezone
    from decimal import Decimal

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
    from app.models.user import KYCStatus, User, UserRole
    from app.services.fraud_scoring import _compute_xgb_features

    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine, checkfirst=True)
    Transaction.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as db:
        sender = User(
            full_name="Sender", email="tzsender@example.com", phone="+96170000111",
            password_hash="hashed", kyc_status=KYCStatus.approved, role=UserRole.customer,
        )
        receiver = User(
            full_name="Receiver", email="tzreceiver@example.com", phone="+96170000112",
            password_hash="hashed", kyc_status=KYCStatus.approved, role=UserRole.customer,
        )
        db.add_all([sender, receiver])
        db.commit()

        utc_created_at = datetime(2026, 7, 25, 23, 30, 0, tzinfo=timezone.utc)
        transaction = Transaction(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=Decimal("50.00"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key="tz-test-key",
            created_at=utc_created_at,
        )
        db.add(transaction)
        db.commit()

        features = _compute_xgb_features(db, transaction)

    # [amount, amount_to_user_avg_ratio, is_new_recipient, hour_of_day, day_of_week, sender_tx_count_30d, currency_match]
    hour_of_day = features[3]
    day_of_week = features[4]

    assert hour_of_day == 2, (
        f"Expected Beirut local hour 2 (02:30), got {hour_of_day} "
        f"(23 would mean this is still reading the raw UTC hour)"
    )
    assert day_of_week == 6, (
        f"Expected Sunday (weekday=6) in Beirut local time, got {day_of_week} "
        f"(5 would mean this is still reading the UTC weekday, Saturday)"
    )