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
    _to_minor_units,
    charge_card,
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
async def test_charge_card_raises_gateway_unavailable_on_unexpected_status(monkeypatch):
    """
    A PaymentIntent that comes back neither "succeeded" nor as a CardError
    (e.g. "requires_action", meaning Stripe wants a client-side flow this
    endpoint doesn't support) must not be treated as a successful charge.
    """
    class _FakeIntent:
        id = "pi_test_456"
        status = "requires_action"

    def _fake_create(*args, **kwargs):
        return _FakeIntent()

    monkeypatch.setattr(
        "app.services.stripe_gateway._create_and_confirm_payment_intent",
        _fake_create,
    )

    with pytest.raises(GatewayUnavailableError):
        await charge_card("pm_test", Decimal("10.00"), "USD", "idem-key-4")
