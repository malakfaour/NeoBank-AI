import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
import app.api.v1.endpoints.exchange as exchange_endpoint


@pytest.mark.anyio
async def test_live_rate_stale_flag_when_cache_old(mock_redis):
    with patch.object(
        exchange_endpoint,
        "get_cached_exchange_rates_with_age",
        new=AsyncMock(return_value=({("USD", "LBP"): Decimal("90000")}, 400)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/exchange/rates/live?from_currency=USD&to_currency=LBP")
    assert response.status_code == 200
    data = response.json()
    assert data["stale"] is True
    assert data["cache_age_seconds"] == 400


@pytest.mark.anyio
async def test_live_rate_not_stale_when_cache_fresh(mock_redis):
    with patch.object(
        exchange_endpoint,
        "get_cached_exchange_rates_with_age",
        new=AsyncMock(return_value=({("USD", "LBP"): Decimal("90000")}, 100)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/exchange/rates/live?from_currency=USD&to_currency=LBP")
    assert response.status_code == 200
    data = response.json()
    assert data["stale"] is False


@pytest.mark.anyio
async def test_feed_500_does_not_write_db_row_and_returns_stale(mock_redis):
    from sqlalchemy import select
    from app.models.exchange_rate import ExchangeRate
    from app.db.session import AsyncSessionLocal

    stale_rates = {("USD", "LBP"): Decimal("89000")}

    async with AsyncSessionLocal() as session:
        before = (await session.execute(select(ExchangeRate))).scalars().all()

    with patch.object(
        exchange_endpoint,
        "get_cached_exchange_rates_with_age",
        new=AsyncMock(return_value=(stale_rates, 400)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/exchange/rates/live?from_currency=USD&to_currency=LBP")

    assert response.status_code == 200
    data = response.json()
    assert data["stale"] is True

    async with AsyncSessionLocal() as session:
        after = (await session.execute(select(ExchangeRate))).scalars().all()

    assert len(after) == len(before)
