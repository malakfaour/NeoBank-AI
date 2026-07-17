from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.exchange_audit_log import ExchangeAuditLog
from app.models.exchange_rate import ExchangeRate
from app.models.model_metrics import ModelMetrics
from app.models.transaction import ExchangeLegType, Transaction
from app.models.user import User, UserRole
from app.models.wallet import Wallet, WalletCurrency
from app.services.exchange_cache import set_cached_exchange_rates
from app.tasks import exchange_tasks


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


async def _get_user_and_wallets(email: str) -> tuple[User, dict[WalletCurrency, Wallet]]:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        wallets = (
            await session.execute(select(Wallet).where(Wallet.user_id == user.id))
        ).scalars().all()
        return user, {wallet.currency: wallet for wallet in wallets}


async def _top_up(client, access_token: str, wallet_id: int, amount: str) -> None:
    # DEVATTECH-125: X-Idempotency-Key is now required on this endpoint.
    response = await client.post(
        "/api/v1/accounts/top-up",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "wallet_id": wallet_id,
            "amount": amount,
            "card_token": "tok_visa_test_123",
        },
    )
    assert response.status_code == 200, response.text


async def _promote_user(email: str, role: UserRole) -> tuple[User, str]:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        user.role = role
        await session.commit()
        await session.refresh(user)
        token, _ = create_access_token(str(user.id), role=user.role.value)
        return user, token


@pytest.mark.anyio
async def test_exchange_rates_live_prefers_cache(client):
    await set_cached_exchange_rates({("USD", "LBP"): Decimal("89500.25")})

    response = await client.get("/api/v1/exchange/rates/live?from_currency=USD&to_currency=LBP")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "redis-cache"
    assert Decimal(body["rate"]) == Decimal("89500.25")
    assert body["cache_age_seconds"] >= 0


@pytest.mark.anyio
async def test_exchange_rates_live_falls_back_to_database(client):
    async with AsyncSessionLocal() as session:
        session.add(
            ExchangeRate(
                base_currency="USD",
                target_currency="LBP",
                rate=Decimal("90000.00"),
                provider="db-seed",
                last_updated_at=datetime.now(timezone.utc) - timedelta(seconds=45),
            )
        )
        await session.commit()

    response = await client.get("/api/v1/exchange/rates/live?from_currency=USD&to_currency=LBP")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "db-seed"
    assert Decimal(body["rate"]) == Decimal("90000.00")
    assert body["cache_age_seconds"] >= 40


@pytest.mark.anyio
async def test_execute_exchange_creates_transaction_and_audit_rows(client, monkeypatch):
    tokens = await _register_user(client, "exchange-happy")
    user, wallets = await _get_user_and_wallets(tokens["email"])
    await _top_up(client, tokens["access_token"], wallets[WalletCurrency.USD].id, "120.00")

    async def fake_rates():
        return {("USD", "LBP"): Decimal("89500.00")}

    monkeypatch.setattr("app.api.v1.endpoints.exchange.is_market_open", lambda: True)
    monkeypatch.setattr("app.api.v1.endpoints.exchange.get_rates_from_cache_or_provider", fake_rates)

    response = await client.post(
        "/api/v1/exchange/execute",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "from_currency": "USD",
            "to_currency": "LBP",
            "amount": "10.00",
        },
    )

    assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as session:
        usd_wallet = await session.scalar(
            select(Wallet).where(Wallet.user_id == user.id, Wallet.currency == WalletCurrency.USD)
        )
        lbp_wallet = await session.scalar(
            select(Wallet).where(Wallet.user_id == user.id, Wallet.currency == WalletCurrency.LBP)
        )
        exchange_tx = await session.scalar(
            select(Transaction).where(
                Transaction.sender_id == user.id,
                Transaction.receiver_id == user.id,
                Transaction.category == "Exchange",
                # Ledger fix (Issue 1 of 3): this exchange now writes TWO
                # rows (debit + credit legs); the original unfiltered
                # query would be ambiguous (.scalar() with no explicit
                # single-row guarantee). Filtering by the intended
                # semantic leg -- debit, which is what this assertion
                # actually checks (currency == "USD", the source
                # currency) -- keeps this deterministic without relying
                # on row/insertion order.
                Transaction.exchange_leg == ExchangeLegType.debit,
            )
        )
        exchange_audit = await session.scalar(
            select(ExchangeAuditLog).where(ExchangeAuditLog.exchange_id == response.json()["exchange_id"])
        )

    assert usd_wallet.balance == Decimal("110.0000")
    assert lbp_wallet.balance == Decimal("895000.0000")
    assert exchange_tx is not None
    assert exchange_tx.currency.value == "USD"
    assert exchange_tx.status.value == "completed"
    assert exchange_audit is not None
    assert exchange_audit.user_id == user.id
    assert exchange_audit.status == "executed"


