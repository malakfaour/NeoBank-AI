# Backend — Techtalks-Bank

FastAPI + SQLAlchemy (async) + Alembic + Celery backend for the Techtalks-Bank
neobank platform. Python 3.12.

See the [root README](../README.md) for the overall project, and
[`docs/ENGINEERING_RULES.md`](../docs/ENGINEERING_RULES.md) for the rules
this codebase is built against — read that before opening a PR.

## Prerequisites

- Python 3.12
- Docker + Docker Compose (for Postgres, Redis, and the other services)
- A `.env` file at the **repo root** (not inside `backend/`) — `app/core/config.py`
  reads it from there

## Setup

1. From the repo root, copy the env template and fill in your values:

   ```bash
   cp .env.example .env
   ```

   See [Environment variables](#environment-variables) below for what each
   group is for.

2. Create and activate a virtualenv, then install dependencies:

   ```bash
   cd backend
   python -m venv venv

   # Windows
   venv\Scripts\Activate.ps1
   # Mac/Linux
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. Start Postgres and Redis (and the other supporting services) via Docker:

   ```bash
   docker compose up postgres redis -d
   ```

4. Run migrations (see [Migrations](#migrations) below), then start the API:

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

   The API is served at `http://localhost:8000`, all routes under `/api/v1/...`.

Alternatively, run everything through Docker Compose — the `api` service
already runs `alembic upgrade head` before starting `uvicorn`:

```bash
docker compose up -d
```

This brings up `postgres`, `redis`, `api`, `celery-worker`, `celery-beat`,
and `gateway-stub` (a stub for the payment gateway used by top-ups/bill
payments in local dev).

## Environment variables

Every variable in `.env.example` corresponds to a field in
`app/core/config.py`'s `Settings` class, and vice versa — this is enforced
in CI by `scripts/check_env_example.py` (see [Scripts](#scripts)). If you
add a new env var, add it to **both** files, with the **exact same name**,
in the same commit. A mismatch here has silently broken a feature before
(a test set `SMTP_USER` while config read `SMTP_USERNAME`).

Groups defined in `.env.example`:

| Group | Purpose |
|---|---|
| Database | `DATABASE_URL` / `DATABASE_URL_DIRECT` — see the callout below, this is a real footgun |
| Redis | `REDIS_URL` |
| KYC | Face-match approve/flag thresholds, liveness threshold |
| Auth | JWT secret/algorithm/expiry, OTP expiry |
| App | `APP_ENV`, `LOG_FORMAT` (`text` for dev, `json` for prod) |
| ML | DeepFace model, Groq API key (chatbot), forecast model |
| Storage / S3 | KYC document storage |
| FCM | Web push notification credentials |
| Email | SMTP or SendGrid, or `console` provider for local dev |
| Twilio | SMS OTP delivery, high-value-transfer SMS threshold |
| Payment gateway | Points at `gateway-stub` in Docker, or your own mock locally |
| Bill payments | Biller API URL |
| Limits | Daily transfer limit, action-token requirement |

> **`DATABASE_URL` vs `DATABASE_URL_DIRECT`:** Alembic's `env.py` reads
> `DATABASE_URL_DIRECT`, not `DATABASE_URL`. If these point at different
> databases (e.g. one pooled, one direct — as they typically do against
> Neon), an `alembic upgrade`/`alembic revision` run will silently target
> whichever database `DATABASE_URL_DIRECT` points to. Double-check this
> variable before running any Alembic command against a shared database.

## Migrations

Migrations live in `backend/alembic/versions/`. Config is in `alembic.ini`
and `alembic/env.py`.

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new revision (edit it by hand afterward — see below)
alembic revision -m "short_description"
```

Before creating a migration, and again before pushing:

```bash
python scripts/check_single_alembic_head.py
```

This is also enforced in CI. Rules that apply to every migration (full
detail in `docs/ENGINEERING_RULES.md` §2):

- One new revision per PR, `down_revision` set to the current single head.
- **Never commit raw `alembic revision --autogenerate` output as-is** — it
  diffs against your local DB and will include drops of tables/columns you
  don't own. Review and strip anything not part of your change.
- No `drop_table` / `drop_column` in `upgrade()` without full team sign-off
  in the PR description.
- Postgres-only DDL must be guarded with
  `if op.get_bind().dialect.name == "postgresql":` — the test suite
  migrates a SQLite database.
- New JSON columns: `JSONB().with_variant(JSON, "sqlite")`, never bare
  `JSONB`.
- A model change without a matching migration (or vice versa) is a
  rejected PR — they ship together.

## Running Celery

Celery tasks live in `app/tasks/<feature>_tasks.py`; scheduled jobs are
registered in `celery_app.py`'s `beat_schedule`.

Locally, outside Docker:

```bash
cd backend
venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate    # Mac/Linux

celery -A app.celery_app:celery_app worker --loglevel=info --pool=solo
# --pool=solo is required on Windows
```

To also run scheduled/periodic tasks, start beat in a second terminal:

```bash
celery -A app.celery_app:celery_app beat --loglevel=info
```

Or via Docker Compose:

```bash
docker compose up celery-worker celery-beat -d
```

Celery tasks are plain `def` + `SyncSessionLocal` (from
`app/db/sync_session.py`) — never `async def` or an async session. Tasks
never call async service functions directly, not even via `asyncio.run`;
if an async service is needed from a task, use its `_sync` twin (e.g.
`append_audit_sync`, `check_fraud_rules_sync`).

## Seeding demo data

```bash
python scripts/seed_demo.py
# or via Docker:
docker compose run api python scripts/seed_demo.py
```

Idempotent and deterministic — safe to run repeatedly. Creates 6 demo
users in varying KYC states, wallets, beneficiaries, and illustrative
transaction history.

## Tests

```bash
python -m pytest tests/ -q
```

The default suite runs against SQLite (forced in `tests/conftest.py`) and
needs no external services — Redis is mocked (`mock_redis` fixture in
`conftest.py`; if your module imports `from app.core.redis import
redis_client`, add a matching patch line there or your tests will
silently hit real Redis) and external calls (Groq, Twilio, S3, payment
gateway) are mocked via `httpx`.

A separate Postgres-backed suite exists for money-path/ledger tests that
need real Postgres semantics:

```bash
# requires a running Postgres and POSTGRES_TEST_URL set
python -m pytest tests_postgres -m postgres -q
```

It's skipped automatically if `POSTGRES_TEST_URL` isn't set. Locally you
can point it at the Docker Compose `postgres` service; CI spins up an
isolated instance.

Before pushing, run (this mirrors CI):

```bash
python scripts/check_single_alembic_head.py
python scripts/check_env_example.py
ruff check .
python -m pytest tests/ -q
```

New endpoints need an endpoint-level test (see `test_money_movement.py`
for the pattern): happy path, auth rejected, ownership rejected, and one
failure path. Mock only the external boundary — never the DB or your own
service code.

## Scripts

All in `backend/scripts/`:

| Script | Purpose |
|---|---|
| `check_single_alembic_head.py` | Fails if there's more than one Alembic head. Run before creating/pushing a migration; also runs in CI. |
| `check_env_example.py` | Fails if `Settings` fields in `app/core/config.py` and `.env.example` fall out of sync in either direction. |
| `seed_demo.py` | Idempotent demo data seed — see [Seeding demo data](#seeding-demo-data). |

## Project layout

```
backend/
├── alembic/versions/     # migrations
├── app/
│   ├── api/v1/endpoints/ # routers — registered in app/api/v1/router.py
│   ├── core/             # config, redis, logging, request context
│   ├── db/                # sync/async session setup
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic schemas
│   ├── services/          # shared business logic — import, don't duplicate
│   ├── tasks/              # Celery tasks
│   └── main.py
├── scripts/
├── tests/                 # SQLite-backed unit/endpoint tests
└── tests_postgres/        # Postgres-backed E2E tests (opt-in via POSTGRES_TEST_URL)
```

Every router is registered in `app/api/v1/router.py` and served under
`/api/v1/...` — nothing is mounted directly in `main.py`, and no router
should hardcode that prefix itself.
