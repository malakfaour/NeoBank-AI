"""
Regression tests for the write-endpoint rate-limiting gap flagged in the
engineering gap analysis: the sliding-window limiter (rate_limiter.py) was
wired into only 5 endpoints (login, send-otp, verify-otp, send_money,
chatbot). This adds coverage for the newly-protected endpoints:
/exchange/execute, /accounts/top-up, /transfer/neo/mobile+iban, and the
three /beneficiaries write routes.

check_rate_limit() runs as the first statement in every endpoint touched
here, before any business logic (market-hours, wallet lookup, ownership,
etc.), so these tests only need requests that pass FastAPI's own request
validation (auth header, required fields) -- they don't need to reach a
real happy path to prove the limiter fires. Existing tests
(test_exchange_endpoints.py, test_money_movement.py, etc.) already cover
each endpoint's actual business behavior; this file is scoped only to the
429-after-threshold regression, per the action plan's Phase 1 checklist.
"""
from uuid import uuid4

import pytest


async def _register_user(client, label: str) -> dict:
    suffix = uuid4().hex[:10]
    email = f"{label.lower()}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96170{suffix[:6]}",
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200, response.text
    return {**response.json(), "email": email}


@pytest.mark.anyio
async def test_exchange_execute_returns_429_after_threshold(client, monkeypatch):
    # Market closed => every under-limit request gets a fast, deterministic
    # 403 instead of depending on live/cached rates or the real clock.
    monkeypatch.setattr("app.api.v1.endpoints.exchange.is_market_open", lambda: False)

    tokens = await _register_user(client, "ratelimit-exchange")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    payload = {"from_currency": "USD", "to_currency": "LBP", "amount": "1.00"}

    for i in range(10):
        response = await client.post("/api/v1/exchange/execute", headers=headers, json=payload)
        assert response.status_code != 429, f"request {i + 1} was rate limited unexpectedly"

    response = await client.post("/api/v1/exchange/execute", headers=headers, json=payload)
    assert response.status_code == 429, response.text
    assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_accounts_topup_returns_429_after_threshold(client):
    tokens = await _register_user(client, "ratelimit-topup")
    # DEVATTECH-125 requires X-Idempotency-Key on this endpoint. Same key
    # reused across every call here is safe: each request 404s on the
    # nonexistent wallet before reaching the point where a response would
    # ever get cached against that key.
    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Idempotency-Key": uuid4().hex,
    }
    # wallet_id doesn't need to exist -- the rate-limit check runs before
    # the wallet lookup, so the wallet-not-found path is fine for the
    # under-limit requests here.
    payload = {"wallet_id": 999999, "amount": "1.00", "payment_method_id": "pm_test_ratelimit"}

    for i in range(10):
        response = await client.post("/api/v1/accounts/top-up", headers=headers, json=payload)
        assert response.status_code != 429, f"request {i + 1} was rate limited unexpectedly"

    response = await client.post("/api/v1/accounts/top-up", headers=headers, json=payload)
    assert response.status_code == 429, response.text
    assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_transfer_neo_rate_limit_shared_across_mobile_and_iban(client):
    """
    /transfer/neo/mobile and /transfer/neo/iban share one per-user budget
    (5/60s, same shape as the DEVATTECH-107 velocity guard on
    /transactions/send) -- a script alternating between the two paths must
    still hit the combined limit, not get 5 free requests on each.
    """
    tokens = await _register_user(client, "ratelimit-transfer")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    def mobile_payload():
        return {"receiver_phone": "+96170000000", "amount": "1.00", "currency": "USD"}

    def iban_payload():
        return {"receiver_iban": "LB00000000000000000000000000", "amount": "1.00", "currency": "USD"}

    # 3 on /mobile, 2 on /iban == 5, the shared limit -- none should 429 yet.
    for i in range(3):
        headers_with_key = {**headers, "X-Idempotency-Key": uuid4().hex}
        response = await client.post("/api/v1/transfer/neo/mobile", headers=headers_with_key, json=mobile_payload())
        assert response.status_code != 429, f"mobile request {i + 1} was rate limited unexpectedly"

    for i in range(2):
        headers_with_key = {**headers, "X-Idempotency-Key": uuid4().hex}
        response = await client.post("/api/v1/transfer/neo/iban", headers=headers_with_key, json=iban_payload())
        assert response.status_code != 429, f"iban request {i + 1} was rate limited unexpectedly"

    # 6th request on either path must 429.
    headers_with_key = {**headers, "X-Idempotency-Key": uuid4().hex}
    response = await client.post("/api/v1/transfer/neo/mobile", headers=headers_with_key, json=mobile_payload())
    assert response.status_code == 429, response.text
    assert "Retry-After" in response.headers


@pytest.mark.anyio
async def test_beneficiaries_write_rate_limit_shared_across_create_update_delete(client):
    """
    create/update/delete share one per-user budget (10/60s) -- alternating
    across the three routes must still hit the combined limit.
    """
    tokens = await _register_user(client, "ratelimit-beneficiary")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    create_payload = {"nickname": "Test", "type": "mobile", "value": "+96170111222"}
    update_payload = {"nickname": "Updated"}

    for i in range(4):
        response = await client.post("/api/v1/beneficiaries", headers=headers, json=create_payload)
        assert response.status_code != 429, f"create request {i + 1} was rate limited unexpectedly"

    for i in range(3):
        response = await client.patch("/api/v1/beneficiaries/999999", headers=headers, json=update_payload)
        assert response.status_code != 429, f"update request {i + 1} was rate limited unexpectedly"

    for i in range(3):
        response = await client.delete("/api/v1/beneficiaries/999999", headers=headers)
        assert response.status_code != 429, f"delete request {i + 1} was rate limited unexpectedly"

    # 11th write (any of the three routes) must 429.
    response = await client.delete("/api/v1/beneficiaries/999999", headers=headers)
    assert response.status_code == 429, response.text
    assert "Retry-After" in response.headers
