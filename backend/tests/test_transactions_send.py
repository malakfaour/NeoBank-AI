"""
DEVATTECH-72 tests.

What's actually covered here: the pure idempotency-hashing logic
(app.core.redis.hash_idempotency_key), following the same plain
function-test style as test_account_utils.py — no fixtures needed.

What's NOT covered here, and why: a full send_money endpoint test needs
an authenticated async HTTP client + an async DB session against a real
schema (SELECT ... FOR UPDATE, JSONB audit metadata, wallet locking).
conftest.py currently points DATABASE_URL at SQLite for tests, and this
repo doesn't yet have an async client/DB fixture I've been shown. SQLite
does not support FOR UPDATE row locking the same way Postgres does, so
even with a fixture, a SQLite-backed test could not verify the locking
behavior this ticket depends on — it would only prove the happy path,
which would be misleading to report as "tested."

TODO: once there's an async test-client + Postgres-backed (or testcontainers)
DB fixture in this repo, add:
  - test_send_money_happy_path (debit sender, credit receiver, status=completed)
  - test_send_money_insufficient_balance (400)
  - test_send_money_self_transfer_rejected (400)
  - test_send_money_missing_wallet (404)
  - test_send_money_idempotent_replay (same header -> same cached response,
    only one row inserted)
  - test_send_money_concurrent_duplicate (simulate the Redis-race path ->
    expect 409 from the DB unique-constraint fallback)
  - test_send_money_audit_log_created (one TransactionAuditLog row, action="created")
"""
from app.core.redis import hash_idempotency_key


def test_hash_idempotency_key_deterministic():
    key1 = hash_idempotency_key(user_id=1, raw_key="abc-123")
    key2 = hash_idempotency_key(user_id=1, raw_key="abc-123")
    assert key1 == key2


def test_hash_idempotency_key_scoped_per_user():
    # Same raw key, different users -> must not collide.
    key_user_1 = hash_idempotency_key(user_id=1, raw_key="abc-123")
    key_user_2 = hash_idempotency_key(user_id=2, raw_key="abc-123")
    assert key_user_1 != key_user_2


def test_hash_idempotency_key_different_raw_keys_differ():
    key1 = hash_idempotency_key(user_id=1, raw_key="abc-123")
    key2 = hash_idempotency_key(user_id=1, raw_key="xyz-999")
    assert key1 != key2


def test_hash_idempotency_key_fits_column_length():
    # Transaction.idempotency_key is String(100) — sha256 hex digest is 64
    # chars, well within that, but pin it so a future hash-function swap
    # can't silently break the unique constraint.
    key = hash_idempotency_key(user_id=1, raw_key="abc-123")
    assert len(key) <= 100
