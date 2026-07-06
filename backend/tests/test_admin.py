"""
NBL-111 tests.

Following the same convention as test_bills.py, test_transactions_send.py,
and test_transactions_history.py: do NOT import
app.api.v1.endpoints.admin directly (it imports app.db.session, which
constructs an async SQLAlchemy engine against DATABASE_URL -- fails under
the SQLite test config, since that needs sqlite+aiosqlite, not plain
pysqlite).

What's actually covered here:
  - FraudResolutionType enum values (app.models.fraud_resolution only
    imports app.db.base, not app.db.session -- safe to import directly).
  - ResolveFlagRequest's Literal-based validation (app.schemas.admin is
    pure Pydantic, no DB imports at all).
  - ComplianceSummaryResponse's nested shape, matching the exact structure
    approved in review.
  - wallet_locking.lock_and_credit_wallet()'s missing-wallet and
    successful-credit paths, using an AsyncMock in place of a real
    AsyncSession/DB -- same approach as test_bills.py's coverage of its
    sibling function lock_and_debit_wallet(). Tested here rather than in
    test_bills.py since admin.py is lock_and_credit_wallet's only caller,
    and test_bills.py is already-approved work not being touched.

What's NOT covered here, and why: the three endpoints themselves
(GET /admin/flagged-transactions, POST /admin/transactions/{id}/resolve-flag,
GET /admin/reports/summary) need an authenticated async HTTP client + a
real async DB session (RBAC dependency, real transaction/wallet/
fraud_resolution rows, the reversal's cross-table update). That requires a
Postgres-backed (or testcontainers) async fixture that doesn't exist yet
in this repo -- same gap as every other endpoint test file in this
codebase.

TODO: once there's an async test-client + Postgres-backed DB fixture:
  - test_get_flagged_transactions_only_returns_status_flagged
  - test_get_flagged_transactions_pagination
  - test_get_flagged_transactions_includes_sender_name_and_email
  - test_get_flagged_transactions_403_for_customer_role
  - test_resolve_flag_legitimate_sets_status_completed
  - test_resolve_flag_confirmed_fraud_reverses_status_and_credits_sender
    (assert wallet balance restored to pre-transaction amount)
  - test_resolve_flag_confirmed_fraud_writes_audit_action_reversed
  - test_resolve_flag_legitimate_writes_audit_action_resolved_legitimate
  - test_resolve_flag_404_for_nonexistent_transaction
  - test_resolve_flag_400_for_non_flagged_transaction
  - test_resolve_flag_409_for_already_resolved_transaction
    (both the advisory pre-check path and the IntegrityError race path)
  - test_resolve_flag_500_when_sender_wallet_missing
  - test_resolve_flag_403_for_customer_role
  - test_compliance_summary_total_transactions_created
  - test_compliance_summary_currently_flagged_is_a_snapshot
    (a transaction flagged AND resolved within the same month is NOT
    counted -- documented limitation, should be asserted explicitly)
  - test_compliance_summary_resolutions_keyed_by_resolved_at
    (not by the underlying transaction's created_at)
  - test_compliance_summary_reversed_amount_grouped_by_currency
  - test_compliance_summary_invalid_month_format_400
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.models.fraud_resolution import FraudResolutionType
from app.schemas.admin import (
    ComplianceSummaryResponse,
    ResolutionCounts,
    ResolveFlagRequest,
    ReversedAmountByCurrency,
)
from app.services.wallet_locking import lock_and_credit_wallet


def test_fraud_resolution_type_values():
    assert {member.value for member in FraudResolutionType} == {"legitimate", "confirmed_fraud"}


def test_resolve_flag_request_accepts_valid_resolutions():
    ResolveFlagRequest(resolution="legitimate", reviewer_note="looks fine")
    ResolveFlagRequest(resolution="confirmed_fraud", reviewer_note=None)


def test_resolve_flag_request_rejects_invalid_resolution():
    with pytest.raises(ValidationError):
        ResolveFlagRequest(resolution="not_a_real_option")


def test_compliance_summary_response_shape():
    response = ComplianceSummaryResponse(
        month="2026-07",
        total_transactions_created=1450,
        currently_flagged_from_month=12,
        resolutions_this_month=ResolutionCounts(legitimate=8, confirmed_fraud=3),
        reversed_amount_by_currency=[
            ReversedAmountByCurrency(currency="USD", total_amount=Decimal("1240.50"), count=2),
            ReversedAmountByCurrency(currency="LBP", total_amount=Decimal("980000.00"), count=1),
        ],
    )
    assert response.resolutions_this_month.legitimate == 8
    assert response.resolutions_this_month.confirmed_fraud == 3
    assert len(response.reversed_amount_by_currency) == 2
    assert response.reversed_amount_by_currency[0].currency == "USD"


@pytest.mark.asyncio
async def test_lock_and_credit_wallet_raises_on_missing_wallet():
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None

    fake_db = AsyncMock()
    fake_db.execute.return_value = fake_result

    with pytest.raises(ValueError, match="not found"):
        await lock_and_credit_wallet(fake_db, wallet_id=999, amount=Decimal("10.00"))


@pytest.mark.asyncio
async def test_lock_and_credit_wallet_credits_correctly():
    fake_wallet = MagicMock()
    fake_wallet.balance = Decimal("50.00")

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_wallet

    fake_db = AsyncMock()
    fake_db.execute.return_value = fake_result

    updated_wallet = await lock_and_credit_wallet(fake_db, wallet_id=1, amount=Decimal("25.00"))

    assert updated_wallet.balance == Decimal("75.00")


@pytest.mark.asyncio
async def test_lock_and_credit_wallet_has_no_balance_ceiling():
    """
    Unlike lock_and_debit_wallet, there's no upper-bound check here --
    crediting can't fail on balance grounds. This test exists mainly to
    document that absence explicitly, not just by omission.
    """
    fake_wallet = MagicMock()
    fake_wallet.balance = Decimal("0.00")

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_wallet

    fake_db = AsyncMock()
    fake_db.execute.return_value = fake_result

    updated_wallet = await lock_and_credit_wallet(fake_db, wallet_id=1, amount=Decimal("999999.99"))

    assert updated_wallet.balance == Decimal("999999.99")
