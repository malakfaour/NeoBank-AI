"""
Postgres E2E money-path CI job -- the full AC path:
register -> top-up -> send -> fraud score -> audit -> reversal.

Design decisions worth calling out explicitly:

1. "score" step: calls score_transaction(transaction_id) directly as a
   plain function call, NOT .delay() -- per the approved "option 3"
   design from earlier in this ticket. Celery task objects remain
   directly callable; this executes the real task body -- real
   SyncSessionLocal, real Isolation Forest scoring (cold-start users,
   which this test's freshly-registered sender always is), real status
   update, real audit write -- entirely in-process, no broker needed.

2. "reversal" step: resolve_flag (admin.py) requires the transaction to
   already be status=flagged -- but the Isolation Forest's actual
   flag/no-flag outcome for any specific synthetic transaction is not
   something this test can predict or control (it depends on the
   trained model's stats vs. this transaction's computed features).
   Rather than make this test flaky (sometimes able to test reversal,
   sometimes not, depending on the real scoring outcome), the test
   scores the transaction for real first (proving the actual scoring
   path executes correctly, whatever its outcome), then -- ONLY if the
   natural outcome was not already "flagged" -- performs one minimal,
   explicitly-justified direct DB write to set status=flagged. This
   mirrors an established pattern already used elsewhere in this
   codebase (a _force_flag_transaction-style helper, from earlier
   admin-endpoint test work) -- not a new invention. This does NOT
   touch fraud_score, scoring_model, resolve_flag, send_money, or
   score_transaction's logic -- only sets up a deterministic starting
   state for testing the reversal step specifically.

3. Wallet lookup and reviewer-role setup use the same direct, read-only
   DB query pattern already approved in test_audit_log_append_only.py --
   no reviewed endpoint exposes a wallet's numeric id, and JWT role
   claims are baked in at issuance time (confirmed against the real
   dependencies.py earlier in this project), so a fresh login is
   required after promoting a role in the DB.

4. UNVERIFIED ASSUMPTION, flagged explicitly: this file imports
   app.tasks.transaction_tasks, which imports app.celery_app.
   app/celery_app.py's actual content has not been reviewed in this
   ticket. Assumes standard Celery behavior -- constructing a Celery()
   app object does not itself attempt a broker connection; only
   .delay()/.apply_async() or a running worker does. If that assumption
   is wrong, this import could fail or hang without a reachable broker.

No production file is modified. No dataset is required -- the
Isolation Forest model used for scoring is provided by this suite's own
provide_isolation_forest_model fixture (conftest.py), since
isolation_forest.pkl was moved to S3 by DEVATTECH-143 and is not
available in CI (no real S3/MinIO configured there, by design).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select


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
    assert response.status_code == 200, response.text

    # Registration now correctly stops before authentication until the email
    # OTP is verified. OTP delivery is outside this money-path test's scope,
    # so verify the fixture user directly and use the real login endpoint to
    # establish the session consumed by the remainder of this E2E path.
    from app.db.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()


async def _register_reviewer(client, label: str) -> dict:
    """
    Compliance/admin role required for resolve_flag (admin.py:
    require_role(UserRole.compliance_officer, UserRole.admin)). Register
    as a normal customer, promote the role directly in the DB, then log
    in again so the fresh token actually carries the new role.
    """
    password = "TestPass123"
    tokens = await _register_user(client, label, password=password)
    email = tokens["user"]["email"]

    from app.db.session import AsyncSessionLocal
    from app.models.user import User, UserRole

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.role = UserRole.compliance_officer
        await db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()


@pytest.mark.postgres
async def test_full_money_path_register_topup_send_score_audit_reversal(
    client, stub_fraud_scoring, provide_isolation_forest_model
):
    # --- register ---
    sender = await _register_user(client, "e2e-sender")
    receiver = await _register_user(client, "e2e-receiver")
    sender_id = sender["user"]["id"]
    receiver_id = receiver["user"]["id"]

    from app.db.session import AsyncSessionLocal
    from app.models.wallet import Wallet, WalletCurrency

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Wallet).where(
                Wallet.user_id == sender_id,
                Wallet.currency == WalletCurrency.USD,
            )
        )
        sender_wallet = result.scalar_one()

    # --- top-up ---
    top_up_response = await client.post(
        "/api/v1/accounts/top-up",
        headers={
        "Authorization": f"Bearer {sender['access_token']}",
        "X-Idempotency-Key": uuid4().hex,
        },
        json={
            "wallet_id": sender_wallet.id,
            "amount": "500.00",
            "payment_method_id": "pm_card_visa_test_123",
        },
    )
    assert top_up_response.status_code == 200, top_up_response.text
    assert Decimal(str(top_up_response.json()["new_balance"])) == Decimal("500.00")

    # --- send ---
    send_response = await client.post(
        "/api/v1/transactions/send",
        headers={
            "Authorization": f"Bearer {sender['access_token']}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={
            # str(), not the bare int -- confirmed from transactions.py's
            # own comment (see test_audit_log_append_only.py for the
            # same, already-approved reasoning).
            "receiver_id": str(receiver_id),
            "amount": "50.00",
            "currency": "USD",
        },
    )
    assert send_response.status_code == 200, send_response.text
    send_body = send_response.json()
    transaction_id = send_body["transaction_id"]
    assert send_body["status"] == "completed"  # send_money always completes optimistically first
    assert stub_fraud_scoring == [transaction_id]  # confirms send_money DID attempt to dispatch scoring

    balance_response = await client.get(
        "/api/v1/accounts/balance",
        headers={"Authorization": f"Bearer {sender['access_token']}"},
    )
    assert balance_response.status_code == 200, balance_response.text
    usd_balance = next(b for b in balance_response.json()["balances"] if b["currency"] == "USD")
    assert Decimal(str(usd_balance["balance"])) == Decimal("450.00")

    # --- score (real task body, direct synchronous call -- not .delay()) ---
    from app.tasks.transaction_tasks import score_transaction

    score_result = score_transaction(transaction_id)
    assert score_result["model"] == "isolation_forest"  # freshly-registered sender = cold-start

    from app.models.transaction import Transaction, TransactionStatus

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
        scored_transaction = result.scalar_one()
        assert scored_transaction.fraud_score is not None
        assert scored_transaction.scoring_model == "isolation_forest"
        assert scored_transaction.status in (TransactionStatus.completed, TransactionStatus.flagged)

        # Deterministic setup for the reversal step below -- see module
        # docstring point 2. Only forces status if the real scoring
        # outcome didn't already flag it. Also writes the same
        # "status_changed" audit entry score_transaction itself would
        # have written for a natural completed->flagged transition
        # (see transaction_tasks.py), via the existing shared
        # append_audit service -- not a new audit mechanism -- so the
        # audit trail stays representationally consistent with what a
        # real flag transition produces, even though this specific
        # transition was forced for test determinism rather than
        # produced by the scoring model itself.
        if scored_transaction.status != TransactionStatus.flagged:
            scored_transaction.status = TransactionStatus.flagged
            await db.commit()

            from app.services.audit_log import append_audit

            await append_audit(
                db,
                transaction_id=transaction_id,
                action="status_changed",
                actor_id=sender_id,
                metadata={"from": "completed", "to": "flagged"},
            )

    # --- audit ---
    from app.models.transaction_audit_log import TransactionAuditLog

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TransactionAuditLog)
            .where(TransactionAuditLog.transaction_id == transaction_id)
            .order_by(TransactionAuditLog.id.asc())
        )
        audit_actions = [row.action for row in result.scalars().all()]

    assert "created" in audit_actions
    assert "fraud_scoring_queued" in audit_actions
    assert "fraud_scored" in audit_actions

    # --- reversal ---
    reviewer = await _register_reviewer(client, "e2e-reviewer")

    resolve_response = await client.post(
        f"/api/v1/admin/transactions/{transaction_id}/resolve-flag",
        headers={"Authorization": f"Bearer {reviewer['access_token']}"},
        json={"resolution": "confirmed_fraud", "reviewer_note": "Postgres E2E test reversal"},
    )
    assert resolve_response.status_code == 200, resolve_response.text
    resolve_body = resolve_response.json()
    assert resolve_body["resolution"] == "confirmed_fraud"
    assert resolve_body["new_status"] == "reversed"

    final_balance_response = await client.get(
        "/api/v1/accounts/balance",
        headers={"Authorization": f"Bearer {sender['access_token']}"},
    )
    assert final_balance_response.status_code == 200, final_balance_response.text
    final_usd_balance = next(
        b for b in final_balance_response.json()["balances"] if b["currency"] == "USD"
    )
    assert Decimal(str(final_usd_balance["balance"])) == Decimal("500.00")  # restored to pre-send balance

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TransactionAuditLog)
            .where(TransactionAuditLog.transaction_id == transaction_id)
            .order_by(TransactionAuditLog.id.asc())
        )
        final_audit_actions = [row.action for row in result.scalars().all()]

    assert "reversed" in final_audit_actions
