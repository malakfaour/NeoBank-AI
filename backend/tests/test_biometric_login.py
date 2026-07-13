import base64
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _key_material():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key, public_key


def _signature(private_key, nonce: str) -> str:
    return base64.b64encode(private_key.sign(nonce.encode("utf-8"))).decode("ascii")


@pytest.fixture
async def biometric_user(client):
    suffix = uuid.uuid4().hex[:10]
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Biometric User",
            "email": f"biometric-{suffix}@neobank.com",
            "phone": f"+9617{suffix[:7]}",
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200
    tokens = response.json()
    private_key, public_key = _key_material()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    enrolled = await client.post(
        "/api/v1/auth/biometric/enroll",
        headers=headers,
        json={"device_id": f"test-device-{suffix}", "public_key": public_key},
    )
    assert enrolled.status_code == 200
    return private_key, headers, enrolled.json()["user_id"], enrolled.json()["device_id"]


async def _challenge(client, headers):
    response = await client.get("/api/v1/auth/biometric/challenge", headers=headers)
    assert response.status_code == 200
    return response.json()["nonce"]


async def test_biometric_happy_path_and_tokens_work(client, biometric_user):
    private_key, headers, _, device_id = biometric_user
    nonce = await _challenge(client, headers)
    response = await client.post(
        "/api/v1/auth/biometric/login",
        json={"device_id": device_id, "signed_nonce": _signature(private_key, nonce)},
    )
    assert response.status_code == 200
    tokens = response.json()
    assert set(tokens) == {"access_token", "refresh_token", "token_type"}
    assert tokens["token_type"] == "bearer"
    token_check = await client.get(
        "/api/v1/auth/biometric/challenge",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert token_check.status_code == 200


async def test_biometric_nonce_cannot_be_replayed(client, biometric_user):
    private_key, headers, _, device_id = biometric_user
    nonce = await _challenge(client, headers)
    body = {"device_id": device_id, "signed_nonce": _signature(private_key, nonce)}
    assert (await client.post("/api/v1/auth/biometric/login", json=body)).status_code == 200
    replay = await client.post("/api/v1/auth/biometric/login", json=body)
    assert replay.status_code == 401
    assert replay.json()["detail"] == "Invalid credentials"


async def test_biometric_wrong_signature_is_rejected(client, biometric_user):
    _, headers, user_id, _ = biometric_user
    wrong_key, _ = _key_material()
    nonce = await _challenge(client, headers)
    response = await client.post(
        "/api/v1/auth/biometric/login",
        json={"user_id": user_id, "signed_nonce": _signature(wrong_key, nonce)},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_biometric_expired_nonce_is_rejected(client, biometric_user, mock_redis):
    private_key, headers, _, device_id = biometric_user
    nonce = await _challenge(client, headers)
    # Delete the actual challenge key to model Redis TTL expiry.
    keys = await mock_redis.keys("challenge:*")
    if keys:
        await mock_redis.delete(*keys)
    response = await client.post(
        "/api/v1/auth/biometric/login",
        json={"device_id": device_id, "signed_nonce": _signature(private_key, nonce)},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
