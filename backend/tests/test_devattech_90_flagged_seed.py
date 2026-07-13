"""
DEVATTECH-90, AC #3: seeded flagged transactions must appear in
GET /admin/flagged-transactions.

New, standalone test file -- does not modify any existing test file.
Seeds transactions directly into the test DB (matching
ENGINEERING_RULES.md section 9's convention: "mock only the external
boundary... never the DB"), covering both independent flagging paths
the endpoint's filter checks (see admin.py's get_flagged_transactions
docstring): status == "flagged", and rule_triggered == True with
status left as "completed" -- these are deliberately different rows so
this test proves the OR-condition, not just one branch of it.

Does not touch backend/seed.py.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.transaction import Transaction, TransactionCurrency, TransactionStatus
from app.models.user import User, UserRole


async def _register_user(client, label: str, password: str = "TestPass123") -> dict:
    suffix = uuid4().hex[:10]
    email = f"{label.lower()}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96170{suffix[:6]}",
            "password": password,
        },
    )
    assert response.status_code == 200, response.text
    return {**response.json(), "email": email, "password": password}


async def _login(client, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _promote_to_role(email: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        user.role = role
        await session.commit()


async def _register_reviewer(client, label: str, role: UserRole) -> dict:
    """Register a customer, promote to the given role in the DB, then log
    in again so the fresh token actually carries that role (JWT role
    claims are baked in at issuance time -- see prior DEVATTECH-111 test
    notes)."""
    tokens = await _register_user(client, label)
    await _promote_to_role(tokens["email"], role)
    return await _login(client, tokens["email"], tokens["password"])


async def _get_user(email: str) -> User:
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one()


async def _seed_flagged_transaction(
    sender_id: int, receiver_id: int, *, status: TransactionStatus, rule_triggered: bool, amount: str
) -> int:
    """Inserts one transaction row directly, bypassing the API/Celery
    scoring pipeline entirely -- this is seeding test fixture data, not
    exercising send_money or score_transaction, which are out of scope
    for this ticket."""
    async with AsyncSessionLocal() as session:
        transaction = Transaction(
            sender_id=sender_id,
            receiver_id=receiver_id,
            amount=Decimal(amount),
            currency=TransactionCurrency.USD,
            status=status,
            rule_triggered=rule_triggered,
            idempotency_key=f"devattech90-seed:{uuid4().hex}",
        )
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)
        return transaction.id


@pytest.mark.anyio
async def test_seeded_flagged_transactions_appear_in_flagged_transactions_endpoint(client):
    sender_tokens = await _register_user(client, "devattech90-sender")
    receiver_tokens = await _register_user(client, "devattech90-receiver")
    sender = await _get_user(sender_tokens["email"])
    receiver = await _get_user(receiver_tokens["email"])

    # Row 1: flagged via status == "flagged" (the scoring-exception
    # fallback path).
    status_flagged_id = await _seed_flagged_transaction(
        sender.id, receiver.id,
        status=TransactionStatus.flagged, rule_triggered=False, amount="120.00",
    )

    # Row 2: flagged via rule_triggered == True, with status left as
    # "completed" -- the second, independent flagging signal the
    # endpoint's OR-condition checks (DEVATTECH-84/87).
    rule_triggered_id = await _seed_flagged_transaction(
        sender.id, receiver.id,
        status=TransactionStatus.completed, rule_triggered=True, amount="75.00",
    )

    reviewer_tokens = await _register_reviewer(
        client, "devattech90-reviewer", UserRole.compliance_officer
    )

    response = await client.get(
        "/api/v1/admin/flagged-transactions",
        headers={"Authorization": f"Bearer {reviewer_tokens['access_token']}"},
        params={"page_size": 100},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    returned_ids = {item["id"] for item in body["items"]}

    assert status_flagged_id in returned_ids
    assert rule_triggered_id in returned_ids
