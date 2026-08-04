from decimal import Decimal

from app.schemas.bill import BillPayRequest


def test_bill_payment_uses_wallet_without_card_token() -> None:
    request = BillPayRequest(
        from_wallet_id=121,
        bill_type="ogero",
        bill_reference="LB81441957494991",
        amount=Decimal("5.00"),
        currency="USD",
    )

    assert request.from_wallet_id == 121
    assert request.amount == Decimal("5.00")
    assert "card_token" not in BillPayRequest.model_fields
