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


class RequiresActionError(Exception):
    """
    Stripe needs an additional client-side authentication step (3D Secure)
    before this PaymentIntent can be confirmed. Carries what the frontend
    needs to run that challenge via stripe.confirmCardPayment(), and what
    the backend needs afterward to independently verify the outcome
    (get_confirmed_charge below) rather than trusting the client's say-so.
    """

    def __init__(self, payment_intent_id: str, client_secret: str):
        self.payment_intent_id = payment_intent_id
        self.client_secret = client_secret
        super().__init__(f"PaymentIntent {payment_intent_id} requires_action")


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

    if intent.status == "requires_action":
        # 3D Secure (or another SCA challenge) is needed. allow_redirects=
        # "never" above only rules out redirect-based payment *methods*
        # (e.g. iDEAL) -- it does not disable 3DS, which Stripe.js
        # resolves in-page via stripe.confirmCardPayment(). The caller
        # (accounts.py) surfaces this to the frontend rather than
        # treating it as a failure.
        raise RequiresActionError(intent.id, intent.client_secret)

    if intent.status != "succeeded":
        # Any other non-succeeded status (canceled, processing, etc.) is
        # genuinely unexpected for a synchronous card confirmation --
        # treat as unavailable rather than silently crediting a wallet
        # for an unresolved payment.
        raise GatewayUnavailableError(
            f"Unexpected PaymentIntent status: {intent.status}"
        )

    return intent.id


def _retrieve_payment_intent(payment_intent_id: str) -> "stripe.PaymentIntent":
    return stripe.PaymentIntent.retrieve(payment_intent_id)


async def get_confirmed_charge(
    payment_intent_id: str,
    expected_amount: Decimal,
    expected_currency: str,
) -> str:
    """
    Re-checks a PaymentIntent's status directly with Stripe -- never
    trusts the client's say-so -- after the frontend has run a 3D Secure
    challenge via stripe.confirmCardPayment(). Returns the PaymentIntent
    id if, and only if, Stripe confirms it actually succeeded AND its
    amount/currency match what this specific top-up attempt expects (so
    a client can't point a legitimately-confirmed PaymentIntent from one
    attempt at crediting an unrelated wallet/amount).

    Raises CardDeclinedError if the challenge resulted in a decline
    (Stripe moves the PaymentIntent to "requires_payment_method" in that
    case, not a stripe.CardError -- there's no synchronous exception to
    catch here, the failure just shows up as this status on retrieval),
    GatewayUnavailableError for any other non-succeeded outcome, an
    amount/currency mismatch, or a Stripe-side failure.
    """
    try:
        intent = await run_in_threadpool(_retrieve_payment_intent, payment_intent_id)
    except stripe.StripeError as exc:
        logger.warning(
            "Stripe gateway error on top-up confirmation: %s",
            exc.user_message or str(exc),
        )
        raise GatewayUnavailableError(str(exc)) from exc

    if intent.status == "requires_payment_method":
        raise CardDeclinedError("Card authentication failed")

    if intent.status != "succeeded":
        raise GatewayUnavailableError(
            f"Unexpected PaymentIntent status after confirmation: {intent.status}"
        )

    expected_minor = _to_minor_units(expected_amount, expected_currency)
    if intent.amount != expected_minor or intent.currency != expected_currency.lower():
        logger.warning(
            "PaymentIntent %s amount/currency mismatch on confirm: "
            "expected %s %s, got %s %s",
            payment_intent_id,
            expected_minor,
            expected_currency.lower(),
            intent.amount,
            intent.currency,
        )
        raise GatewayUnavailableError("Payment amount/currency mismatch")

    return intent.id