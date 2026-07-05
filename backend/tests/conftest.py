import os
import sys
from pathlib import Path
from unittest.mock import patch

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_PATH = BACKEND_DIR / "test_neobank.db"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH.resolve().as_posix()}"

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["DATABASE_URL_DIRECT"] = TEST_DB_URL
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["JWT_SECRET"] = "test_secret_key_that_is_long_enough_32chars"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRE_MINUTES"] = "30"
os.environ["JWT_REFRESH_EXPIRE_DAYS"] = "7"
os.environ["OTP_EXPIRE_MINUTES"] = "5"
os.environ["APP_ENV"] = "test"
os.environ["DEEPFACE_MODEL"] = "ArcFace"
os.environ["GROQ_API_KEY"] = "test_groq_key"
os.environ["AWS_ACCESS_KEY_ID"] = "test_access_key"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test_secret_key"
os.environ["AWS_BUCKET_NAME"] = "test-bucket"
os.environ["AWS_REGION"] = "eu-central-1"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["SMTP_HOST"] = "smtp.gmail.com"
os.environ["SMTP_PORT"] = "587"
os.environ["SMTP_USERNAME"] = "test@example.com"
os.environ["SMTP_PASSWORD"] = "test_password"
os.environ["TWILIO_ACCOUNT_SID"] = "test_sid"
os.environ["TWILIO_AUTH_TOKEN"] = "test_token"
os.environ["TWILIO_FROM_NUMBER"] = "+15555555555"

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
import app.models as app_models  # noqa: E402, F401


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create the SQLite-compatible tables exercised by the test suite."""
    tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["wallets"],
        Base.metadata.tables["user_sessions"],
        Base.metadata.tables["transactions"],
        Base.metadata.tables["transaction_audit_logs"],
        Base.metadata.tables["beneficiaries"],
        Base.metadata.tables["notifications"],
    ]
    async with engine.begin() as conn:
        for table in reversed(tables):
            await conn.run_sync(table.drop, checkfirst=True)
        for table in tables:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with engine.begin() as conn:
        for table in reversed(tables):
            await conn.run_sync(table.drop, checkfirst=True)


@pytest.fixture(autouse=True)
async def mock_redis():
    fake = fakeredis.aioredis.FakeRedis()
    with patch("app.core.redis.redis_client", fake), \
         patch("app.core.cache_utils.redis_client", fake), \
         patch("app.main.redis_client", fake), \
         patch("app.services.exchange_cache.redis_client", fake), \
         patch("app.services.otp.redis_client", fake), \
         patch("app.services.rate_limiter.redis_client", fake):
        yield fake


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
