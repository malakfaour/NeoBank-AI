"""
NBL-110: mock biller integration.

No real biller/mock server exists -- BILLER_API_URL has no confirmed live
listener. Per explicit decision, the 80/20 success/failure simulation
lives HERE in our own code (random.random()), not in an external server's
response.

The httpx call below is still made (POST to settings.BILLER_API_URL) to
satisfy the ticket's literal requirement and as scaffolding for whenever a
real/mock biller endpoint exists -- but its outcome does NOT currently
determine success/failure. A connection error is expected right now (no
server listening) and is swallowed, not treated as the failure signal.

TODO: once a real biller/mock server exists, rewrite this to trust that
endpoint's actual response instead of the random draw.
"""
import logging
import random
from decimal import Decimal

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUCCESS_RATE = 0.8


class BillerResult:
    def __init__(self, success: bool, biller_error: str | None = None):
        self.success = success
        self.biller_error = biller_error


async def call_mock_biller(bill_type: str, bill_reference: str, amount: Decimal) -> BillerResult:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                settings.BILLER_API_URL,
                json={
                    "bill_type": bill_type,
                    "bill_reference": bill_reference,
                    "amount": str(amount),
                },
            )
    except httpx.HTTPError:
        # Expected right now -- no server exists yet. Not treated as the
        # failure signal; see module docstring.
        logger.debug(
            "Biller API call to %s failed (expected -- no listener configured yet)",
            settings.BILLER_API_URL,
        )

    if random.random() < SUCCESS_RATE:
        return BillerResult(success=True)
    return BillerResult(success=False, biller_error="Biller temporarily unavailable")
