from uuid import uuid4
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.kyc_audit_log import KYCAuditLog
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


async def _create_record(
    user_id: int,
    suffix: str,
    *,
    status: KYCRecordStatus = KYCRecordStatus.flagged,
    created_at: datetime | None = None,
) -> int:
    async with AsyncSessionLocal() as session:
        record = KYCRecord(
            user_id=user_id,
            selfie_url=f"{suffix}/selfie.jpg",
            id_photo_url=f"{suffix}/id.jpg",
            match_score=0.7,
            liveness_score=0.9,
            status=status,
            created_at=created_at,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def _create_flagged_record(user_id: int, suffix: str) -> int:
    return await _create_record(user_id, suffix)


async def _assert_audit(record_id: int, action: str, actor_id: int) -> None:
    async with AsyncSessionLocal() as session:
        audit = await session.scalar(
            select(KYCAuditLog).where(KYCAuditLog.kyc_record_id == record_id)
        )
        assert audit is not None
        assert audit.action == action
        assert audit.actor_id == actor_id


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
        "app.api.v1.endpoints.admin_kyc.get_presigned_url",
        lambda key: f"https://signed.example/{key}",
    )

    response = await client.get(
        "/api/v1/admin/kyc/queue",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [first_record_id, second_record_id]
    assert body["items"][0]["selfie_presigned_url"].endswith("/older/selfie.jpg")
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 2
    assert body["total_pages"] == 1


@pytest.mark.anyio
async def test_admin_kyc_queue_filters_status_date_and_paginates(client):
    admin_tokens = await _register_user(client, "adminfilters")
    customer_tokens = await _register_user(client, "filtercustomer")
    _, token = await _promote_user(admin_tokens["email"], UserRole.admin)
    customer, _ = await _promote_user(customer_tokens["email"], UserRole.customer)
    old = datetime.now(timezone.utc) + timedelta(days=1)
    recent = datetime.now(timezone.utc) + timedelta(days=2)
    await _create_record(customer.id, "old", created_at=old)
    recent_id = await _create_record(customer.id, "recent", created_at=recent)
    await _create_record(customer.id, "approved", status=KYCRecordStatus.approved)

    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get(
        "/api/v1/admin/kyc/queue",
        params={"status": "flagged", "date_from": (recent - timedelta(minutes=1)).isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [recent_id]

    approved = await client.get(
        "/api/v1/admin/kyc/queue",
        params={"status": "approved", "page": 1, "page_size": 1},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["total"] == 1
    assert approved.json()["page_size"] == 1

    capped = await client.get(
        "/api/v1/admin/kyc/queue",
        params={"page_size": 101},
        headers=headers,
    )
    assert capped.status_code == 422


@pytest.mark.anyio
async def test_admin_approve_kyc_updates_record_and_user(client, monkeypatch):
    admin_tokens = await _register_user(client, "adminapprove")
    customer_tokens = await _register_user(client, "customerapprove")
    admin, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.compliance_officer)
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
    await _assert_audit(record_id, "kyc_approved", admin.id)


@pytest.mark.anyio
async def test_admin_reject_kyc_sets_rejection_reason(client, monkeypatch):
    admin_tokens = await _register_user(client, "adminreject")
    customer_tokens = await _register_user(client, "customerreject")
    admin, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.admin)
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
    await _assert_audit(record_id, "kyc_rejected", admin.id)


@pytest.mark.anyio
async def test_admin_request_resubmit_marks_record_rejected(client, monkeypatch):
    admin_tokens = await _register_user(client, "adminresubmit")
    customer_tokens = await _register_user(client, "customerresubmit")
    admin, admin_access_token = await _promote_user(admin_tokens["email"], UserRole.admin)
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
    await _assert_audit(record_id, "kyc_resubmit_requested", admin.id)


@pytest.mark.anyio
async def test_admin_kyc_queue_requires_authentication(client):
    response = await client.get("/api/v1/admin/kyc/queue")
    assert response.status_code in {401, 403}


@pytest.mark.anyio
async def test_admin_kyc_queue_rejects_customer_role(client):
    customer_tokens = await _register_user(client, "queuecustomer")
    _, token = await _promote_user(customer_tokens["email"], UserRole.customer)
    response = await client.get(
        "/api/v1/admin/kyc/queue",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
