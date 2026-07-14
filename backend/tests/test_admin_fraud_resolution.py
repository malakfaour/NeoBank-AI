"""
Endpoint-level tests for the reversal-ledger fix (Issue 2 of 3):
resolve_flag's confirmed_fraud path now creates a compensating
Transaction row (category="Reversal", ledger_direction=credit) in
addition to flipping the original transaction's status -- so balance
reconstruction can see the credit-back directly in Transaction data.

Follows test_admin_wallet_tools.py's exact pattern: real client, real
AsyncSessionLocal, admin/compliance tokens minted directly via
create_access_token (get_current_user reads role purely from the JWT
claim, no DB re-fetch -- confirmed in app/api/dependencies.py).

A flagged transaction is seeded directly via DB write, not through the
real scoring pipeline -- there's no reliable way to make the real
Isolation Forest/XGBoost scoring path naturally flag a specific
synthetic transaction on demand.

related_transaction_id is intentionally NOT a schema column, per
approved scope -- linkage is asserted via audit-log metadata instead
(compensating_transaction_id on the original transaction's audit entry,
related_transaction_id on the compensating transaction's own entry).
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.transaction import LedgerDirection, Transaction, TransactionCurrency, TransactionStatus
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


async def _seed_flagged_transaction(sender_id: int, receiver_id: int, amount: Decimal) -> int:
    async with AsyncSessionLocal() as session:
        transaction = Transaction(
            sender_id=sender_id,
            receiver_id=receiver_id,
            amount=amount,
            currency=TransactionCurrency.USD,
            status=TransactionStatus.flagged,
            idempotency_key=f"test-flagged:{uuid4().hex}",
        )
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)
        return transaction.id


def _compliance_token() -> str:
    access_token, _ = create_access_token(subject="999003", role="compliance_officer")
    return access_token


@pytest.mark.anyio
async def test_resolve_flag_confirmed_fraud_creates_compensating_reversal_transaction(client):
    sender_tokens = await _register_user(client, "ReversalSender")
    receiver_tokens = await _register_user(client, "ReversalReceiver")
    sender, sender_wallet = await _get_user_and_wallet(sender_tokens["email"], WalletCurrency.USD)
    receiver, _ = await _get_user_and_wallet(receiver_tokens["email"], WalletCurrency.USD)

    transaction_id = await _seed_flagged_transaction(sender.id, receiver.id, Decimal("50.00"))

    response = await client.post(
        f"/api/v1/admin/transactions/{transaction_id}/resolve-flag",
        headers={"Authorization": f"Bearer {_compliance_token()}"},
        json={"resolution": "confirmed_fraud", "reviewer_note": "Confirmed fraud in test"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_status"] == "reversed"

    async with AsyncSessionLocal() as session:
        # --- original transaction preserved, only status changed ---
        original = (
            await session.execute(select(Transaction).where(Transaction.id == transaction_id))
        ).scalar_one()
        assert original.status == TransactionStatus.reversed
        assert original.amount == Decimal("50.0000")
        assert original.currency == TransactionCurrency.USD
        assert original.sender_id == sender.id
        assert original.receiver_id == receiver.id

        # --- exactly one compensating Reversal row, correctly shaped ---
        compensating_rows = (
            await session.execute(
                select(Transaction).where(
                    Transaction.category == "Reversal",
                    Transaction.sender_id == sender.id,
                )
            )
        ).scalars().all()
        assert len(compensating_rows) == 1
        compensating = compensating_rows[0]
        assert compensating.ledger_direction == LedgerDirection.credit
        assert compensating.amount == Decimal("50.0000")
        assert compensating.currency == TransactionCurrency.USD
        assert compensating.sender_id == sender.id
        assert compensating.receiver_id == sender.id
        assert compensating.status == TransactionStatus.completed

        # --- sender's wallet actually credited back ---
        refreshed_wallet = (
            await session.execute(select(Wallet).where(Wallet.id == sender_wallet.id))
        ).scalar_one()
        assert refreshed_wallet.balance == Decimal("50.0000")

        # --- audit linkage lives in metadata on BOTH sides, per approved scope ---
        original_audit_rows = (
            await session.execute(
                select(TransactionAuditLog).where(TransactionAuditLog.transaction_id == transaction_id)
            )
        ).scalars().all()
        reversed_audit = next(row for row in original_audit_rows if row.action == "reversed")
        assert reversed_audit.event_metadata["compensating_transaction_id"] == compensating.id

        compensating_audit_rows = (
            await session.execute(
                select(TransactionAuditLog).where(TransactionAuditLog.transaction_id == compensating.id)
            )
        ).scalars().all()
        assert len(compensating_audit_rows) >= 1
        reversal_credit_audit = next(row for row in compensating_audit_rows if row.action == "reversal_credit")
        assert reversal_credit_audit.event_metadata["related_transaction_id"] == transaction_id


@pytest.mark.anyio
async def test_resolve_flag_duplicate_resolution_does_not_create_second_compensating_row(client):
    sender_tokens = await _register_user(client, "ReversalDupSender")
    receiver_tokens = await _register_user(client, "ReversalDupReceiver")
    sender, _ = await _get_user_and_wallet(sender_tokens["email"], WalletCurrency.USD)
    receiver, _ = await _get_user_and_wallet(receiver_tokens["email"], WalletCurrency.USD)

    transaction_id = await _seed_flagged_transaction(sender.id, receiver.id, Decimal("20.00"))

    first_response = await client.post(
        f"/api/v1/admin/transactions/{transaction_id}/resolve-flag",
        headers={"Authorization": f"Bearer {_compliance_token()}"},
        json={"resolution": "confirmed_fraud", "reviewer_note": "First resolution"},
    )
    assert first_response.status_code == 200, first_response.text

    # Second attempt: transaction.status is now "reversed", not "flagged",
    # so resolve_flag's own status check rejects it (400) before ever
    # reaching the FraudResolution unique-constraint race path (409) --
    # both are valid "rejected, not double-processed" outcomes; this test
    # only asserts on the resulting row count, not the exact status code.
    second_response = await client.post(
        f"/api/v1/admin/transactions/{transaction_id}/resolve-flag",
        headers={"Authorization": f"Bearer {_compliance_token()}"},
        json={"resolution": "confirmed_fraud", "reviewer_note": "Second resolution attempt"},
    )
    assert second_response.status_code in (400, 409), second_response.text

    async with AsyncSessionLocal() as session:
        compensating_rows = (
            await session.execute(
                select(Transaction).where(
                    Transaction.category == "Reversal",
                    Transaction.sender_id == sender.id,
                )
            )
        ).scalars().all()
        assert len(compensating_rows) == 1
