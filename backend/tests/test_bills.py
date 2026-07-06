"""
NBL-110 tests.

Following the same convention as test_transactions_send.py and
test_transactions_history.py: do NOT import app.api.v1.endpoints.bills
directly (it imports app.db.session, which constructs an async
SQLAlchemy engine against DATABASE_URL -- fails under the SQLite test
config, since that needs sqlite+aiosqlite, not plain pysqlite).

What's actually covered here:
  - BillType / BillPaymentStatus enum values (app.models.bill_payment only
    imports app.db.base, not app.db.session -- safe to import directly).
  - biller_client.call_mock_biller()'s 80/20 simulation, over many trials
    (app.services.biller_client imports httpx + app.core.config only --
    no app.db.session in its import chain either).
  - wallet_locking.lock_and_debit_wallet()'s missing-wallet and
    insufficient-balance paths, using an AsyncMock in place of a real
    AsyncSession/DB. This is genuinely DB-free (no real Postgres/SQLite
    connection involved), not a shortcut -- the function's logic (raise
    ValueError for either case) is fully exercised.

What's NOT covered here, and why: the two endpoints themselves
(POST /bills/pay, GET /bills/history) need an authenticated async HTTP
client + a real async DB session (wallet locking under contention, the
bill_payments/transactions FK relationship, pagination against real
rows). That requires a Postgres-backed (or testcontainers) async fixture
that doesn't exist yet in this repo -- same gap as every other endpoint
test file in this codebase.

TODO: once there's an async test-client + Postgres-backed DB fixture:
  - test_pay_bill_happy_path (debits wallet, creates bill_payment +
    transaction rows, returns 200)
  - test_pay_bill_wallet_not_owned_by_caller (404)
  - test_pay_bill_currency_mismatch (400)
  - test_pay_bill_insufficient_balance_before_biller_call (400, biller
    never called -- assert call_mock_biller was NOT invoked)
  - test_pay_bill_biller_failure_writes_failed_bill_payment_row (502,
    no wallet debit, no transaction row created)
  - test_pay_bill_balance_conflict_after_biller_success (500, logged,
    biller succeeded but balance insufficient at lock time)
  - test_pay_bill_enqueues_score_transaction_after_commit (assert
    score_transaction.delay called with the committed transaction's id,
    AFTER the commit -- not before)
  - test_pay_bill_invalidates_balance_cache_on_success
  - test_get_bill_history_pagination
  - test_get_bill_history_only_returns_callers_own_payments
"""
import random
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bill_payment import BillPaymentStatus, BillType
from app.services.biller_client import SUCCESS_RATE, call_mock_biller
from app.services.wallet_locking import lock_and_debit_wallet


def test_bill_type_matches_ticket_spec():
    assert {member.value for member in BillType} == {"ogero", "edl", "water", "mobile_topup"}


def test_bill_payment_status_values():
    assert {member.value for member in BillPaymentStatus} == {"success", "failed"}


@pytest.mark.asyncio
async def test_call_mock_biller_success_rate_within_expected_range():
    """
    Statistical test over many trials -- not a guarantee of exactly 80%,
    but confirms the simulation is centered near SUCCESS_RATE and not,
    say, always-succeed or always-fail due to a logic error.
    """
    random.seed(42)
    trials = 500
    successes = sum(
        1 for _ in range(trials)
        if (await call_mock_biller("ogero", "REF-1", Decimal("10.00"))).success
    )
    observed_rate = successes / trials
    assert abs(observed_rate - SUCCESS_RATE) < 0.08  # generous tolerance for randomness


@pytest.mark.asyncio
async def test_call_mock_biller_failure_includes_error_message():
    random.seed(1)  # seed chosen so at least one failure occurs in a few calls
    results = [await call_mock_biller("edl", "REF-2", Decimal("5.00")) for _ in range(20)]
    failures = [r for r in results if not r.success]
    assert failures, "expected at least one simulated failure in 20 trials"
    assert failures[0].biller_error is not None


@pytest.mark.asyncio
async def test_lock_and_debit_wallet_raises_on_missing_wallet():
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None

    fake_db = AsyncMock()
    fake_db.execute.return_value = fake_result

    with pytest.raises(ValueError, match="not found"):
        await lock_and_debit_wallet(fake_db, wallet_id=999, amount=Decimal("10.00"))


@pytest.mark.asyncio
async def test_lock_and_debit_wallet_raises_on_insufficient_balance():
    fake_wallet = MagicMock()
    fake_wallet.balance = Decimal("5.00")

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_wallet

    fake_db = AsyncMock()
    fake_db.execute.return_value = fake_result

    with pytest.raises(ValueError, match="Insufficient balance"):
        await lock_and_debit_wallet(fake_db, wallet_id=1, amount=Decimal("10.00"))

    # Balance must be untouched when the debit is rejected.
    assert fake_wallet.balance == Decimal("5.00")


@pytest.mark.asyncio
async def test_lock_and_debit_wallet_debits_on_sufficient_balance():
    fake_wallet = MagicMock()
    fake_wallet.balance = Decimal("100.00")

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_wallet

    fake_db = AsyncMock()
    fake_db.execute.return_value = fake_result

    updated_wallet = await lock_and_debit_wallet(fake_db, wallet_id=1, amount=Decimal("30.00"))

    assert updated_wallet.balance == Decimal("70.00")