@pytest.mark.anyio
async def test_execute_exchange_rejects_insufficient_balance_without_writing_rows(client, monkeypatch):
    tokens = await _register_user(client, "exchange-low")
    user, _ = await _get_user_and_wallets(tokens["email"])

    async def fake_rates():
        return {("USD", "LBP"): Decimal("89500.00")}

    monkeypatch.setattr("app.api.v1.endpoints.exchange.is_market_open", lambda: True)
    monkeypatch.setattr("app.api.v1.endpoints.exchange.get_rates_from_cache_or_provider", fake_rates)

    response = await client.post(
        "/api/v1/exchange/execute",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "from_currency": "USD",
            "to_currency": "LBP",
            "amount": "10.00",
        },
    )

    assert response.status_code == 422, response.text

    async with AsyncSessionLocal() as session:
        exchange_rows = (
            await session.execute(
                select(Transaction).where(
                    Transaction.sender_id == user.id,
                    Transaction.category == "Exchange",
                )
            )
        ).scalars().all()
        audit_rows = (
            await session.execute(
                select(ExchangeAuditLog).where(ExchangeAuditLog.user_id == user.id)
            )
        ).scalars().all()

    assert exchange_rows == []
    assert audit_rows == []


@pytest.mark.anyio
async def test_execute_exchange_uses_single_ordered_wallet_lock_query(client, monkeypatch):
    tokens = await _register_user(client, "exchange-lock")
    _, wallets = await _get_user_and_wallets(tokens["email"])
    await _top_up(client, tokens["access_token"], wallets[WalletCurrency.USD].id, "25.00")

    async def fake_rates():
        return {("USD", "LBP"): Decimal("89500.00")}

    monkeypatch.setattr("app.api.v1.endpoints.exchange.is_market_open", lambda: True)
    monkeypatch.setattr("app.api.v1.endpoints.exchange.get_rates_from_cache_or_provider", fake_rates)

    original_execute = AsyncSession.execute
    wallet_statements: list[object] = []

    async def recording_execute(self, statement, *args, **kwargs):
        statement_text = str(statement)
        if "FROM wallets" in statement_text:
            wallet_statements.append(statement)
        return await original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", recording_execute)

    response = await client.post(
        "/api/v1/exchange/execute",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "from_currency": "USD",
            "to_currency": "LBP",
            "amount": "5.00",
        },
    )

    assert response.status_code == 200, response.text
    assert len(wallet_statements) == 1
    assert wallet_statements[0]._for_update_arg is not None
    assert "ORDER BY wallets.id ASC" in str(wallet_statements[0])


