"""
DEVATTECH-122 / SP3-703: middleware-level tests -- no endpoint logic
changes, so these test main.py's middleware and exception handler
directly rather than any specific business endpoint.
"""
import pytest


async def test_response_includes_x_request_id_header(client):
    """Every response, even a simple public one, gets an X-Request-ID header."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # Sanity check it looks like a uuid4 (36 chars, 4 hyphens)
    assert len(response.headers["X-Request-ID"]) == 36


async def test_two_requests_get_different_request_ids(client):
    r1 = await client.get("/health")
    r2 = await client.get("/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


async def test_unhandled_exception_returns_generic_error_with_request_id(auth_tokens):
    """
    An unhandled exception anywhere in a route must never leak its message
    or a stack trace to the client -- only {error, request_id}.

    Uses app.dependency_overrides rather than unittest.mock.patch: FastAPI
    binds Depends(get_current_user) to the function object at route
    registration (import) time, so patching the module attribute afterward
    doesn't intercept it. dependency_overrides is looked up per-request,
    so it's the correct way to inject a failure here.

    Uses Starlette's TestClient (not httpx.AsyncClient directly): another
    fixture in this suite globally patches httpx.AsyncClient for payment-
    gateway mocking, which collides with building a second AsyncClient
    here. TestClient is a separate class, unaffected by that patch, and
    its raise_server_exceptions=False is the documented way to test a
    global exception handler -- a real client behind uvicorn always gets
    the 500 JSON response regardless of this setting.
    """
    from starlette.testclient import TestClient

    from app.api.dependencies import get_current_user
    from app.main import app

    async def _boom():
        raise RuntimeError("boom -- this must never reach the client")

    app.dependency_overrides[get_current_user] = _boom
    try:
        with TestClient(app, raise_server_exceptions=False) as local_client:
            response = local_client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            )
    finally:
        del app.dependency_overrides[get_current_user]

    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "internal_error"
    assert "request_id" in data
    assert data["request_id"] == response.headers["X-Request-ID"]
    # The exact assertion that matters: nothing about "boom" leaked.
    assert "boom" not in response.text


@pytest.fixture
async def auth_tokens(client):
    """Register and login a test user, return tokens."""
    await client.post("/api/v1/auth/register", json={
        "full_name": "Observability Test User",
        "email": "observabilitytest@neobank.com",
        "phone": "+96170000097",
        "password": "TestPass123",
    })
    response = await client.post("/api/v1/auth/login", json={
        "email": "observabilitytest@neobank.com",
        "password": "TestPass123",
    })
    return response.json()
