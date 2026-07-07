"""
NBL-411 tests.

Rule 1-3 checks (fraud_rules.py) previously counted a user's own top-ups
(sender_id == receiver_id, see accounts.py card_top_up) as ordinary spend
when computing a sender's rolling average and recent-recipient counts.
This meant a single large top-up could mask a genuinely large, suspicious
send from Rule 1, and inflate the cold-start transaction count in
fraud_scoring.py -- see NBL-411 fraud-query exclusion fix.

Follows the in-memory-SQLite-session pattern from test_transaction_tasks.py
rather than the async API client, since these are plain sync functions
that only need a Session, not a running app.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
from app.models.user import KYCStatus, User, UserRole
from app.services.fraud_rules import (
    _get_rolling_average_spend_sync,
    check_fraud_rules_sync,
)


def _build_sync_session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine, checkfirst=True)
    Transaction.__table__.create(bind=engine, checkfirst=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _make_user(db, label: str) -> User:
    user = User(
        full_name=f"{label} User",
        email=f"{label.lower()}@example.com",
        phone=f"+9617000{abs(hash(label)) % 10000:04d}",
        password_hash="hashed",
        kyc_status=KYCStatus.approved,
        role=UserRole.customer,
    )
    db.add(user)
    db.commit()
    return user


def test_rolling_average_excludes_self_transfers(monkeypatch):
    """
    Direct unit test: _get_rolling_average_spend_sync must not count a
    user's own top-ups (sender_id == receiver_id) toward their spend
    average.
    """
    session_factory = _build_sync_session()
    now = datetime.now(timezone.utc)

    with session_factory() as db:
        sender = _make_user(db, "Sender")
        receiver = _make_user(db, "Receiver")

        # Real prior send: 20.00
        db.add(Transaction(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=Decimal("20.00"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key="real-send-1",
            created_at=now - timedelta(days=1),
        ))
        # Top-up: 10000.00, sender_id == receiver_id == sender
        db.add(Transaction(
            sender_id=sender.id,
            receiver_id=sender.id,
            amount=Decimal("10000.00"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key="topup-1",
            created_at=now - timedelta(hours=1),
        ))
        db.commit()

        avg = _get_rolling_average_spend_sync(db, sender.id, now)

    # If the top-up were (wrongly) included: (20 + 10000) / 2 = 5010.
    # With it excluded, only the real 20.00 send remains.
    assert avg == Decimal("20.00")


def test_rule_1_still_fires_on_large_send_despite_prior_topup(monkeypatch):
    """
    Integration-level proof of the actual bug this fixes: a large top-up
    must not mask a subsequent large, genuinely suspicious send.

    Without the NBL-411 fix, the rolling average would be
    (20 + 10000) / 2 = 5010, and 5000 > 5*5010 is False -- Rule 1 would
    NOT fire. With the fix, the average excludes the top-up (= 20), and
    5000 > 5*20 is True -- Rule 1 fires as it should.
    """
    session_factory = _build_sync_session()
    now = datetime.now(timezone.utc)

    with session_factory() as db:
        sender = _make_user(db, "Sender2")
        receiver = _make_user(db, "Receiver2")
        third_party = _make_user(db, "ThirdParty")

        db.add(Transaction(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=Decimal("20.00"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key="real-send-2",
            created_at=now - timedelta(days=1),
        ))
        db.add(Transaction(
            sender_id=sender.id,
            receiver_id=sender.id,
            amount=Decimal("10000.00"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key="topup-2",
            created_at=now - timedelta(hours=1),
        ))

        new_transaction = Transaction(
            sender_id=sender.id,
            receiver_id=third_party.id,
            amount=Decimal("5000.00"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key="large-send",
            created_at=now,
        )
        db.add(new_transaction)
        db.commit()

        result = check_fraud_rules_sync(db, new_transaction)

    assert result.triggered is True
    assert result.rule_name == "excessive_amount_vs_average"
