import os
import sys
import pytest
import pytest_asyncio
import fakeredis.aioredis
from pathlib import Path
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_neobank.db"
os.environ["DATABASE_URL_DIRECT"] = "sqlite+aiosqlite:///./test_neobank.db"
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
os.environ["SMTP_HOST"] = "smtp.gmail.com"
os.environ["SMTP_PORT"] = "587"
os.environ["SMTP_USER"] = "test@example.com"
os.environ["SMTP_PASSWORD"] = "test_password"
os.environ["TWILIO_ACCOUNT_SID"] = "test_sid"
os.environ["TWILIO_AUTH_TOKEN"] = "test_token"
os.environ["TWILIO_FROM_NUMBER"] = "+15555555555"

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create only the tables needed for auth tests."""

    tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["wallets"],
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with engine.begin() as conn:
        for table in reversed(tables):
            await conn.run_sync(table.drop, checkfirst=True)


@pytest.fixture(autouse=True)
async def mock_redis():
    """Replace Redis with fakeredis for all tests — no real connection needed."""
    fake = fakeredis.aioredis.FakeRedis()
    with patch("app.core.redis.redis_client", fake), \
         patch("app.services.rate_limiter.redis_client", fake):
        yield fake


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac