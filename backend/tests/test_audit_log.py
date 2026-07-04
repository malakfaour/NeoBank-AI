"""
DEVATTECH-74 tests.

Covers: pure Pydantic schema validation for AuditLogEntry /
AuditTrailResponse. app.schemas.audit_log imports nothing from app.db,
app.api, or app.models, so this is safe to import under the SQLite test
environment without triggering the async-engine construction issue seen
in earlier tickets.

NOT covered here, and why: GET /admin/transactions/{id}/audit-trail
(RBAC-gated route, real transaction + audit rows) and the new
append_audit() call ordering inside send_money both need an authenticated
async HTTP client + an async Postgres-backed DB session. That fixture
doesn't exist yet in this repo — same gap flagged in the DEVATTECH-72/73
test files.

TODO: once there's an async test-client + Postgres-backed DB fixture:
  - test_audit_trail_returns_entries_ordered_by_timestamp_asc
  - test_audit_trail_404_for_nonexistent_transaction
  - test_audit_trail_403_for_non_admin_role
  - test_send_money_writes_four_audit_rows_in_order
    (created, fraud_scored, status_changed, flagged/completed)
  - test_send_money_created_event_has_no_fraud_score_key
  - test_send_money_status_changed_metadata_reflects_transition
"""
from datetime import datetime, timezone

from app.schemas.audit_log import AuditLogEntry, AuditTrailResponse


def test_audit_log_entry_accepts_valid_data():
    entry = AuditLogEntry(
        id=1,
        action="created",
        actor_id=42,
        timestamp=datetime.now(timezone.utc),
        metadata={"amount": "100.00", "currency": "USD"},
    )
    assert entry.action == "created"
    assert entry.metadata["currency"] == "USD"


def test_audit_log_entry_allows_null_actor_and_metadata():
    entry = AuditLogEntry(
        id=2,
        action="status_changed",
        actor_id=None,
        timestamp=datetime.now(timezone.utc),
        metadata=None,
    )
    assert entry.actor_id is None
    assert entry.metadata is None


def test_audit_trail_response_holds_ordered_entries():
    entries = [
        AuditLogEntry(
            id=1, action="created", actor_id=1,
            timestamp=datetime(2026, 7, 1, 10, 0, 0), metadata=None,
        ),
        AuditLogEntry(
            id=2, action="fraud_scored", actor_id=1,
            timestamp=datetime(2026, 7, 1, 10, 0, 1), metadata=None,
        ),
        AuditLogEntry(
            id=3, action="status_changed", actor_id=1,
            timestamp=datetime(2026, 7, 1, 10, 0, 2), metadata=None,
        ),
        AuditLogEntry(
            id=4, action="completed", actor_id=1,
            timestamp=datetime(2026, 7, 1, 10, 0, 3), metadata=None,
        ),
    ]
    trail = AuditTrailResponse(transaction_id=99, entries=entries)
    assert trail.transaction_id == 99
    assert [e.action for e in trail.entries] == [
        "created", "fraud_scored", "status_changed", "completed",
    ]
