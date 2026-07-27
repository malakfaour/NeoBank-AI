from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


async def to_usd_equivalent(amount: Decimal, currency: str, db: AsyncSession) -> Decimal:
    """
    Convert a wallet-native amount to its USD equivalent so flat-USD daily
    limits (TOPUP_DAILY_LIMIT, DAILY_TRANSFER_LIMIT_USD) are enforced
    consistently across currencies -- comparing/accumulating the raw
    currency amount directly against a USD limit lets LBP amounts blow
    past a dollar cap while numerically tiny, and lets USD amounts exhaust
    a limit LBP amounts of the same face value barely touch.
    """
    if currency == "USD":
        return amount

    from app.api.v1.endpoints.exchange import get_rates_from_cache_or_provider

    rates = await get_rates_from_cache_or_provider(db)
    rate = rates.get(("USD", currency))
    if not rate:
        raise HTTPException(
            status_code=503,
            detail="Exchange rate provider unavailable",
        )
    return amount / rate
