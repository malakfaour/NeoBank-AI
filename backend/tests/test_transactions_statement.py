"""
Endpoint-level tests for DEVATTECH-94: GET /transactions/statement.

Follows established conventions from this project:
  - test_admin_wallet_tools.py / test_admin_fraud_resolution.py: real
    client, real AsyncSessionLocal, register-via-real-API for fixture
    users, bare @pytest.mark.anyio with no other stacked decorator on
    the test function itself.
  - test_storage.py: mock_aws + a local _configure_storage helper that
    rebuilds storage.storage_client INSIDE the mock context (the
    module-level client built at import time is NOT mock-aware --
    confirmed from that file's own existing pattern, reproduced here
    independently rather than imported, matching this project's
    established "each test file owns its local fixtures" convention).

IMPORTANT: mock_aws is used as a `with mock_aws():` CONTEXT MANAGER
inside each test body, not stacked as a decorator on top of
@pytest.mark.anyio. Stacking `@mock_aws` on an `async def` test breaks
pytest's async-test detection -- moto's decorator wrapper is not itself
declared `async def`, so `asyncio.iscoroutinefunction()` on the wrapped
result is False even though calling it eventually returns a coroutine;
pytest's collection phase uses exactly that check to decide whether a
test needs anyio handling, so a stacked decorator causes it to be
treated as a plain sync test and fail with "async def functions are not
natively supported". Using mock_aws as a plain context manager around
the S3-touching code inside a clean `async def` (matching every other
async test in this project -- none of which stack any decorator on top
of @pytest.mark.anyio) avoids this entirely.

Balance/content assertions require inspecting the actual uploaded S3
object's bytes (the API response itself only carries
{month, s3_key, presigned_url}, per the approved minimal contract) --
done via the same moto-mocked storage client used to configure the
bucket.
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from moto import mock_aws
from sqlalchemy import select

from app.core import storage
from app.db.session import AsyncSessionLocal
from app.models.transaction import (
    Transaction,
    TransactionCurrency,
    TransactionStatus,
)
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency


def _configure_storage(monkeypatch):
    """Independent copy of test_storage.py's own helper -- not imported
    from there, per this project's established per-file fixture
    convention. Must be called from INSIDE an active `with mock_aws():`
    block."""
    monkeypatch.setattr(storage.settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(storage.settings, "S3_REGION", "eu-central-1")
    monkeypatch.setattr(storage.settings, "AWS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(storage.settings, "AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(storage.settings, "S3_ENDPOINT_URL", "")
    client = storage._build_storage_client()
    storage.storage_client = client
    client.create_bucket(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
    )
    return client


async def _register_user(client, label: str) -> dict:
    suffix = uuid4().hex[:10]
    email = f"{label.lower()}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96170{suffix[:6]}",
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200, response.text
    return {**response.json(), "email": email}


async def _get_user_and_wallet(email: str, currency: WalletCurrency) -> tuple[User, Wallet]:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        wallet = (
            await session.execute(
                select(Wallet).where(Wallet.user_id == user.id, Wallet.currency == currency)
            )
        ).scalar_one()
        return user, wallet


async def _set_wallet_balance(wallet_id: int, balance: Decimal) -> None:
    async with AsyncSessionLocal() as session:
        wallet = (await session.execute(select(Wallet).where(Wallet.id == wallet_id))).scalar_one()
        wallet.balance = balance
        await session.commit()


async def _seed_transaction(**kwargs) -> int:
    async with AsyncSessionLocal() as session:
        transaction = Transaction(idempotency_key=f"test-stmt:{uuid4().hex}", **kwargs)
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)
        return transaction.id


def _current_test_month() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _mid_month_datetime():
    now = datetime.now(timezone.utc)
    return now.replace(day=min(now.day, 15) if now.day > 1 else 2)


@pytest.mark.anyio
async def test_statement_csv_happy_path_uploads_and_returns_presigned_url(client, monkeypatch):
    tokens = await _register_user(client, "StatementCsvUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_balance(wallet.id, Decimal("200.00"))

    await _seed_transaction(
        sender_id=user.id,
        receiver_id=user.id,
        amount=Decimal("50.00"),
        currency=TransactionCurrency.USD,
        category="TopUp",
        status=TransactionStatus.completed,
        created_at=_mid_month_datetime(),
    )

    with mock_aws():
        _configure_storage(monkeypatch)

        response = await client.get(
            "/api/v1/transactions/statement",
            params={"month": _current_test_month(), "format": "csv"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["month"] == _current_test_month()
        assert body["s3_key"] == f"neobank-statements/{user.id}/{_current_test_month()}.csv"
        assert body["presigned_url"].startswith("https://")

        object_body = storage.storage_client.get_object(
            Bucket="test-bucket", Key=body["s3_key"]
        )["Body"].read()
        rows = list(csv.reader(io.StringIO(object_body.decode("utf-8"))))
        assert any("USD" in " ".join(row) for row in rows)
        assert any("50.0000" in " ".join(row) for row in rows)


@pytest.mark.anyio
async def test_statement_pdf_happy_path_uploads_valid_pdf(client, monkeypatch):
    tokens = await _register_user(client, "StatementPdfUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_balance(wallet.id, Decimal("100.00"))

    with mock_aws():
        _configure_storage(monkeypatch)

        response = await client.get(
            "/api/v1/transactions/statement",
            params={"month": _current_test_month(), "format": "pdf"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["s3_key"] == f"neobank-statements/{user.id}/{_current_test_month()}.pdf"

        object_body = storage.storage_client.get_object(
            Bucket="test-bucket", Key=body["s3_key"]
        )["Body"].read()
        assert object_body.startswith(b"%PDF")


@pytest.mark.anyio
async def test_statement_includes_pending_bill_payment(client, monkeypatch):
    """
    Status-inclusion regression: bills.py's pay_bill leaves transactions
    permanently in status=pending (confirmed from that file's own
    documented note -- nothing ever transitions them out). Excluding
    pending rows would silently drop every bill payment ever made from
    every statement. This test proves a pending Bills-category row is
    reflected in the reconstructed closing balance.
    """
    tokens = await _register_user(client, "StatementPendingBillUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_balance(wallet.id, Decimal("70.00"))

    await _seed_transaction(
        sender_id=user.id,
        receiver_id=user.id,
        amount=Decimal("30.00"),
        currency=TransactionCurrency.USD,
        category="Bills",
        status=TransactionStatus.pending,
        created_at=_mid_month_datetime(),
    )

    with mock_aws():
        _configure_storage(monkeypatch)

        response = await client.get(
            "/api/v1/transactions/statement",
            params={"month": _current_test_month(), "format": "csv"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()

        object_body = storage.storage_client.get_object(
            Bucket="test-bucket", Key=body["s3_key"]
        )["Body"].read()
        content = object_body.decode("utf-8")
        # Bills = debit; wallet.balance (70.00, no after-month-end tx) is
        # the closing balance; opening = closing - (-30.00) = 100.00.
        assert "100.0000" in content  # opening balance
        assert "70.0000" in content  # closing balance
        assert "pending" in content  # the pending row itself is listed


@pytest.mark.anyio
async def test_statement_currency_with_ambiguous_historical_row_is_not_reconciled(client, monkeypatch):
    """
    A pre-ledger-fix Exchange row (exchange_leg=None) must NOT produce
    a silently-wrong Decimal("0")-based balance -- that currency's
    opening/closing balance must be omitted, with an explicit
    unreconciled marker, per the approved correction.
    """
    tokens = await _register_user(client, "StatementAmbiguousUser")
    user, usd_wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_balance(usd_wallet.id, Decimal("500.00"))

    await _seed_transaction(
        sender_id=user.id,
        receiver_id=user.id,
        amount=Decimal("40.00"),
        currency=TransactionCurrency.USD,
        category="Exchange",
        status=TransactionStatus.completed,
        exchange_leg=None,  # pre-fix row -- direction unknown
        created_at=_mid_month_datetime(),
    )

    with mock_aws():
        _configure_storage(monkeypatch)

        response = await client.get(
            "/api/v1/transactions/statement",
            params={"month": _current_test_month(), "format": "csv"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()

        object_body = storage.storage_client.get_object(
            Bucket="test-bucket", Key=body["s3_key"]
        )["Body"].read()
        content = object_body.decode("utf-8")
        assert "Not available" in content
        # The raw wallet balance must never be shown as if it were the
        # reconciled closing balance.
        assert "500.0000" not in content


@pytest.mark.anyio
async def test_statement_multi_currency_sections_are_independent(client, monkeypatch):
    tokens = await _register_user(client, "StatementMultiCurrencyUser")
    user, usd_wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    _, lbp_wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.LBP)
    await _set_wallet_balance(usd_wallet.id, Decimal("300.00"))
    await _set_wallet_balance(lbp_wallet.id, Decimal("900000.00"))

    with mock_aws():
        _configure_storage(monkeypatch)

        response = await client.get(
            "/api/v1/transactions/statement",
            params={"month": _current_test_month(), "format": "csv"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()

        object_body = storage.storage_client.get_object(
            Bucket="test-bucket", Key=body["s3_key"]
        )["Body"].read()
        content = object_body.decode("utf-8")
        assert "Currency: USD" in content
        assert "Currency: LBP" in content
        assert "300.0000" in content
        assert "900000.0000" in content


@pytest.mark.anyio
async def test_statement_invalid_month_format_returns_400(client):
    tokens = await _register_user(client, "StatementBadMonthUser")

    response = await client.get(
        "/api/v1/transactions/statement",
        params={"month": "not-a-month", "format": "csv"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 400, response.text


@pytest.mark.anyio
async def test_statement_invalid_format_value_returns_422(client):
    tokens = await _register_user(client, "StatementBadFormatUser")

    response = await client.get(
        "/api/v1/transactions/statement",
        params={"month": _current_test_month(), "format": "xlsx"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_statement_route_not_swallowed_by_transaction_id_route(client):
    """
    Route-ordering sanity check: GET /transactions/statement must not be
    matched by GET /{transaction_id} (which would try to parse
    "statement" as an int and 422, or otherwise misroute). A 400 (bad
    month) -- not a transaction_id validation error -- confirms
    /statement was matched correctly.
    """
    tokens = await _register_user(client, "StatementRouteOrderUser")

    response = await client.get(
        "/api/v1/transactions/statement",
        params={"month": "bad", "format": "csv"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 400, response.text
    assert "month" in response.text.lower()