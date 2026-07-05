from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User


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
async def test_upload_kyc_enqueues_task_after_commit(client, monkeypatch):
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
        files={
            "selfie": ("selfie.jpg", b"fake-selfie", "image/jpeg"),
            "id_photo": ("id.jpg", b"fake-id", "image/jpeg"),
        },
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == KYCRecordStatus.pending.value
    assert len(uploads) == 2
    assert delayed_ids == [body["kyc_record_id"]]

    async with AsyncSessionLocal() as session:
        record = await session.scalar(select(KYCRecord).where(KYCRecord.id == body["kyc_record_id"]))
        user = await session.scalar(select(User).where(User.id == record.user_id))
        assert record is not None
        assert record.status == KYCRecordStatus.pending
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
async def test_upload_kyc_rejects_invalid_file_type(client):
    tokens = await _register_user(client, "kyc-invalid")

    response = await client.post(
        "/api/v1/kyc/upload",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        files={
            "selfie": ("selfie.txt", b"not-an-image", "text/plain"),
            "id_photo": ("id.jpg", b"fake-id", "image/jpeg"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "selfie must be a JPEG or PNG image"
