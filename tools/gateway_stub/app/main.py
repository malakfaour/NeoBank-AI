from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="NeoBank Payment Gateway Stub"
)


class PaymentRequest(BaseModel):
    token: str
    amount: float


@app.post("/payments/charge")
async def charge_payment(
    payload: PaymentRequest,
):
    token = payload.token

    if token.startswith("tok_ok"):
        return {
            "status": "approved",
            "transaction_id": "gw_success_001",
        }

    if token.startswith("tok_declined"):
        return {
            "status": "declined",
            "reason": "card_declined",
        }

    if token.startswith("tok_timeout"):
        raise HTTPException(
            status_code=504,
            detail="gateway_timeout",
        )

    return {
        "status": "declined",
        "reason": "unknown_token",
    }