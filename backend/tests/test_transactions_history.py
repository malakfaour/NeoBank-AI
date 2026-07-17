"""
DEVATTECH-73 tests.

These import ONLY from app.utils.transaction_query_utils — not from
app.api.v1.endpoints.transactions. Importing the endpoint module pulls in
app.db.session, which constructs an async SQLAlchemy engine
(create_async_engine) against DATABASE_URL. Under the test environment
(conftest.py sets DATABASE_URL to sqlite:///./test_neobank.db), that URL
has no async driver configured — it would need sqlite+aiosqlite, not
plain pysqlite — so importing the endpoint module fails at import time,
before any test even runs.

What's actually covered here: the pure helper functions (pagination math,
month-string parsing), same plain function-test style as
test_account_utils.py.

What's NOT covered here, and why: the three endpoints themselves
(list/detail/summary) need an authenticated async HTTP client + an async
DB session against real data (joins to `users` for counterparty_name,
GROUP BY aggregation, EXTRACT(year/month FROM ...) date filtering). That
requires a Postgres-backed (or testcontainers) async fixture that doesn't
exist yet in this repo.

TODO: once there's an async test-client + Postgres-backed DB fixture in
this repo, add:
  - test_list_transactions_pagination (page/page_size respected, total/total_pages correct)
  - test_list_transactions_filters_by_type_send_and_receive
  - test_list_transactions_type_topup_bill_exchange_returns_empty
  - test_list_transactions_filters_by_date_range
  - test_list_transactions_filters_by_category_and_currency
  - test_list_transactions_counterparty_name_resolved_correctly
  - test_list_transactions_flagged_reflects_status
  - test_get_transaction_detail_includes_audit_logs
  - test_get_transaction_detail_404_for_non_participant
  - test_get_transaction_summary_groups_by_category_and_currency
  - test_get_transaction_summary_only_counts_outgoing_as_sender
  - test_get_transaction_summary_invalid_month_format_400
"""
import pytest

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency
from app.utils.transaction_query_utils import compute_total_pages, parse_summary_month


def test_compute_total_pages_exact_division():
    assert compute_total_pages(total=40, page_size=20) == 2


def test_compute_total_pages_rounds_up():
    assert compute_total_pages(total=41, page_size=20) == 3


def test_compute_total_pages_zero_total():
    assert compute_total_pages(total=0, page_size=20) == 0


def test_compute_total_pages_single_page():
    assert compute_total_pages(total=5, page_size=20) == 1


def test_parse_summary_month_valid():
    year, month = parse_summary_month("2026-07")
    assert (year, month) == (2026, 7)


def test_parse_summary_month_invalid_format_raises():
    with pytest.raises(ValueError):
        parse_summary_month("not-a-month")


def test_parse_summary_month_invalid_month_number_raises():
    with pytest.raises(ValueError):
        parse_summary_month("2026-13")




# --- NBL-411: top-up display in history/detail/summary ---
#
# The module docstring above says importing app.api.v1.endpoints.transactions
# fails under tests because DATABASE_URL lacks an async driver. That's no
# longer true: conftest.py (see TEST_DB_URL) sets DATABASE_URL to
# sqlite+aiosqlite, and test_money_movement.py already imports and exercises
# this same module successfully via the async client. These tests use that
# same client fixture rather than the plain-function style above, since they
# need real HTTP requests against real endpoints, not just pure helpers.
#
# Scope: these tests cover only what NBL-411 changed (top-up type display
# and its exclusion from spend summary) -- the broader TODO list in the
# docstring above (pagination, date filters, etc.) is still open and belongs
# to DEVATTECH-73, not this ticket.

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


async def _get_user_and_wallet(email: str) -> tuple[User, Wallet]:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        wallet = (
            await session.execute(
                select(Wallet).where(Wallet.user_id == user.id, Wallet.currency == WalletCurrency.USD)
            )
        ).scalar_one()
        return user, wallet


async def _top_up(client, access_token: str, wallet_id: int, amount: str) -> dict:
    # DEVATTECH-125: X-Idempotency-Key is now required on this endpoint.
    response = await client.post(
        "/api/v1/accounts/top-up",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Idempotency-Key": uuid4().hex,
        },
        json={"wallet_id": wallet_id, "amount": amount, "card_token": "tok_visa_test_123"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
async def test_topup_appears_as_topup_type_in_list_transactions(client):
    tokens = await _register_user(client, "history-topup")
    _, wallet = await _get_user_and_wallet(tokens["email"])

    await _top_up(client, tokens["access_token"], wallet.id, "88.00")

    response = await client.get(
        "/api/v1/transactions",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]

    topup_items = [i for i in items if i["type"] == "topup"]
    assert len(topup_items) == 1
    assert Decimal(topup_items[0]["amount"]) == Decimal("88.00")
    assert topup_items[0]["counterparty_name"] is None


@pytest.mark.anyio
async def test_list_transactions_type_topup_filter_returns_real_rows(client):
    tokens = await _register_user(client, "history-filter")
    _, wallet = await _get_user_and_wallet(tokens["email"])

    await _top_up(client, tokens["access_token"], wallet.id, "33.00")

    response = await client.get(
        "/api/v1/transactions?type=topup",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]

    assert len(items) == 1
    assert items[0]["type"] == "topup"


@pytest.mark.anyio
async def test_get_transaction_detail_for_topup_has_no_counterparty(client):
    tokens = await _register_user(client, "history-detail")
    _, wallet = await _get_user_and_wallet(tokens["email"])

    await _top_up(client, tokens["access_token"], wallet.id, "17.00")

    list_response = await client.get(
        "/api/v1/transactions",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    transaction_id = list_response.json()["items"][0]["id"]

    detail_response = await client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()

    assert detail["type"] == "topup"
    assert detail["counterparty_name"] is None
    assert detail["sender_id"] == detail["receiver_id"]


@pytest.mark.anyio
async def test_summary_excludes_topups_from_spend_total(client):
    tokens = await _register_user(client, "history-summary")
    _, wallet = await _get_user_and_wallet(tokens["email"])

    # A large top-up that would badly skew the summary if wrongly counted.
    await _top_up(client, tokens["access_token"], wallet.id, "500.00")

    month = date.today().strftime("%Y-%m")
    response = await client.get(
        f"/api/v1/transactions/summary?month={month}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    summary_items = response.json()["summary"]

    topup_rows = [row for row in summary_items if row["category"] == "TopUp"]
    assert topup_rows == []
