from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.bill_payment import BillPayment, BillPaymentStatus, BillType
from app.models.transaction import (
    Transaction,
    TransactionCurrency,
    TransactionStatus,
)
from app.models.user import KYCStatus, User, UserRole
from app.models.wallet import WalletCurrency
from app.tasks import categorization_tasks


def _build_sync_session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine, checkfirst=True)
    Transaction.__table__.create(bind=engine, checkfirst=True)
    BillPayment.__table__.create(bind=engine, checkfirst=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_transaction(
    session_factory,
    *,
    idempotency_key: str,
    with_bill_payment: bool = False,
):
    with session_factory() as db:
        sender = User(
            full_name="Sender",
            email=f"{idempotency_key}-sender@example.com",
            phone=f"+96171{idempotency_key[-3:]}01",
            password_hash="hashed",
            kyc_status=KYCStatus.approved,
            role=UserRole.customer,
        )
        receiver = User(
            full_name="Receiver",
            email=f"{idempotency_key}-receiver@example.com",
            phone=f"+96171{idempotency_key[-3:]}02",
            password_hash="hashed",
            kyc_status=KYCStatus.approved,
            role=UserRole.customer,
        )
        db.add_all([sender, receiver])
        db.commit()

        transaction = Transaction(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=Decimal("42.50"),
            currency=TransactionCurrency.USD,
            status=TransactionStatus.completed,
            idempotency_key=idempotency_key,
            created_at=datetime.now(timezone.utc),
        )
        db.add(transaction)
        db.commit()

        if with_bill_payment:
            bill_payment = BillPayment(
                user_id=sender.id,
                wallet_id=1,
                bill_type=BillType.edl,
                bill_reference="EDL-12345",
                amount=Decimal("42.50"),
                currency=WalletCurrency.USD,
                status=BillPaymentStatus.success,
                transaction_id=transaction.id,
            )
            db.add(bill_payment)
            db.commit()

        return transaction.id


def test_categorize_transaction_writes_valid_groq_category(monkeypatch):
    session_factory = _build_sync_session()
    transaction_id = _seed_transaction(
        session_factory,
        idempotency_key="cat-food",
    )

    monkeypatch.setattr(
        categorization_tasks,
        "SyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        categorization_tasks,
        "_call_groq",
        lambda _transaction_text: "Food",
    )

    result = categorization_tasks.categorize_transaction(transaction_id)

    with session_factory() as db:
        transaction = db.get(Transaction, transaction_id)
        assert transaction.category == "Food"

    assert result == "Food"


def test_categorize_transaction_defaults_to_other_for_unexpected_response(
    monkeypatch,
):
    session_factory = _build_sync_session()
    transaction_id = _seed_transaction(
        session_factory,
        idempotency_key="cat-other",
    )

    monkeypatch.setattr(
        categorization_tasks,
        "SyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        categorization_tasks,
        "_call_groq",
        lambda _transaction_text: "Travel",
    )

    result = categorization_tasks.categorize_transaction(transaction_id)

    with session_factory() as db:
        transaction = db.get(Transaction, transaction_id)
        assert transaction.category == "Other"

    assert result == "Other"


def test_bill_transaction_hardcodes_bills_without_calling_groq(monkeypatch):
    session_factory = _build_sync_session()
    transaction_id = _seed_transaction(
        session_factory,
        idempotency_key="cat-bill",
        with_bill_payment=True,
    )

    monkeypatch.setattr(
        categorization_tasks,
        "SyncSessionLocal",
        session_factory,
    )

    def fail_if_called(_transaction_text):
        raise AssertionError("Groq must not be called for bill transactions")

    monkeypatch.setattr(
        categorization_tasks,
        "_call_groq",
        fail_if_called,
    )

    result = categorization_tasks.categorize_transaction(transaction_id)

    with session_factory() as db:
        transaction = db.get(Transaction, transaction_id)
        assert transaction.category == "Bills"

    assert result == "Bills"
