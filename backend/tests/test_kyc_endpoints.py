from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.kyc_record import KYCDocumentType, KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User


async def _register_user(client, label: str) -> dict:
    suffix = uuid4().hex[:10]
    phone_suffix = f"{int(suffix, 16) % 1_000_000:06d}"
    email = f"{label.lower()}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96170{phone_suffix}",
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        user.email_verified_at = datetime.now(timezone.utc)
        await session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestPass123"},
    )
    assert login.status_code == 200, login.text
    return {**login.json(), "email": email}


@pytest.mark.anyio
@pytest.mark.parametrize("document_type", list(KYCDocumentType))
async def test_upload_kyc_enqueues_task_after_commit(client, monkeypatch, document_type):
    tokens = await _register_user(client, "kyc-upload")
    uploads = []
    delayed_ids = []

    def fake_upload_file(file_source, destination_key, bucket_name=None, extra_args=None):
        uploads.append(
            {
                "destination_key": destination_key,
                "bucket_name": bucket_name,
                "extra_args": extra_args,
                "size": len(file_source),
            }
        )
        return destination_key

    def fake_delay(kyc_record_id: int):
        delayed_ids.append(kyc_record_id)

    monkeypatch.setattr("app.api.v1.endpoints.kyc.upload_file", fake_upload_file)
    monkeypatch.setattr("app.api.v1.endpoints.kyc.process_kyc.delay", fake_delay)

    response = await client.post(
        "/api/v1/kyc/upload",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        data={"document_type": document_type.value},
        files={
            "selfie": ("selfie.jpg", b"fake-selfie", "image/jpeg"),
            "id_photo": ("id.jpg", b"fake-id", "image/jpeg"),
        },
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == KYCRecordStatus.pending.value
    assert body["document_type"] == document_type.value
    assert len(uploads) == 2
    assert [upload["extra_args"] for upload in uploads] == [
        {"ContentType": "image/jpeg"},
        {"ContentType": "image/jpeg"},
    ]
    assert delayed_ids == [body["kyc_record_id"]]

    async with AsyncSessionLocal() as session:
        record = await session.scalar(select(KYCRecord).where(KYCRecord.id == body["kyc_record_id"]))
        user = await session.scalar(select(User).where(User.id == record.user_id))
        assert record is not None
        assert record.status == KYCRecordStatus.pending
        assert record.document_type == document_type
        assert record.match_score is None
        assert record.liveness_score is None
        assert record.rejection_reason is None
        assert record.reviewed_at is None
        assert record.reviewed_by is None
        assert user.kyc_status == KYCStatus.pending


@pytest.mark.anyio
async def test_upload_kyc_requires_authentication(client):
    response = await client.post(
        "/api/v1/kyc/upload",
        files={
            "selfie": ("selfie.jpg", b"fake-selfie", "image/jpeg"),
            "id_photo": ("id.jpg", b"fake-id", "image/jpeg"),
        },
    )

    assert response.status_code in {401, 403}


@pytest.mark.anyio
async def test_selfie_draft_can_be_saved_before_identification_documents(
    client, monkeypatch
):
    tokens = await _register_user(client, "kyc-split-documents")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    uploaded_keys = []

    def fake_upload_file(file_source, destination_key, bucket_name=None, extra_args=None):
        uploaded_keys.append(destination_key)
        return destination_key

    monkeypatch.setattr("app.api.v1.endpoints.kyc.upload_file", fake_upload_file)

    selfie = await client.post(
        "/api/v1/kyc/selfie",
        headers=headers,
        files={"selfie": ("selfie.jpg", b"fake-selfie", "image/jpeg")},
    )
    assert selfie.status_code == 202, selfie.text

    documents = await client.post(
        "/api/v1/kyc/upload",
        headers=headers,
        data={"document_type": "national_id", "submit_for_review": "false"},
        files={
            "id_photo": ("front.jpg", b"fake-front", "image/jpeg"),
            "back_id_photo": ("back.jpg", b"fake-back", "image/jpeg"),
        },
    )
    assert documents.status_code == 202, documents.text
    assert documents.json()["selfie_url"] == selfie.json()["selfie_url"]
    assert len(uploaded_keys) == 3

    profile = await client.get("/api/v1/kyc/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["has_selfie"] is True
    assert profile.json()["has_front_id"] is True
    assert profile.json()["has_back_id"] is True


@pytest.mark.anyio
async def test_kyc_profile_progress_can_be_saved_and_resumed(client):
    tokens = await _register_user(client, "kyc-progress")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    initial = await client.get("/api/v1/kyc/profile", headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["workflow_status"] == "in_progress"

    saved = await client.put(
        "/api/v1/kyc/profile",
        headers=headers,
        json={
            "current_step": 3,
            "profile_data": {
                "first_name": "Rana",
                "last_name": "Haddad",
                "date_of_birth": "1995-02-10",
            },
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["current_step"] == 3

    resumed = await client.get("/api/v1/kyc/profile", headers=headers)
    assert resumed.json()["profile_data"]["first_name"] == "Rana"
    assert resumed.json()["current_step"] == 3


@pytest.mark.anyio
async def test_kyc_submission_validates_required_fields_and_consent(client):
    tokens = await _register_user(client, "kyc-required")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    await client.get("/api/v1/kyc/profile", headers=headers)

    response = await client.post(
        "/api/v1/kyc/submit",
        headers=headers,
        json={
            "terms_accepted": True,
            "information_confirmed": True,
            "privacy_consent": True,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "kyc_required_fields_missing"
    assert "identity_documents" in detail["fields"]


@pytest.mark.anyio
async def test_non_approved_user_keeps_read_access_but_money_actions_are_locked(
    client, monkeypatch
):
    tokens = await _register_user(client, "kyc-access")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setattr(
        "app.api.v1.endpoints.exchange.fetch_exchange_rates",
        AsyncMock(return_value={("USD", "LBP"): Decimal("89500")}),
    )

    balance = await client.get("/api/v1/accounts/balance", headers=headers)
    history = await client.get("/api/v1/transactions", headers=headers)
    rates = await client.get("/api/v1/exchange/rates", headers=headers)
    assert balance.status_code == 200
    assert history.status_code == 200
    assert rates.status_code == 200

    transfer = await client.post(
        "/api/v1/transactions/send",
        headers={**headers, "X-Idempotency-Key": uuid4().hex},
        json={"receiver_id": "999999", "amount": "1", "currency": "USD"},
    )
    exchange = await client.post(
        "/api/v1/exchange/execute",
        headers=headers,
        json={"from_currency": "USD", "to_currency": "LBP", "amount": "1"},
    )
    top_up = await client.post(
        "/api/v1/accounts/top-up",
        headers={**headers, "X-Idempotency-Key": uuid4().hex},
        json={"wallet_id": 1, "amount": "1", "payment_method_id": "pm_test"},
    )

    for response in (transfer, exchange, top_up):
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["error"] == "kyc_approval_required"
        assert response.json()["detail"]["route"] == "/kyc"


@pytest.mark.anyio
async def test_upload_kyc_rejects_invalid_file_type(client):
    tokens = await _register_user(client, "kyc-invalid")

    response = await client.post(
        "/api/v1/kyc/upload",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        data={"document_type": KYCDocumentType.passport.value},
        files={
            "selfie": ("selfie.txt", b"not-an-image", "text/plain"),
            "id_photo": ("id.jpg", b"fake-id", "image/jpeg"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "selfie must be a JPEG or PNG image"


@pytest.mark.anyio
async def test_upload_kyc_rejects_invalid_document_type(client):
    tokens = await _register_user(client, "kyc-invalid-document")

    response = await client.post(
        "/api/v1/kyc/upload",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        data={"document_type": "residence_permit"},
        files={
            "selfie": ("selfie.jpg", b"fake-selfie", "image/jpeg"),
            "id_photo": ("id.jpg", b"fake-id", "image/jpeg"),
        },
    )

    assert response.status_code == 422
