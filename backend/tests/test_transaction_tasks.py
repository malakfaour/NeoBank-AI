from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.transaction import (
    Transaction,
    TransactionCurrency,
    TransactionStatus,
)
from app.models.user import KYCStatus, User, UserRole
from app.services.fraud_rules import RuleCheckResult
from app.services.fraud_scoring import FRAUD_FLAG_THRESHOLD
from app.tasks import transaction_tasks


def _build_sync_session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine, checkfirst=True)
    Transaction.__table__.create(bind=engine, checkfirst=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_transaction(session_factory, *, idempotency_key: str):
    with session_factory() as db:
        sender = User(
            full_name="Sender",
            email=f"{idempotency_key}-sender@example.com",
            phone=f"+96170{idempotency_key[-3:]}01",
            password_hash="hashed",
            kyc_status=KYCStatus.approved,
            role=UserRole.customer,
        )
        receiver = User(
            full_name="Receiver",
            email=f"{idempotency_key}-receiver@example.com",
            phone=f"+96170{idempotency_key[-3:]}02",
            password_hash="hashed",
            kyc_status=KYCStatus.approved,
            role=UserRole.customer,
        )
        db.add_all([sender, receiver])
        db.commit()

        transaction = Transaction(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=Decimal("125.00"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key=idempotency_key,
            created_at=datetime.now(timezone.utc),
        )
        db.add(transaction)
        db.commit()
        return transaction.id


def test_score_transaction_flags_when_score_crosses_threshold(monkeypatch):
    session_factory = _build_sync_session()
    transaction_id = _seed_transaction(
        session_factory,
        idempotency_key="idem-flag",
    )

    monkeypatch.setattr(
        transaction_tasks,
        "SyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        transaction_tasks,
        "get_sender_tx_count",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        transaction_tasks,
        "score_with_isolation_forest",
        lambda *args, **kwargs: FRAUD_FLAG_THRESHOLD + 0.01,
    )
    monkeypatch.setattr(
        transaction_tasks,
        "check_fraud_rules_sync",
        lambda *args, **kwargs: RuleCheckResult(
            triggered=False,
            rule_name=None,
        ),
    )
    monkeypatch.setattr(
        transaction_tasks,
        "append_audit_sync",
        lambda *args, **kwargs: None,
    )

    enqueued = []
    monkeypatch.setattr(
        transaction_tasks.categorize_transaction,
        "delay",
        lambda queued_id: enqueued.append(queued_id),
    )

    result = transaction_tasks.score_transaction(transaction_id)

    with session_factory() as db:
        transaction = db.get(Transaction, transaction_id)
        assert transaction.status == TransactionStatus.flagged
        assert transaction.scoring_model == "isolation_forest"
        assert transaction.fraud_score == FRAUD_FLAG_THRESHOLD + 0.01
        assert transaction.rule_triggered is False

    assert enqueued == []

    assert result == {
        "score": FRAUD_FLAG_THRESHOLD + 0.01,
        "flagged": True,
        "model": "isolation_forest",
    }


def test_score_transaction_leaves_completed_below_threshold(monkeypatch):
    session_factory = _build_sync_session()
    transaction_id = _seed_transaction(
        session_factory,
        idempotency_key="idem-safe",
    )

    monkeypatch.setattr(
        transaction_tasks,
        "SyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        transaction_tasks,
        "get_sender_tx_count",
        lambda *args, **kwargs: transaction_tasks.COLD_START_TX_THRESHOLD,
    )
    monkeypatch.setattr(
        transaction_tasks,
        "score_with_xgboost",
        lambda *args, **kwargs: FRAUD_FLAG_THRESHOLD - 0.01,
    )
    monkeypatch.setattr(
        transaction_tasks,
        "check_fraud_rules_sync",
        lambda *args, **kwargs: RuleCheckResult(
            triggered=False,
            rule_name=None,
        ),
    )
    monkeypatch.setattr(
        transaction_tasks,
        "append_audit_sync",
        lambda *args, **kwargs: None,
    )

    enqueued = []
    monkeypatch.setattr(
        transaction_tasks.categorize_transaction,
        "delay",
        lambda queued_id: enqueued.append(queued_id),
    )

    result = transaction_tasks.score_transaction(transaction_id)

    with session_factory() as db:
        transaction = db.get(Transaction, transaction_id)
        assert transaction.status == TransactionStatus.completed
        assert transaction.scoring_model == "xgboost"
        assert transaction.fraud_score == FRAUD_FLAG_THRESHOLD - 0.01
        assert transaction.rule_triggered is False

    assert enqueued == [transaction_id]

    assert result == {
        "score": FRAUD_FLAG_THRESHOLD - 0.01,
        "flagged": False,
        "model": "xgboost",
    }

def test_score_transaction_ml_unavailable_and_rules_clean_completes_normally(monkeypatch):
    """
    DEVATTECH-92: the actual end-to-end scenario item 92 describes --
    "rule-based fallback layer works gracefully if ML scoring service is
    down". Simulates score_with_isolation_forest() returning its safe
    0.0 fallback (as it now does when the model file is missing, instead
    of raising) alongside a clean rule-check result. Before the
    _load_isolation_forest fix, a missing model crashed before
    check_fraud_rules_sync() ever ran, and the transaction was
    blanket-flagged by score_transaction's outer except regardless of
    what the rules said. This proves that no longer happens: with ML
    "down" (0.0, the fallback value) and rules genuinely clean, the
    transaction completes normally, exactly as if a human reviewer had
    manually checked the rules and found nothing wrong.
    """
    session_factory = _build_sync_session()
    transaction_id = _seed_transaction(
        session_factory,
        idempotency_key="idem-ml-down-clean",
    )

    monkeypatch.setattr(transaction_tasks, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(transaction_tasks, "get_sender_tx_count", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        transaction_tasks,
        "score_with_isolation_forest",
        lambda *args, **kwargs: 0.0,  # the graceful missing-model fallback value
    )
    monkeypatch.setattr(
        transaction_tasks,
        "check_fraud_rules_sync",
        lambda *args, **kwargs: RuleCheckResult(triggered=False, rule_name=None),
    )
    monkeypatch.setattr(transaction_tasks, "append_audit_sync", lambda *args, **kwargs: None)

    enqueued = []
    monkeypatch.setattr(
        transaction_tasks.categorize_transaction, "delay", lambda queued_id: enqueued.append(queued_id)
    )

    result = transaction_tasks.score_transaction(transaction_id)

    with session_factory() as db:
        transaction = db.get(Transaction, transaction_id)
        assert transaction.status == TransactionStatus.completed
        assert transaction.rule_triggered is False

    assert enqueued == [transaction_id]
    assert result == {"score": 0.0, "flagged": False, "model": "isolation_forest"}


def test_score_transaction_ml_unavailable_but_rules_triggered_still_flags(monkeypatch):
    """
    Same "ML down" scenario as above, but rules DO find something --
    proves the rule-based layer is still fully independent and effective
    even while ML scoring is unavailable, not just that it doesn't
    over-flag.
    """
    session_factory = _build_sync_session()
    transaction_id = _seed_transaction(
        session_factory,
        idempotency_key="idem-ml-down-flag",
    )

    monkeypatch.setattr(transaction_tasks, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(transaction_tasks, "get_sender_tx_count", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        transaction_tasks,
        "score_with_isolation_forest",
        lambda *args, **kwargs: 0.0,
    )
    monkeypatch.setattr(
        transaction_tasks,
        "check_fraud_rules_sync",
        lambda *args, **kwargs: RuleCheckResult(
            triggered=True, rule_name="excessive_amount_vs_average"
        ),
    )
    monkeypatch.setattr(transaction_tasks, "append_audit_sync", lambda *args, **kwargs: None)

    enqueued = []
    monkeypatch.setattr(
        transaction_tasks.categorize_transaction, "delay", lambda queued_id: enqueued.append(queued_id)
    )

    result = transaction_tasks.score_transaction(transaction_id)

    with session_factory() as db:
        transaction = db.get(Transaction, transaction_id)
        assert transaction.status == TransactionStatus.flagged
        assert transaction.rule_triggered is True

    assert enqueued == []
    assert result == {"score": 0.0, "flagged": True, "model": "isolation_forest"}