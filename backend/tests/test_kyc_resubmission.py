from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User, UserRole


async def _register_user(client, label: str) -> dict:
    suffix = uuid4().hex[:10]
    email = f"{label}-{suffix}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"{label} User",
            "email": email,
            "phone": f"+96171{suffix[:6]}",
            "password": "TestPass123",
        },
    )
    assert response.status_code == 200, response.text
    return {**response.json(), "email": email}


async def _promote_to_admin(email: str) -> str:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        user.role = UserRole.admin
        await session.commit()
        token, _ = create_access_token(str(user.id), role=UserRole.admin.value)
        return token


def _upload_files(round_name: str) -> dict:
    return {
        "selfie": (f"{round_name}-selfie.jpg", b"fake-selfie", "image/jpeg"),
        "id_photo": (f"{round_name}-id.jpg", b"fake-id", "image/jpeg"),
    }


@pytest.mark.anyio
async def test_kyc_resubmission_full_loop_retains_old_s3_objects(client, monkeypatch):
    customer_tokens = await _register_user(client, "resubmit-customer")
    admin_tokens = await _register_user(client, "resubmit-admin")
    admin_access_token = await _promote_to_admin(admin_tokens["email"])

    uploaded_objects: dict[str, bytes] = {}
    delayed_ids: list[int] = []
    timestamps = iter([1_700_000_000, 1_700_000_100])
    notify = AsyncMock(return_value=1)

    def fake_upload_file(file_source, destination_key, bucket_name=None, extra_args=None):
        uploaded_objects[destination_key] = file_source
        return destination_key

    monkeypatch.setattr("app.api.v1.endpoints.kyc.upload_file", fake_upload_file)
    monkeypatch.setattr(
        "app.api.v1.endpoints.kyc.process_kyc.delay",
        lambda record_id: delayed_ids.append(record_id),
    )
    monkeypatch.setattr("app.api.v1.endpoints.kyc.time", lambda: next(timestamps))
    monkeypatch.setattr("app.api.v1.endpoints.admin.notify", notify)

    customer_headers = {
        "Authorization": f"Bearer {customer_tokens['access_token']}"
    }
    first = await client.post(
        "/api/v1/kyc/upload",
        headers=customer_headers,
        files=_upload_files("first"),
    )
    assert first.status_code == 202, first.text
    first_body = first.json()
    first_keys = {first_body["selfie_url"], first_body["id_photo_url"]}
    assert first_body["status"] == KYCRecordStatus.pending.value
    assert delayed_ids == [first_body["kyc_record_id"]]

    duplicate = await client.post(
        "/api/v1/kyc/upload",
        headers=customer_headers,
        files=_upload_files("duplicate"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "KYC verification is already processing"
    assert set(uploaded_objects) == first_keys
    assert delayed_ids == [first_body["kyc_record_id"]]
    notify.assert_not_awaited()

    async with AsyncSessionLocal() as session:
        record = await session.get(KYCRecord, first_body["kyc_record_id"])
        user = await session.get(User, record.user_id)
        record.status = KYCRecordStatus.approved
        user.kyc_status = KYCStatus.approved
        await session.commit()

    resubmit_request = await client.post(
        f"/api/v1/admin/kyc/{first_body['kyc_record_id']}/request-resubmit",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )
    assert resubmit_request.status_code == 200, resubmit_request.text
    assert resubmit_request.json()["status"] == KYCRecordStatus.rejected.value
    assert resubmit_request.json()["rejection_reason"] == "resubmit_requested"
    notify.assert_awaited_once()

    second = await client.post(
        "/api/v1/kyc/upload",
        headers=customer_headers,
        files=_upload_files("second"),
    )
    assert second.status_code == 202, second.text
    second_body = second.json()
    second_keys = {second_body["selfie_url"], second_body["id_photo_url"]}
    assert second_body["kyc_record_id"] == first_body["kyc_record_id"]
    assert second_body["status"] == KYCRecordStatus.pending.value
    assert second_keys.isdisjoint(first_keys)
    assert set(uploaded_objects) == first_keys | second_keys
    assert delayed_ids == [first_body["kyc_record_id"], first_body["kyc_record_id"]]
    notify.assert_awaited_once()

    async with AsyncSessionLocal() as session:
        record = await session.get(KYCRecord, first_body["kyc_record_id"])
        user = await session.get(User, record.user_id)
        assert record.status == KYCRecordStatus.pending
        assert {record.selfie_url, record.id_photo_url} == second_keys
        assert record.rejection_reason is None
        assert record.reviewed_at is None
        assert record.reviewed_by is None
        assert user.kyc_status == KYCStatus.pending
