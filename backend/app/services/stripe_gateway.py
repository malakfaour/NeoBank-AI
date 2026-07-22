"""
DEVATTECH-131: real card tokenization via Stripe, replacing the fake
gateway stub previously used by POST /accounts/top-up (the raw card
number never reaches this backend at all now -- the frontend's Stripe
Elements form tokenizes it directly with Stripe and only ever sends this
service a payment_method_id, e.g. "pm_1Nx...").

Scope decision (confirmed with the ticket owner): USD and LBP wallets
only. USDT is crypto -- no card processor charges a card and hands back
crypto, so USDT top-up is rejected before this module is ever called
(see accounts.py). Bill payments (bills.py) have their own, separate
fake-gateway stub and are explicitly NOT touched by this ticket.
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

import stripe
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

# Stripe's own zero-decimal presentment currencies (whole-unit amounts,
# no multiplying by 100). LBP is deliberately NOT in this set -- Stripe
# treats it as a standard two-decimal currency as of when this was
# written. If that ever changes on Stripe's side, this is the one place
# to update; see the currency test in test_stripe_gateway.py, which pins
# the current LBP behavior so a silent Stripe-side change gets caught.
ZERO_DECIMAL_CURRENCIES = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg",
    "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
}

# Wallet currencies this gateway will actually charge a card for.
SUPPORTED_CURRENCIES = {"USD", "LBP"}


class CardDeclinedError(Exception):
    """Stripe declined the card. `.message` is safe to show the customer."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class GatewayUnavailableError(Exception):
    """Any other Stripe-side failure: network, config, rate limit, etc."""


def _to_minor_units(amount: Decimal, currency: str) -> int:
    """
    Convert a decimal wallet amount to the integer minor-unit amount
    Stripe's API expects (e.g. 10.00 USD -> 1000; 10 JPY -> 10).
    """
    if currency.lower() in ZERO_DECIMAL_CURRENCIES:
        return int(amount.to_integral_value(rounding=ROUND_HALF_UP))
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _create_and_confirm_payment_intent(
    payment_method_id: str,
    amount: Decimal,
    currency: str,
    idempotency_key: str,
) -> "stripe.PaymentIntent":
    # confirm=True executes the charge synchronously in this same call.
    # allow_redirects="never" rules out redirect-based payment methods
    # (e.g. bank redirects) that would need a client-side follow-up flow
    # this endpoint doesn't implement -- card-only, resolves immediately.
    return stripe.PaymentIntent.create(
        amount=_to_minor_units(amount, currency),
        currency=currency.lower(),
        payment_method=payment_method_id,
        confirm=True,
        automatic_payment_methods={
            "enabled": True,
            "allow_redirects": "never",
        },
        idempotency_key=idempotency_key,
    )


async def charge_card(
    payment_method_id: str,
    amount: Decimal,
    currency: str,
    idempotency_key: str,
) -> str:
    """
    Charge `payment_method_id` for `amount` in `currency` via a real
    Stripe PaymentIntent. Returns the PaymentIntent id on success.

    Raises CardDeclinedError on a decline (caller should surface this as
    a 402, same as the old fake-gateway contract), or
    GatewayUnavailableError on any other failure (caller should surface
    this as a 502, same as the old fake-gateway contract).

    idempotency_key: currently a fresh uuid4 generated per call site
    (accounts.py) -- CardTopUpRequest has no client-supplied idempotency
    header yet (that's DEVATTECH-125, on a separate in-flight branch).
    Once that lands, thread its X-Idempotency-Key value through here
    instead of generating a fresh one, so a client retry reuses the same
    Stripe idempotency key too and can't double-charge the card.

    stripe-python's PaymentIntent.create is a blocking/synchronous call;
    every other I/O path in this app is async, so it runs in a
    threadpool rather than blocking the event loop -- same pattern as
    the forecast model call in exchange.py.
    """
    try:
        intent = await run_in_threadpool(
            _create_and_confirm_payment_intent,
            payment_method_id,
            amount,
            currency,
            idempotency_key,
        )
    except stripe.CardError as exc:
        logger.info(
            "Stripe card declined: %s",
            exc.user_message or str(exc),
        )
        raise CardDeclinedError(exc.user_message or "Card declined") from exc
    except stripe.StripeError as exc:
        logger.warning(
            "Stripe gateway error: %s",
            exc.user_message or str(exc),
        )
        raise GatewayUnavailableError(str(exc)) from exc

    if intent.status != "succeeded":
        # A confirmed card payment with redirects disabled should resolve
        # to "succeeded" or raise CardError above. Any other status here
        # (e.g. "requires_action") means Stripe wants a client-side flow
        # this endpoint doesn't support -- treat as unavailable rather
        # than silently crediting a wallet for an unresolved payment.
        raise GatewayUnavailableError(
            f"Unexpected PaymentIntent status: {intent.status}"
        )

    return intent.id
