# NeoBank Lebanon - Engineering Rules

Every rule here exists because we broke it once. Read before every task; AI sessions must be given this file.

## 1. Git & branches

- Branch from **latest develop** the morning you start: `git fetch origin && git checkout -b feature/<name> origin/develop`. Pull develop again before opening the PR.
- One PR per task-cluster, one commit per logical change. Real commit messages (`fix(exchange): ...`) - we once merged a commit literally named "Fix: your message here".
- Never push to `develop` or `main` directly. Never merge your own PR without 1 approval + all 4 CI checks green.
- Never edit or rebase commits that are already on `develop`.

## 2. Migrations

We once had three Alembic heads and a migration that dropped another member's tables.

- Before creating a migration and before pushing: `cd backend && python scripts/check_single_alembic_head.py` (CI runs this too - it will block you anyway).
- Exactly one new revision per PR, `down_revision` = the current single head. If `develop` moved and your migration is stale, re-parent it - do not merge heads yourself without telling the team.
- **Never commit raw `alembic revision --autogenerate` output.** Autogenerate diffs against your local DB and will emit drops of other members' tables/columns. This destroyed `user_sessions` + `passcode_hash` once. Delete every operation that touches a table you don't own.
- No `drop_table` / `drop_column` in `upgrade()` unless the whole team signed off in the PR description.
- Postgres-only DDL (triggers, JSONB ops) must be guarded: `if op.get_bind().dialect.name == "postgresql":` - the test suite migrates a SQLite DB.
- New JSON columns: use `JSONB().with_variant(JSON, "sqlite")` (see `transaction_audit_log.py`), never bare `JSONB`.
- Model change without a migration, or migration without a model change = rejected PR. They ship together.

## 3. Async vs sync DB

We shipped a Celery task calling async services with a sync session and every call crashed.

