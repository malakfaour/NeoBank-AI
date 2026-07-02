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
