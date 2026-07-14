"""
Endpoint-level tests for DEVATTECH-108: admin user/wallet lookup +
manual balance adjustment.

Admin/compliance role access is tested by minting tokens directly via
create_access_token(subject, role=...), since /auth/register only ever
creates customer-role users and get_current_user() reads role purely
from the JWT claim (no DB re-fetch) -- confirmed in
app/api/dependencies.py, same technique used in DEVATTECH-104's tests.
This avoids the heavier RBAC/DB fixture gap documented in test_admin.py,
which only applies where real cross-table DB state is also needed.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.transaction import LedgerDirection, Transaction
from app.models.transaction_audit_log import TransactionAuditLog
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency


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
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        wallet = (
            await session.execute(
                select(Wallet).where(
                    Wallet.user_id == user.id,
                    Wallet.currency == currency,
                )
            )
        ).scalar_one()
        return user, wallet


async def _set_wallet_balance(wallet_id: int, balance: Decimal) -> None:
    async with AsyncSessionLocal() as session:
        wallet = (
            await session.execute(select(Wallet).where(Wallet.id == wallet_id))
        ).scalar_one()
        wallet.balance = balance
        await session.commit()


def _admin_token() -> str:
    access_token, _ = create_access_token(subject="999001", role="admin")
    return access_token


def _compliance_token() -> str:
    access_token, _ = create_access_token(subject="999002", role="compliance_officer")
    return access_token


@pytest.mark.anyio
async def test_search_users_finds_by_partial_email(client):
    tokens = await _register_user(client, "SearchTargetUnique")

    response = await client.get(
        "/api/v1/admin/users/search",
        params={"q": "searchtargetunique"},
        headers={"Authorization": f"Bearer {_admin_token()}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 1
    assert any(item["email"] == tokens["email"] for item in body["items"])


@pytest.mark.anyio
async def test_search_users_accessible_by_compliance(client):
    response = await client.get(
        "/api/v1/admin/users/search",
        params={"q": "nonexistent-search-term-xyz"},
        headers={"Authorization": f"Bearer {_compliance_token()}"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_get_user_wallets_returns_all_currencies(client):
    tokens = await _register_user(client, "WalletLookupUser")
    user, _ = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await client.get(
        f"/api/v1/admin/users/{user.id}/wallets",
        headers={"Authorization": f"Bearer {_admin_token()}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == user.id
    currencies = {item["currency"] for item in body["items"]}
    assert "USD" in currencies


@pytest.mark.anyio
async def test_adjust_credit_by_admin_creates_transaction_and_audit_row(client):
    tokens = await _register_user(client, "AdjustCreditUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_balance(wallet.id, Decimal("100.00"))

    response = await client.post(
        f"/api/v1/admin/wallets/{wallet.id}/adjust",
        headers={"Authorization": f"Bearer {_admin_token()}"},
        json={"amount": "50.00", "direction": "credit", "reason": "Goodwill credit - support ticket #123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_balance"] == "150.0000" or Decimal(body["new_balance"]) == Decimal("150.00")

    async with AsyncSessionLocal() as session:
        tx = (
            await session.execute(
                select(Transaction).where(Transaction.id == body["transaction_id"])
            )
        ).scalar_one()
        assert tx.sender_id == user.id
        assert tx.receiver_id == user.id
        assert tx.category == "Adjustment"
        assert Decimal(tx.amount) == Decimal("50.00")
        assert tx.ledger_direction == LedgerDirection.credit

        audit_rows = (
            await session.execute(
                select(TransactionAuditLog).where(
                    TransactionAuditLog.transaction_id == tx.id
                )
            )
        ).scalars().all()
        assert any(row.action == "admin_adjustment" for row in audit_rows)
        adjustment_row = next(row for row in audit_rows if row.action == "admin_adjustment")
        assert adjustment_row.event_metadata["direction"] == "credit"
        assert adjustment_row.event_metadata["reason"] == "Goodwill credit - support ticket #123"


@pytest.mark.anyio
async def test_adjust_debit_reduces_balance(client):
    tokens = await _register_user(client, "AdjustDebitUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_balance(wallet.id, Decimal("100.00"))

    response = await client.post(
        f"/api/v1/admin/wallets/{wallet.id}/adjust",
        headers={"Authorization": f"Bearer {_admin_token()}"},
        json={"amount": "30.00", "direction": "debit", "reason": "Correcting duplicate top-up"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body["new_balance"]) == Decimal("70.00")

    async with AsyncSessionLocal() as session:
        tx = (
            await session.execute(
                select(Transaction).where(Transaction.id == body["transaction_id"])
            )
        ).scalar_one()
        assert tx.ledger_direction == LedgerDirection.debit


@pytest.mark.anyio
async def test_adjust_debit_insufficient_balance_rejected(client):
    tokens = await _register_user(client, "AdjustInsufficientUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)
    await _set_wallet_balance(wallet.id, Decimal("10.00"))

    response = await client.post(
        f"/api/v1/admin/wallets/{wallet.id}/adjust",
        headers={"Authorization": f"Bearer {_admin_token()}"},
        json={"amount": "500.00", "direction": "debit", "reason": "Should fail"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_adjust_by_compliance_role_returns_403(client):
    """Explicit AC requirement: admin only, NOT compliance_officer."""
    tokens = await _register_user(client, "AdjustComplianceDeniedUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await client.post(
        f"/api/v1/admin/wallets/{wallet.id}/adjust",
        headers={"Authorization": f"Bearer {_compliance_token()}"},
        json={"amount": "10.00", "direction": "credit", "reason": "Should be denied"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_adjust_by_customer_role_returns_403(client):
    tokens = await _register_user(client, "AdjustCustomerDeniedUser")
    user, wallet = await _get_user_and_wallet(tokens["email"], WalletCurrency.USD)

    response = await client.post(
        f"/api/v1/admin/wallets/{wallet.id}/adjust",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"amount": "10.00", "direction": "credit", "reason": "Should be denied"},
    )
    assert response.status_code == 403, response.text
