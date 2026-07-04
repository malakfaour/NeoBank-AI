"""
Pure, DB-free helper functions for DEVATTECH-73's transaction history/
summary endpoints.

Pulled out into app/utils/ (matching the existing account_utils.py
convention) specifically so tests can import them without triggering
app.api.v1.endpoints.transactions' import chain, which loads
app.db.session and constructs an async SQLAlchemy engine — that fails
under the test environment's sqlite:// DATABASE_URL, which has no async
driver configured (would need sqlite+aiosqlite, not plain pysqlite).

This module imports nothing from app.db, app.models, or app.api — keep
it that way, or it stops being test-safe.
"""
from datetime import datetime


def compute_total_pages(total: int, page_size: int) -> int:
    """Pagination page-count math."""
    if total == 0:
        return 0
    return (total + page_size - 1) // page_size


def parse_summary_month(month: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' -> (year, month). Raises ValueError on bad format."""
    parsed = datetime.strptime(month, "%Y-%m")
    return parsed.year, parsed.month
