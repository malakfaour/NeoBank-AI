import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.db.sync_session import SyncSessionLocal
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User
from app.services.notifications import notify_sync

logger = logging.getLogger(__name__)


def _persist_decision(
    db,
    *,
    kyc_record: KYCRecord,
    user: User,
    status: KYCRecordStatus,
    user_status: KYCStatus,
    match_score: float | None,
    liveness_score: float | None,
    rejection_reason: str | None,
    notification_type: str,
) -> dict[str, object]:
    kyc_record.status = status
    kyc_record.match_score = match_score
    kyc_record.liveness_score = liveness_score
    kyc_record.rejection_reason = rejection_reason
    kyc_record.reviewed_at = datetime.now(timezone.utc)
    kyc_record.reviewed_by = None
    user.kyc_status = user_status
    db.commit()
    db.refresh(kyc_record)
    notify_sync(
        db,
        user_id=user.id,
        notification_type=notification_type,
        metadata={
            "reason": rejection_reason,
            "match_score": match_score,
            "liveness_score": liveness_score,
            "full_name": user.full_name,
        },
    )
    return {
        "kyc_record_id": kyc_record.id,
        "status": kyc_record.status.value,
        "match_score": kyc_record.match_score,
        "liveness_score": kyc_record.liveness_score,
        "rejection_reason": kyc_record.rejection_reason,
    }


@celery_app.task(name="app.tasks.kyc_tasks.process_kyc")
def process_kyc(kyc_record_id: int):
    """No automated face-match/liveness decisioning: every submission with
    both documents present is routed to the compliance queue for a human
    to approve or reject (see admin_kyc.py)."""
    with SyncSessionLocal() as db:
        kyc_record = db.get(KYCRecord, kyc_record_id)
        if kyc_record is None:
            logger.warning("KYC record %s not found", kyc_record_id)
            return {"kyc_record_id": kyc_record_id, "status": "missing"}

        if kyc_record.status != KYCRecordStatus.pending:
            return {
                "kyc_record_id": kyc_record.id,
                "status": kyc_record.status.value,
                "match_score": kyc_record.match_score,
                "liveness_score": kyc_record.liveness_score,
                "rejection_reason": kyc_record.rejection_reason,
            }

        user = db.get(User, kyc_record.user_id)
        if user is None:
            logger.warning("User %s missing for KYC record %s", kyc_record.user_id, kyc_record_id)
            return {"kyc_record_id": kyc_record_id, "status": "missing_user"}

        if not kyc_record.selfie_url or not kyc_record.id_photo_url:
            return _persist_decision(
                db,
                kyc_record=kyc_record,
                user=user,
                status=KYCRecordStatus.flagged,
                user_status=KYCStatus.flagged,
                match_score=None,
                liveness_score=None,
                rejection_reason="documents_missing",
                notification_type="KYC_FLAGGED",
            )

        return _persist_decision(
            db,
            kyc_record=kyc_record,
            user=user,
            status=KYCRecordStatus.flagged,
            user_status=KYCStatus.flagged,
            match_score=None,
            liveness_score=None,
            rejection_reason=None,
            notification_type="KYC_FLAGGED",
        )