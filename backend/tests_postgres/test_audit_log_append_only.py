"""
Postgres E2E money-path CI job -- AC: "append-only trigger proven by a
test that verifies UPDATE raises an error."

Proves the Postgres trigger added in 7f3d9c1a6e28
(trg_transaction_audit_logs_no_update) enforces append-only behavior at
the DATABASE level, not just in application code -- app/services/
audit_log.py deliberately has no update_audit()/delete_audit() helper,
but that alone doesn't prove the database itself would reject a raw
UPDATE issued some other way (a bad migration, a manual psql session, a
future bug). This test issues a raw UPDATE directly against
transaction_audit_logs and asserts it raises.

Setup uses the real API (register -> top-up -> send) to produce a real
Transaction + TransactionAuditLog row, rather than hand-constructing
User/Transaction rows directly -- several fields on those models were
never fully confirmed during this ticket's file-review rounds, and
reusing already-proven-correct application code for row creation avoids
guessing at a schema. The one exception: wallet_id is looked up via a
direct, READ-ONLY database query after registration, since no reviewed
endpoint (register's response, GET /accounts/balance) exposes a wallet's
numeric id. This is a deliberate, narrow choice for this specific file --
it already needs a direct DB connection for its actual assertion (the
raw UPDATE), so one extra read-only lookup on that same connection is in
keeping with what this file already does, not a new kind of workaround.

The actual assertion this test makes has nothing to do with send_money's
business logic -- only with whether the resulting audit log row can be
updated. No production file is modified.
"""
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError


async def _register_user(client, label: str, password: str = "TestPass123") -> dict:
    suffix = uuid4().hex[:10]
    numeric_suffix = str(int(suffix, 16))[-6:].zfill(6)
    email = f"{label.lower()}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96170{numeric_suffix}",
            "password": password,
        },
    )
    # Confirmed from auth.py's actual decorator -- no status_code= override
    # is passed to @router.post("/register", ...), so FastAPI's default
    # (200, not 201) applies.
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.postgres
async def test_transaction_audit_log_update_is_rejected_by_db_trigger(client, stub_fraud_scoring):
    # --- setup: real register -> top-up -> send, via the actual API ---
    sender = await _register_user(client, "audit-trigger-sender")
    receiver = await _register_user(client, "audit-trigger-receiver")
    sender_id = sender["user"]["id"]
    receiver_id = receiver["user"]["id"]

    # Lazy import, matching conftest.py's own discipline -- only imported
    # inside a test function, never at module level. AsyncSessionLocal
    # confirmed against the real backend/app/db/session.py:
    # `AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, ...)`.
    from app.db.session import AsyncSessionLocal
    from app.models.wallet import Wallet, WalletCurrency

    async with AsyncSessionLocal() as db:
        # READ-ONLY lookup -- see module docstring for why this one
        # direct query exists in this file specifically.
        result = await db.execute(
            select(Wallet).where(
                Wallet.user_id == sender_id,
                Wallet.currency == WalletCurrency.USD,
            )
        )
        sender_wallet = result.scalar_one()

    top_up_response = await client.post(
        "/api/v1/accounts/top-up",
        headers={"Authorization": f"Bearer {sender['access_token']}"},
        json={
            "wallet_id": sender_wallet.id,
            "amount": "100.00",
            "card_token": "tok_visa_test_123",
        },
    )
    assert top_up_response.status_code == 200, top_up_response.text

    send_response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            # str(), not the bare int -- confirmed from transactions.py's
            # own comment: "receiver_id arrives as str on the wire
            # (schema), but the DB column is Integer".
            "receiver_id": str(receiver_id),
            "amount": "10.00",
            "currency": "USD",
        },
    )
    assert send_response.status_code == 200, send_response.text
    transaction_id = send_response.json()["transaction_id"]

    # --- the actual assertion: a raw UPDATE against transaction_audit_logs must be rejected ---
    from app.models.transaction_audit_log import TransactionAuditLog

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TransactionAuditLog)
            .where(TransactionAuditLog.transaction_id == transaction_id)
            .order_by(TransactionAuditLog.id.asc())
        )
        audit_log_rows = result.scalars().all()
        assert len(audit_log_rows) >= 1, "send_money should have written at least one audit log row"

        target_row = audit_log_rows[0]
        original_action = target_row.action
        # Captured as a plain int now -- target_row itself will be
        # expired after the rollback() below (SQLAlchemy expires all
        # objects in a session on rollback, regardless of
        # expire_on_commit=False, which only suppresses expiration on
        # commit), and this session closes at the end of this `async
        # with` block. Accessing target_row.id later, in a NEW session,
        # would raise DetachedInstanceError -- a plain int has no such
        # lifecycle.
        target_row_id = target_row.id

        with pytest.raises(DBAPIError):
            await db.execute(
                text("UPDATE transaction_audit_logs SET action = :new_action WHERE id = :row_id"),
                {"new_action": "tampered", "row_id": target_row_id},
            )
            await db.commit()

        # A failed statement leaves the session's transaction aborted --
        # must roll back before the session can be used again.
        await db.rollback()

    # --- confirm the row is genuinely unchanged, not just that an exception fired ---
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TransactionAuditLog).where(TransactionAuditLog.id == target_row_id)
        )
        unchanged_row = result.scalar_one()
        assert unchanged_row.action == original_action
