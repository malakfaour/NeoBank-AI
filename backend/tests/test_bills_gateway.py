from decimal import Decimal

import pytest

from app.api.v1.endpoints import bills


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    def json(self):
        return self.body


class FakeClient:

    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self.response


@pytest.mark.anyio
async def test_bill_gateway_ok(monkeypatch):

    monkeypatch.setattr(
        bills.httpx,
        "AsyncClient",
        lambda *a, **k: FakeClient(
            FakeResponse(
                200,
                {"status": "approved"},
            )
        ),
    )

    result = await bills._call_payment_gateway(
        "tok_ok_test",
        Decimal("10"),
        "USD",
    )

    assert result["status"] == "approved"


@pytest.mark.anyio
async def test_bill_gateway_declined(monkeypatch):

    monkeypatch.setattr(
        bills.httpx,
        "AsyncClient",
        lambda *a, **k: FakeClient(
            FakeResponse(
                402,
                {
                    "status": "declined",
                    "reason": "card_declined",
                },
            )
        ),
    )

    with pytest.raises(Exception):
        await bills._call_payment_gateway(
            "tok_declined_test",
            Decimal("10"),
            "USD",
        )


@pytest.mark.anyio
async def test_bill_gateway_timeout(monkeypatch):

    monkeypatch.setattr(
        bills.httpx,
        "AsyncClient",
        lambda *a, **k: FakeClient(
            FakeResponse(
                504,
                {
                    "detail": "gateway_timeout"
                },
            )
        ),
    )

    with pytest.raises(Exception):
        await bills._call_payment_gateway(
            "tok_timeout_test",
            Decimal("10"),
            "USD",
        )