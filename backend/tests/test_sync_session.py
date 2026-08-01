from app.db.sync_session import _sync_database_url, sync_engine


def test_celery_engine_uses_a_synchronous_driver():
    assert not sync_engine.dialect.is_async


def test_sync_database_url_replaces_asyncpg_and_normalizes_ssl():
    url = _sync_database_url(
        "postgresql+asyncpg://user:pass@db.example/neobank?ssl=require"
    )

    assert url.drivername == "postgresql+psycopg2"
    assert url.query["sslmode"] == "require"
    assert "ssl" not in url.query


def test_sync_database_url_replaces_aiosqlite():
    url = _sync_database_url("sqlite+aiosqlite:///:memory:")

    assert url.drivername == "sqlite"
