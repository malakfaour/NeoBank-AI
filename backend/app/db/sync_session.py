"""
Dedicated SYNC SQLAlchemy engine for use inside Celery tasks.

FastAPI routes use the async engine (app.db.session, asyncpg-based) --
that's fine for request/response code, but Celery tasks run synchronously
by default, and asyncpg connections are bound to the event loop they were
created on. Reusing the async engine from inside a sync task via
asyncio.run() would risk that binding breaking across task invocations
(each asyncio.run() call spins up a fresh event loop).

Instead, this module gives Celery tasks their own plain sync engine, using
DATABASE_URL_DIRECT -- the same sync Postgres connection string Alembic
already uses for migrations. No asyncio involved, no event-loop risk.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _sync_database_url(database_url: str) -> URL:
    """Return a URL backed by a synchronous SQLAlchemy driver."""
    url = make_url(database_url)
    drivername = {
        "postgresql+asyncpg": "postgresql+psycopg2",
        "sqlite+aiosqlite": "sqlite",
    }.get(url.drivername, url.drivername)

    query = dict(url.query)
    if drivername.startswith("postgresql") and "ssl" in query:
        query.setdefault("sslmode", query.pop("ssl"))

    return url.set(drivername=drivername, query=query)


sync_engine = create_engine(
    _sync_database_url(settings.DATABASE_URL_DIRECT),
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)
