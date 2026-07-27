"""
Unit tests for app/services/stripe_gateway.py (DEVATTECH-131).

These test the module's own logic (minor-unit conversion, exception
mapping) by monkeypatching _create_and_confirm_payment_intent directly --
one level lower than the endpoint tests in test_money_movement.py, which
monkeypatch charge_card() itself and exercise the full HTTP path through
POST /accounts/top-up.
"""
from decimal import Decimal

import pytest
import stripe

from app.services.stripe_gateway import (
    CardDeclinedError,
    GatewayUnavailableError,
    RequiresActionError,
    _to_minor_units,
    charge_card,
    get_confirmed_charge,
)


def test_to_minor_units_usd_two_decimal():
    assert _to_minor_units(Decimal("10.00"), "USD") == 1000
    assert _to_minor_units(Decimal("10.99"), "usd") == 1099


def test_to_minor_units_lbp_treated_as_two_decimal():
    # Pins current behavior: LBP is NOT in Stripe's zero-decimal set as of
    # writing (see the ZERO_DECIMAL_CURRENCIES comment in stripe_gateway.py).
    # If Stripe ever reclassifies it, this test is what catches the drift.
    assert _to_minor_units(Decimal("100000.00"), "LBP") == 10000000


def test_to_minor_units_zero_decimal_currency_not_multiplied():
    assert _to_minor_units(Decimal("500"), "JPY") == 500


@pytest.mark.anyio
async def test_charge_card_returns_payment_intent_id_on_success(monkeypatch):
    class _FakeIntent:
        id = "pi_test_123"
        status = "succeeded"

    def _fake_create(payment_method_id, amount, currency, idempotency_key):
        return _FakeIntent()

    monkeypatch.setattr(
        "app.services.stripe_gateway._create_and_confirm_payment_intent",
        _fake_create,
    )

    result = await charge_card("pm_test", Decimal("10.00"), "USD", "idem-key-1")
    assert result == "pi_test_123"


@pytest.mark.anyio
async def test_charge_card_raises_card_declined_on_stripe_card_error(monkeypatch):
    def _fake_create(*args, **kwargs):
        raise stripe.CardError("Your card was declined.", None, "card_declined")

    monkeypatch.setattr(
        "app.services.stripe_gateway._create_and_confirm_payment_intent",
        _fake_create,
    )

    with pytest.raises(CardDeclinedError) as exc_info:
        await charge_card("pm_test", Decimal("10.00"), "USD", "idem-key-2")
    assert exc_info.value.message == "Your card was declined."


@pytest.mark.anyio
async def test_charge_card_raises_gateway_unavailable_on_other_stripe_error(monkeypatch):
    def _fake_create(*args, **kwargs):
        raise stripe.APIConnectionError("network error")

    monkeypatch.setattr(
        "app.services.stripe_gateway._create_and_confirm_payment_intent",
        _fake_create,
    )

    with pytest.raises(GatewayUnavailableError):
        await charge_card("pm_test", Decimal("10.00"), "USD", "idem-key-3")

@pytest.mark.anyio
async def test_charge_card_raises_requires_action_on_3ds_challenge(monkeypatch):
    """
    A PaymentIntent that comes back "requires_action" (Stripe wants a 3D
    Secure challenge) must not be treated as a failure -- it's a distinct
    outcome the caller (accounts.py) turns into
    CardTopUpRequiresActionResponse for the frontend to act on.
    """
    class _FakeIntent:
        id = "pi_test_456"
        status = "requires_action"
        client_secret = "pi_test_456_secret_abc"

    def _fake_create(*args, **kwargs):
        return _FakeIntent()

    monkeypatch.setattr(
        "app.services.stripe_gateway._create_and_confirm_payment_intent",
        _fake_create,
    )

    with pytest.raises(RequiresActionError) as exc_info:
        await charge_card("pm_test", Decimal("10.00"), "USD", "idem-key-4")
    assert exc_info.value.payment_intent_id == "pi_test_456"
    assert exc_info.value.client_secret == "pi_test_456_secret_abc"


@pytest.mark.anyio
async def test_charge_card_raises_gateway_unavailable_on_genuinely_unexpected_status(monkeypatch):
    """
    Any non-succeeded, non-requires_action, non-CardError outcome (e.g.
    "canceled") is still treated as unavailable rather than credited.
    """
    class _FakeIntent:
        id = "pi_test_789"
        status = "canceled"

    def _fake_create(*args, **kwargs):
        return _FakeIntent()

    monkeypatch.setattr(
        "app.services.stripe_gateway._create_and_confirm_payment_intent",
        _fake_create,
    )

    with pytest.raises(GatewayUnavailableError):
        await charge_card("pm_test", Decimal("10.00"), "USD", "idem-key-5")


# --- get_confirmed_charge (post-3DS-challenge verification) ---


@pytest.mark.anyio
async def test_get_confirmed_charge_returns_id_when_succeeded_and_amounts_match(monkeypatch):
    class _FakeIntent:
        id = "pi_test_confirmed"
        status = "succeeded"
        amount = 1000
        currency = "usd"

    monkeypatch.setattr(
        "app.services.stripe_gateway._retrieve_payment_intent",
        lambda payment_intent_id: _FakeIntent(),
    )

    result = await get_confirmed_charge("pi_test_confirmed", Decimal("10.00"), "USD")
    assert result == "pi_test_confirmed"


@pytest.mark.anyio
async def test_get_confirmed_charge_raises_card_declined_when_challenge_failed(monkeypatch):
    """
    A failed/declined 3DS challenge moves the PaymentIntent to
    "requires_payment_method" -- there's no synchronous exception to
    catch here (unlike the initial charge), the failure just shows up as
    this status on retrieval.
    """
    class _FakeIntent:
        id = "pi_test_failed_challenge"
        status = "requires_payment_method"
        amount = 1000
        currency = "usd"

    monkeypatch.setattr(
        "app.services.stripe_gateway._retrieve_payment_intent",
        lambda payment_intent_id: _FakeIntent(),
    )

    with pytest.raises(CardDeclinedError):
        await get_confirmed_charge("pi_test_failed_challenge", Decimal("10.00"), "USD")


@pytest.mark.anyio
async def test_get_confirmed_charge_rejects_amount_mismatch(monkeypatch):
    """
    Defense in depth: a client can't point a legitimately-confirmed
    PaymentIntent from one attempt at crediting a different amount than
    what was actually authorized.
    """
    class _FakeIntent:
        id = "pi_test_mismatch"
        status = "succeeded"
        amount = 500  # $5.00, not the $10.00 being claimed below
        currency = "usd"

    monkeypatch.setattr(
        "app.services.stripe_gateway._retrieve_payment_intent",
        lambda payment_intent_id: _FakeIntent(),
    )

    with pytest.raises(GatewayUnavailableError):
        await get_confirmed_charge("pi_test_mismatch", Decimal("10.00"), "USD")


@pytest.mark.anyio
async def test_get_confirmed_charge_raises_gateway_unavailable_on_stripe_error(monkeypatch):
    def _fake_retrieve(payment_intent_id):
        raise stripe.APIConnectionError("network error")

    monkeypatch.setattr(
        "app.services.stripe_gateway._retrieve_payment_intent",
        _fake_retrieve,
    )

    with pytest.raises(GatewayUnavailableError):
        await get_confirmed_charge("pi_test_network_fail", Decimal("10.00"), "USD")