@pytest.mark.anyio
async def test_admin_exchange_audit_endpoint_returns_user_info(client):
    admin_tokens = await _register_user(client, "exchange-admin")
    exchange_user_tokens = await _register_user(client, "exchange-user")
    exchange_user, _ = await _promote_user(exchange_user_tokens["email"], UserRole.customer)
    _, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.compliance_officer)

    async with AsyncSessionLocal() as session:
        session.add(
            ExchangeAuditLog(
                exchange_id=str(uuid4()),
                user_id=exchange_user.id,
                from_currency="USD",
                to_currency="LBP",
                amount=Decimal("12.50"),
                rate=Decimal("89500.00"),
                converted_amount=Decimal("1118750.00"),
                status="executed",
                provider="redis-cache",
            )
        )
        await session.commit()

    response = await client.get(
        "/api/v1/admin/exchange/audit",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 1
    matching_rows = [item for item in body["items"] if item["user_id"] == exchange_user.id]
    assert len(matching_rows) == 1
    assert matching_rows[0]["user_email"] == exchange_user.email


@pytest.mark.anyio
async def test_admin_ml_metrics_returns_latest_row_per_model(client):
    admin_tokens = await _register_user(client, "metrics-admin")
    _, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.admin)

    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                ModelMetrics(
                    model_name="LightGBM",
                    mae=12.5,
                    trained_at=datetime.now(timezone.utc) - timedelta(days=2),
                ),
                ModelMetrics(
                    model_name="LightGBM",
                    mae=8.75,
                    trained_at=datetime.now(timezone.utc) - timedelta(hours=1),
                ),
                ModelMetrics(
                    model_name="XGBoost",
                    mae=6.25,
                    trained_at=datetime.now(timezone.utc) - timedelta(hours=2),
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/admin/ml/metrics",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["model_name"] for row in body] == ["LightGBM", "XGBoost"]
    assert body[0]["mae"] == 8.75
    assert body[1]["mae"] == 6.25


class _FakeSyncRedis:
    def __init__(self):
        self.saved = {}

    def setex(self, key, ttl, value):
        self.saved[key] = {"ttl": ttl, "value": value}

@pytest.mark.anyio
async def test_retrain_exchange_forecast_persists_model_metrics(monkeypatch):
    fake_sync_redis = _FakeSyncRedis()

    async def fake_fetch_exchange_rates():
        return {("USD", "LBP"): Decimal("90000.00")}

    monkeypatch.setattr(
        exchange_tasks,
        "fetch_exchange_rates",
        fake_fetch_exchange_rates,
    )

    monkeypatch.setattr(
        redis.Redis,
        "from_url",
        lambda *args, **kwargs: fake_sync_redis,
    )

    async with AsyncSessionLocal() as session:
        before_count = (
            await session.execute(
                select(ModelMetrics).where(
                    ModelMetrics.model_name == "LightGBM"
                )
            )
        ).scalars().all()

    result = await exchange_tasks.retrain_exchange_forecast_model()

    async with AsyncSessionLocal() as session:
        metrics_rows = (
            await session.execute(
                select(ModelMetrics)
                .where(
                    ModelMetrics.model_name == "LightGBM"
                )
                .order_by(ModelMetrics.id.asc())
            )
        ).scalars().all()

    assert result["status"] == "ok"
    assert result["mae"] >= 0
    assert len(metrics_rows) == len(before_count) + 1
    assert metrics_rows[-1].mae == result["mae"]


@pytest.mark.anyio
async def test_execute_exchange_creates_both_debit_and_credit_ledger_legs(client, monkeypatch):
    """
    Ledger fix (Issue 1 of 3, DEVATTECH-92 prerequisite): execute_exchange
    must write TWO Transaction rows -- a debit leg in the source currency
    and a credit leg in the target currency -- distinguished by the new
    Transaction.exchange_leg column, so balance reconstruction can
    identify both legs directly from transaction data.

    Does not duplicate test_execute_exchange_creates_transaction_and_audit_rows
    above (already covers the audit-log row and overall wallet balances) --
    this test is specifically about the new two-row ledger structure and
    the unchanged response contract.

    Atomic-failure coverage (both legs absent on a rejected exchange) is
    already provided by
    test_execute_exchange_rejects_insufficient_balance_without_writing_rows
    above, unmodified -- its query filters only on sender_id/category=="Exchange",
    with no dependence on exchange_leg, so it already catches either leg
    if one were incorrectly written on a failed request.
    """
    tokens = await _register_user(client, "exchange-two-legs")
    user, wallets = await _get_user_and_wallets(tokens["email"])
    await _top_up(client, tokens["access_token"], wallets[WalletCurrency.USD].id, "120.00")

    async def fake_rates():
        return {("USD", "LBP"): Decimal("89500.00")}

    monkeypatch.setattr("app.api.v1.endpoints.exchange.is_market_open", lambda: True)
    monkeypatch.setattr("app.api.v1.endpoints.exchange.get_rates_from_cache_or_provider", fake_rates)

    response = await client.post(
        "/api/v1/exchange/execute",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "from_currency": "USD",
            "to_currency": "LBP",
            "amount": "10.00",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()

    # --- unchanged API response contract (ExchangeExecutionResponse) ---
    assert set(body.keys()) == {
        "exchange_id", "status", "from_currency", "to_currency",
        "amount", "rate", "converted_amount", "message",
    }
    assert body["status"] == "executed"
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "LBP"
    assert Decimal(body["amount"]) == Decimal("10.00")
    assert Decimal(body["converted_amount"]) == Decimal("895000.00")

    # --- both ledger legs exist ---
    async with AsyncSessionLocal() as session:
        exchange_rows = (
            await session.execute(
                select(Transaction).where(
                    Transaction.sender_id == user.id,
                    Transaction.category == "Exchange",
                )
            )
        ).scalars().all()

    assert len(exchange_rows) == 2

    # Proves the column round-trips as the REAL enum class, not merely a
    # string that happens to match -- `is` comparison against the actual
    # enum member (Python enum members are singletons), stronger than
    # `.value == "debit"`.
    for tx in exchange_rows:
        assert isinstance(tx.exchange_leg, ExchangeLegType)

    debit_rows = [tx for tx in exchange_rows if tx.exchange_leg is ExchangeLegType.debit]
    credit_rows = [tx for tx in exchange_rows if tx.exchange_leg is ExchangeLegType.credit]

    assert len(debit_rows) == 1
    assert len(credit_rows) == 1

    debit_leg = debit_rows[0]
    credit_leg = credit_rows[0]

    # --- debit leg: source currency, source amount ---
    assert debit_leg.currency.value == "USD"
    assert debit_leg.amount == Decimal("10.0000")
    assert debit_leg.status.value == "completed"
    assert debit_leg.sender_id == user.id
    assert debit_leg.receiver_id == user.id

    # --- credit leg: target currency, converted amount ---
    assert credit_leg.currency.value == "LBP"
    assert credit_leg.amount == Decimal("895000.0000")
    assert credit_leg.status.value == "completed"
    assert credit_leg.sender_id == user.id
    assert credit_leg.receiver_id == user.id
@pytest.mark.anyio
async def test_retrain_exchange_forecast_rolls_back_worse_model(monkeypatch):

    fake_sync_redis = _FakeSyncRedis()

    monkeypatch.setattr(
        redis.Redis,
        "from_url",
        lambda *args, **kwargs: fake_sync_redis,
    )

    async def fake_fetch_exchange_rates():
        return {
            ("USD", "LBP"): Decimal("90000.00")
        }

    async def fake_previous_mae():
        return 100.0

    def fake_train_models(_):
        return {
            "winner": "LightGBM",
            "results": [
                {
                    "model": "LightGBM",
                    "mae": 150.0,
                }
            ],
        }

    rollback_called = False

    def fake_rollback():
        nonlocal rollback_called
        rollback_called = True

    monkeypatch.setattr(
        exchange_tasks,
        "fetch_exchange_rates",
        fake_fetch_exchange_rates,
    )

    monkeypatch.setattr(
        exchange_tasks,
        "get_previous_mae",
        fake_previous_mae,
    )

    monkeypatch.setattr(
        exchange_tasks,
        "train_and_evaluate_models",
        fake_train_models,
    )

    monkeypatch.setattr(
        exchange_tasks,
        "rollback_model",
        fake_rollback,
    )

    monkeypatch.setattr(
        exchange_tasks,
        "backup_current_model",
        lambda: None,
    )

    result = await exchange_tasks.retrain_exchange_forecast_model()

    assert result["status"] == "ok"
    assert result["mae"] == 150.0
    assert rollback_called is True

@pytest.mark.anyio
async def test_exchange_rates_history_returns_predicted_rate(client):

    async with AsyncSessionLocal() as session:

        existing = await session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency == "USD",
                ExchangeRate.target_currency == "LBP",
            )
        )

        if existing:
            existing.rate = Decimal("90000.00")
            existing.provider = "test-provider"
            existing.last_updated_at = (
                datetime.now(timezone.utc)
                - timedelta(days=1)
            )

        else:
            session.add(
                ExchangeRate(
                    base_currency="USD",
                    target_currency="LBP",
                    rate=Decimal("90000.00"),
                    provider="test-provider",
                    last_updated_at=(
                        datetime.now(timezone.utc)
                        - timedelta(days=1)
                    ),
                )
            )

        await session.commit()

    response = await client.get(
        "/api/v1/exchange/rates/history?days=30"
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert len(body) >= 1
    assert "date" in body[0]
    assert "rate" in body[0]
    assert body[-1]["rate"] == 90000.0
