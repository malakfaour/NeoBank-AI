from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User, UserRole


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


async def _promote_user(email: str, role: UserRole) -> tuple[User, str]:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        user.role = role
        await session.commit()
        await session.refresh(user)
        token, _ = create_access_token(str(user.id), role=user.role.value)
        return user, token


async def _create_flagged_record(user_id: int, suffix: str) -> int:
    async with AsyncSessionLocal() as session:
        record = KYCRecord(
            user_id=user_id,
            selfie_url=f"{suffix}/selfie.jpg",
            id_photo_url=f"{suffix}/id.jpg",
            match_score=0.7,
            liveness_score=0.9,
            status=KYCRecordStatus.flagged,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


@pytest.mark.anyio
async def test_admin_kyc_queue_returns_flagged_records_oldest_first(client, monkeypatch):
    admin_tokens = await _register_user(client, "adminqueue")
    flagged_one = await _register_user(client, "flaggedone")
    flagged_two = await _register_user(client, "flaggedtwo")
    _, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.admin)
    user_one = await _promote_user(flagged_one["email"], UserRole.customer)
    user_two = await _promote_user(flagged_two["email"], UserRole.customer)
    first_record_id = await _create_flagged_record(user_one[0].id, "older")
    second_record_id = await _create_flagged_record(user_two[0].id, "newer")

    monkeypatch.setattr(
        "app.api.v1.endpoints.admin.get_presigned_url",
        lambda key: f"https://signed.example/{key}",
    )

    response = await client.get(
        "/api/v1/admin/kyc/queue",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body] == [first_record_id, second_record_id]
    assert body[0]["selfie_presigned_url"].endswith("/older/selfie.jpg")


@pytest.mark.anyio
async def test_admin_approve_kyc_updates_record_and_user(client, monkeypatch):
    admin_tokens = await _register_user(client, "adminapprove")
    customer_tokens = await _register_user(client, "customerapprove")
    _, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.compliance_officer)
    customer, _ = await _promote_user(customer_tokens["email"], UserRole.customer)
    record_id = await _create_flagged_record(customer.id, "approve")

    monkeypatch.setattr("app.services.notifications.send_email", lambda *args, **kwargs: None)

    response = await client.patch(
        f"/api/v1/admin/kyc/{record_id}/approve",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == KYCRecordStatus.approved.value
    assert response.json()["user_kyc_status"] == KYCStatus.approved.value


@pytest.mark.anyio
async def test_admin_reject_kyc_sets_rejection_reason(client, monkeypatch):
    admin_tokens = await _register_user(client, "adminreject")
    customer_tokens = await _register_user(client, "customerreject")
    _, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.admin)
    customer, _ = await _promote_user(customer_tokens["email"], UserRole.customer)
    record_id = await _create_flagged_record(customer.id, "reject")

    monkeypatch.setattr("app.services.notifications.send_email", lambda *args, **kwargs: None)

    response = await client.patch(
        f"/api/v1/admin/kyc/{record_id}/reject",
        headers={"Authorization": f"Bearer {admin_access_token}"},
        json={"rejection_reason": "document_blurry"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == KYCRecordStatus.rejected.value
    assert response.json()["rejection_reason"] == "document_blurry"


@pytest.mark.anyio
async def test_admin_request_resubmit_marks_record_rejected(client, monkeypatch):
    admin_tokens = await _register_user(client, "adminresubmit")
    customer_tokens = await _register_user(client, "customerresubmit")
    _, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.admin)
    customer, _ = await _promote_user(customer_tokens["email"], UserRole.customer)
    record_id = await _create_flagged_record(customer.id, "resubmit")

    monkeypatch.setattr("app.services.notifications.send_email", lambda *args, **kwargs: None)

    response = await client.post(
        f"/api/v1/admin/kyc/{record_id}/request-resubmit",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == KYCRecordStatus.rejected.value
    assert response.json()["rejection_reason"] == "resubmit_requested"


@pytest.mark.anyio
async def test_admin_kyc_queue_requires_authentication(client):
    response = await client.get("/api/v1/admin/kyc/queue")
    assert response.status_code in {401, 403}
