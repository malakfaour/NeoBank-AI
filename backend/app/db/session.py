from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings


DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# asyncpg uses ssl=require, not sslmode=require
DATABASE_URL = DATABASE_URL.replace("sslmode=require", "ssl=require")

# asyncpg does not support channel_binding in the URL
DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "")
DATABASE_URL = DATABASE_URL.replace("?channel_binding=require&", "?")
DATABASE_URL = DATABASE_URL.replace("?channel_binding=require", "")


engine_kwargs = {"pool_pre_ping": True}
if settings.APP_ENV == "test" and DATABASE_URL == "sqlite+aiosqlite:///:memory:":
    engine_kwargs.update(
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# Backward-compatible name used by existing auth routes
get_async_db = get_db