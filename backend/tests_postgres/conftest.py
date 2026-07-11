"""
Isolated conftest for the Postgres E2E test suite (Postgres E2E
money-path CI job).

This file is intentionally NOT related to, imported from, or dependent
on backend/tests/conftest.py in any way. It exists specifically because
pytest imports every conftest.py file in the directory chain leading to
a collected test file, unconditionally, at collection time -- marker
filtering (-m postgres) only controls which TESTS run, not which
conftest files get imported. Since backend/tests/conftest.py forces
DATABASE_URL/DATABASE_URL_DIRECT to SQLite at module level,
any test living inside backend/tests/ (even nested) would have SQLite
forced on it before this file's Postgres setup could take effect.
backend/tests_postgres/ is a SIBLING of backend/tests/, not a
descendant -- so backend/tests/conftest.py is never in the collection
chain for anything in this directory.

Skip mechanism: uses pytest_collection_modifyitems (a collection hook),
not a module-level pytest.skip(allow_module_level=True) call. Combined
with this: `from app.main import app` is a LAZY import inside the client
fixture's body, not at module level. Empirically verified (both by the
user, in their own environment): with POSTGRES_TEST_URL unset, the test
is reported skipped and a marker proving app.main was imported does NOT
appear; with it set, the test passes and the marker DOES appear.
"""
import os

import pytest

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL")

if POSTGRES_TEST_URL:
    # --- Build the two connection strings this test run actually needs ---
    #
    # DATABASE_URL: async (asyncpg) form, for the app's normal
    # AsyncSession path (register/top-up/send, all called through the
    # real API via the httpx test client below).
    #
    # DATABASE_URL_DIRECT: sync-compatible form. Two DIFFERENT sync
    # consumers have DIFFERENT expectations of this one setting:
    #   - app/db/sync_session.py's SyncSessionLocal does
    #     create_engine(settings.DATABASE_URL_DIRECT) directly, with NO
    #     scheme conversion -- it needs a plain "postgresql://" URL
    #     already.
    #   - alembic/env.py does its OWN
    #     ".replace('postgresql+asyncpg://', 'postgresql://')" on
    #     DATABASE_URL_DIRECT before using it -- it expects the
    #     asyncpg-scheme form as input.
    # These two expectations are inconsistent for a single shared env
    # var value (a pre-existing repo inconsistency -- see
    # docker-compose.yml's DATABASE_URL_DIRECT, which is asyncpg-scheme
    # and would break sync_session.py's direct create_engine() call the
    # same way). NOT fixed by this ticket -- resolved instead at the
    # CI-pipeline level, with no production file changes:
    #   - The CI job's separate "alembic upgrade head" step runs BEFORE
    #     pytest, in its own step, with DATABASE_URL_DIRECT set to the
    #     asyncpg-scheme form (matching env.py's expectation).
    #   - THIS file, running afterward inside the pytest process, sets
    #     DATABASE_URL_DIRECT to the plain sync-compatible form instead
    #     -- matching what sync_session.py actually needs for the
    #     direct score_transaction(...) invocation used later in this
    #     suite.
    # Both consumers get the form they need, at different pipeline
    # stages, via different env var values -- neither file is edited.
    if "+asyncpg" in POSTGRES_TEST_URL:
        _ASYNC_URL = POSTGRES_TEST_URL
        _SYNC_URL = POSTGRES_TEST_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    else:
        _SYNC_URL = POSTGRES_TEST_URL
        _ASYNC_URL = POSTGRES_TEST_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

    os.environ["DATABASE_URL"] = _ASYNC_URL
    os.environ["DATABASE_URL_DIRECT"] = _SYNC_URL

    # Hard-set (not setdefault) -- this suite must not accidentally pick
    # up real Redis/JWT/email values from the machine's environment or
    # from a real .env file (Settings() falls back to reading .env for
    # any field not set via OS env var). Trimmed to only what this
    # suite's actual code path (register/login/top-up/send/score/audit/
    # resolve-flag) touches or requires -- verified against the real,
    # current sessions.py, account_service.py, and transactions.py, not
    # assumed:
    #   - REDIS_URL: isolation, even though fakeredis patches cover
    #     direct usage below.
    #   - JWT_SECRET: required field in Settings(), no default.
    #   - REQUIRE_ACTION_TOKEN=false: without this, send_money demands
    #     a real passcode-verify flow this suite doesn't implement.
    #   - EMAIL_PROVIDER=console: register() dispatches
    #     send_welcome_email as a background task in this exact flow --
    #     if left unset and a real .env has real SMTP credentials, this
    #     could send a real email during the test.
    #   - APP_ENV=test: self-descriptive, harmless.
    # Deliberately NOT set (all have safe Settings() defaults, and none
    # are touched by this suite's exercised code path -- KYC, chatbot,
    # S3, SMS-OTP, and bill-payment are all out of scope here):
    # DEEPFACE_MODEL, GROQ_API_KEY, AWS_*, TWILIO_*, SMTP_*,
    # JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_REFRESH_EXPIRE_DAYS,
    # OTP_EXPIRE_MINUTES, BILLER_API_URL.
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    os.environ["JWT_SECRET"] = "postgres_e2e_test_secret_key_32chars_min"
    os.environ["REQUIRE_ACTION_TOKEN"] = "false"
    os.environ["EMAIL_PROVIDER"] = "console"
    os.environ["APP_ENV"] = "test"


def pytest_collection_modifyitems(config, items):
    """
    Skip every test collected under this directory if POSTGRES_TEST_URL
    is not set. A collection hook, not a module-level pytest.skip() --
    this runs after collection completes but before any fixture executes,
    so it never needs to import app.* code itself.
    """
    if not POSTGRES_TEST_URL:
        skip_marker = pytest.mark.skip(
            reason="POSTGRES_TEST_URL is not set -- Postgres E2E suite skipped "
                   "(expected for local/default runs; set POSTGRES_TEST_URL to run it)"
        )
        for item in items:
            item.add_marker(skip_marker)


# NOTE: no anyio_backend fixture here -- pytest.ini's asyncio_mode = auto
# (repo-wide, untouched by this ticket) already makes pytest-asyncio
# handle every async def test_... function automatically.


@pytest.fixture(autouse=True)
async def _reset_db_engine_per_test():
    """
    Disposes app/db/session.py's module-level AsyncEngine's connection
    pool before each test in this suite. NOT a production file change --
    engine.dispose() is a normal SQLAlchemy operation, called from test
    code only.

    Why this is needed: `engine` in app/db/session.py is a MODULE-LEVEL
    object, constructed exactly once (Python caches modules in
    sys.modules). Its underlying asyncpg connections bind to whichever
    asyncio event loop is running at the moment they are first
    established -- a well-known asyncpg/async-SQLAlchemy constraint.
    pytest-asyncio's default is a FRESH event loop per test function,
    torn down after each test. Without this fixture: Test 1 creates the
    engine (and its connections) bound to Loop A; Loop A closes at the
    end of Test 1; Test 2 starts on a new Loop B but reuses the SAME
    cached engine object, whose connections are still bound to the
    now-closed Loop A -- raising "RuntimeError: Event loop is closed".

    Calling engine.dispose() discards any pooled connections (harmless
    no-op if none exist yet, e.g. before the very first test); the pool
    then creates fresh connections bound to whichever loop is actually
    running for the CURRENT test. This is intentionally version-agnostic
    with respect to pytest-asyncio's own event-loop-scope configuration
    (the classic event_loop fixture override pattern is version-
    sensitive and was not used here) -- it only depends on
    AsyncEngine.dispose(), stable, long-standing SQLAlchemy API.

    autouse=True, no explicit dependents needed: pytest completes setup
    for ALL autouse fixtures before a test function's body runs, so this
    always executes before any AsyncSessionLocal() usage in that body --
    whether via the client fixture's HTTP calls or a test's own direct
    "async with AsyncSessionLocal() as db:" blocks.
    """
    if POSTGRES_TEST_URL:
        from app.db.session import engine

        await engine.dispose()
    yield


@pytest.fixture(autouse=True)
def mock_redis():
    """
    Independently authored here, not imported from
    backend/tests/conftest.py. Patches the same module-level
    redis_client references those modules actually have. Verified
    against the CURRENT sessions.py, account_service.py, and
    transactions.py (send_money): no additional redis_client import
    exists beyond app.core.redis and app.core.cache_utils -- both
    already covered here.
    """
    import fakeredis.aioredis
    from unittest.mock import patch

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.core.redis.redis_client", fake), \
         patch("app.core.cache_utils.redis_client", fake), \
         patch("app.main.redis_client", fake), \
         patch("app.services.exchange_cache.redis_client", fake), \
         patch("app.services.otp.redis_client", fake), \
         patch("app.services.rate_limiter.redis_client", fake):
        yield fake


class _FakePaymentGatewayResponse:
    """Minimal stand-in for the httpx.Response accounts.py's
    _call_payment_gateway() returns on success. Only .status_code and
    .json() are ever read by card_top_up() -- see accounts.py: a 402
    means declined, >=500 means gateway unavailable, anything else
    (this stub's 200) proceeds as success."""
    status_code = 200

    def json(self):
        return {"message": "approved"}


@pytest.fixture(autouse=True)
def mock_payment_gateway():
    """
    Mocks the external HTTP boundary in the top-up step (accounts.py's
    _call_payment_gateway, a real httpx.AsyncClient POST to
    settings.PAYMENT_GATEWAY_URL) so this suite never makes a real
    network call. accounts.py itself is not modified.
    """
    from unittest.mock import AsyncMock, patch

    with patch(
        "app.api.v1.endpoints.accounts._call_payment_gateway",
        new=AsyncMock(return_value=_FakePaymentGatewayResponse()),
    ):
        yield


@pytest.fixture
def stub_fraud_scoring():
    """
    Mocks the SECOND external boundary this suite touches: Celery task
    dispatch. send_money() (transactions.py) unconditionally calls
    score_transaction.delay(transaction.id) on every successful send --
    unlike categorize_transaction.delay() inside transaction_tasks.py,
    this call is NOT wrapped in try/except. Celery's .delay() uses its
    own broker connection, entirely separate from the redis_client
    objects mock_redis patches above -- with no real broker reachable in
    this isolated suite, an unmocked .delay() here would very likely
    raise inside the POST /transactions/send request itself, turning the
    "send" step into a 500 before this suite ever reaches its own
    explicit, direct invocation of score_transaction (per the approved
    "option 3" design -- call the task body directly, synchronously, not
    via .delay()).

    Not invented here -- this exact pattern (same patch target, same
    "record transaction_id, return nothing" shape) already exists in
    backend/tests/test_money_movement.py's own stub_fraud_scoring
    fixture; reproduced independently here since this conftest does not
    import from backend/tests/. Kept as a non-autouse fixture the test
    explicitly requests, matching that file's convention, since the
    E2E test wants to assert dispatch actually happened as part of
    proving the "score" step of the AC.
    """
    calls = []

    def _delay(transaction_id: int) -> None:
        calls.append(transaction_id)

    from unittest.mock import patch

    with patch("app.api.v1.endpoints.transactions.score_transaction.delay", _delay):
        yield calls


@pytest.fixture
async def client():
    """`from app.main import app` is deliberately inside this fixture
    body, not at module level -- see the module docstring above for why
    this matters for the skip-without-importing-the-app guarantee."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