- **API endpoints:** `async def` + `AsyncSession` via `Depends(get_db)` / `get_async_db`. Always `await` your queries. Never import `SyncSessionLocal` in an endpoint.
- **Celery tasks:** plain `def` + `SyncSessionLocal` from `app/db/sync_session.py`. Never call async service functions from a task - not even with `asyncio.run` (the async engine is bound to the app's event loop). If a service you need is async-only, add a `_sync` twin next to it (pattern: `append_audit_sync`, `check_fraud_rules_sync` in `app/services/`).
- Never call a Celery task as a plain function from an endpoint - that runs blocking DB + ML inference inside the event loop and stalls every request. This happened with `score_transaction`. Always `.delay()`, always after `await db.commit()` so the worker can find the row.
- Wallet balances are never mutated without: `SELECT FOR UPDATE` (or via the shared debit/credit helper), a `transactions` row, an audit entry, and `invalidate_balance_cache(user_id)`.

## 4. Endpoints & API conventions

- Every router lives in `backend/app/api/v1/endpoints/` and is registered in `app/api/v1/router.py`. Nothing is mounted in `main.py` directly. All routes are automatically `/api/v1/...` - never hardcode the prefix inside a router.
- **Auth by default:** every endpoint takes `current_user: CurrentUser = Depends(get_current_user)` unless it is deliberately public (`login` / `register` / `refresh` / `health`). Identity comes from the token - never from a `user_id` query/body param. We shipped an unauthenticated top-up that let anyone credit any wallet.
- Ownership checks: any resource id from the client (`wallet_id`, `beneficiary_id`, ...) must be queried with `user_id == int(current_user.id)` in the `WHERE` clause.
- Admin/compliance endpoints: `Depends(require_role(UserRole.compliance_officer, UserRole.admin))`.
- Errors: raise `HTTPException` with the status codes agreed in the ticket. Recipient-lookup endpoints return `{exists: false}`, never `404` (account enumeration).
- Response shape = the ticket's contract. If you change a response the frontend reads, update the frontend (or file it with Lana) in the same PR. The login screen was broken for two sprints because backend and frontend disagreed on the payload.

## 5. Redis

- One client: `app/core/redis.py`. Helpers live there or in `app/core/cache_utils.py` - never create your own connection.
- Key naming: `feature:{scope}` - existing: `otp:{user_id}`, `balance:{user_id}`, `idem:{hash}`, `exchange:latest`, `topup_daily:{user_id}`. Follow the pattern, document new keys in the helper's docstring.
- Every key gets a TTL unless there is a written reason.
- Don't reimplement existing flows: OTP = `services/otp.py` (`verify_and_consume_otp` - someone hand-rolled a second OTP check once and it missed cleanup), rate limits = `services/rate_limiter.py`, idempotency = the Redis helpers.
- If your module does `from app.core.redis import redis_client`, add a matching patch line in `backend/tests/conftest.py`'s `mock_redis` fixture - otherwise your tests silently hit real Redis.

## 6. Celery

- Tasks live in `app/tasks/<feature>_tasks.py`, registered with the full name (`app.tasks.x_tasks.task_name`). Scheduled jobs go in `celery_app.py`'s `beat_schedule` (the `celery-beat` compose service runs them).
- A task must be re-runnable: fetch fresh state by id, tolerate the row being missing, and on exception leave the record in a safe state (fraud scoring flags for manual review on failure - copy that pattern), then re-raise.
- External calls (Groq, Twilio, S3, gateways) always go through `httpx` with a timeout, and are always mocked in tests - CI has no network.

## 7. Shared services

Import, don't duplicate. Single owners; if your feature needs it, import it:

- Wallet creation/IBAN: `services/account_service.create_wallets_for_user` (register once bypassed this - every user had `NULL` IBANs and transfers by IBAN were impossible).
- Notifications: `services/notifications.notify()`. Audit: `services/audit_log`. OTP: `services/otp`. Fraud threshold: import `FRAUD_FLAG_THRESHOLD` from `services/fraud_scoring` - never write `0.75`.
- Enums defined once (`UserRole` lives in `models/user.py`; schemas re-export it).
- ML training code lives in top-level `ml/` only. Model artifacts load from `backend/app/ml_models/`.

## 8. Dependencies & environment

- `backend/requirements.txt` and `ml/requirements.txt`: every line pinned `==`. Shared packages (`numpy`, `xgboost`, `scikit-learn`, `pandas`, `celery`) must be identical in both files - models pickled in one env are unpickled in the other. Before pinning, check the resolver locally (`pip install -r` in a venv): `numpy` is capped by `opencv` (`<2.3`).
- New env var => add to `app/core/config.py` and `.env.example` in the same commit, with the exact same name. A test once set `SMTP_USER` while config read `SMTP_USERNAME` and it was silently ignored.
- New service (beat, inference container) => update `docker-compose.yml` + verify `docker compose config`.
- Never add to `.gitignore` without checking what it already matches (`git check-ignore -v <path>`) - a Python-template `lib/` rule silently kept `frontend/lib/axios.ts` out of the repo and the frontend couldn't build from a clean clone.

## 9. Tests & CI

This is the definition of done. Before every push, from `backend/`:

1. `python -m pytest tests/ -q` - all green, no new skips
2. `python scripts/check_single_alembic_head.py`
3. If you touched frontend: `cd frontend && npm run lint && npm run build`

- New endpoint => endpoint-level test (`httpx` client fixture, style of `test_money_movement.py`): happy path, auth rejected, ownership rejected, one failure path. Mock only the external boundary (`.delay`, `httpx`, Groq) - never the DB or your own service.
- A red CI check is yours to fix before anything else. Never merge on red, never `--passWithNoTests`, never delete a failing test to pass.

## 10. Frontend rules

- All API calls through the shared `api` instance (`frontend/lib/axios.ts`). Paths are relative (`/auth/login`) - the `baseURL` already contains `/api/v1`; never hardcode host or version.
- Before wiring a call, verify the endpoint exists and its exact request/response shape in the backend code (or `/docs`) - we shipped four screens calling endpoints that didn't exist.
- Tokens/user only via `useAuthStore`. Components defined at module level, never inside a render body.
