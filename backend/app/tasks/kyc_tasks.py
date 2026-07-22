import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.celery_app import celery_app
from app.core.config import settings
from app.core.storage import download_file
from app.db.sync_session import SyncSessionLocal
from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.user import KYCStatus, User
from app.services.notifications import notify_sync

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.kyc.face_verification import verify_face  # noqa: E402
from ml.kyc.liveness import require_liveness  # noqa: E402

logger = logging.getLogger(__name__)


def _run_liveness_check(selfie_path: str) -> float:
    return require_liveness(selfie_path)


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
    selfie_temp = tempfile.NamedTemporaryFile(prefix="kyc_selfie_", suffix=".jpg", delete=False)
    id_temp = tempfile.NamedTemporaryFile(prefix="kyc_id_", suffix=".jpg", delete=False)
    selfie_temp.close()
    id_temp.close()

    try:
        with SyncSessionLocal() as db:
            kyc_record = db.get(KYCRecord, kyc_record_id)
            if kyc_record is None:
                logger.warning(
                    "KYC record %s not found",
                    kyc_record_id,
                    extra={"kyc_record_id": kyc_record_id},
                )
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
                logger.warning(
                    "User %s missing for KYC record %s",
                    kyc_record.user_id,
                    kyc_record_id,
                    extra={"kyc_record_id": kyc_record_id, "user_id": kyc_record.user_id},
                )
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

            download_file(kyc_record.selfie_url, selfie_temp.name)
            download_file(kyc_record.id_photo_url, id_temp.name)

            try:
                liveness_score = _run_liveness_check(selfie_temp.name)
            except RuntimeError as exc:
                reason, _, score = str(exc).partition(":")
                parsed_score = float(score) if score else 0.0
                return _persist_decision(
                    db,
                    kyc_record=kyc_record,
                    user=user,
                    status=KYCRecordStatus.rejected,
                    user_status=KYCStatus.rejected,
                    match_score=None,
                    liveness_score=parsed_score,
                    rejection_reason=reason,
                    notification_type="KYC_REJECTED",
                )

            verification = verify_face(selfie_temp.name, id_temp.name)
            match_score = float(verification["match_score"])

            if match_score >= settings.KYC_MATCH_APPROVE_THRESHOLD:
                return _persist_decision(
                    db,
                    kyc_record=kyc_record,
                    user=user,
                    status=KYCRecordStatus.approved,
                    user_status=KYCStatus.approved,
                    match_score=match_score,
                    liveness_score=liveness_score,
                    rejection_reason=None,
                    notification_type="KYC_APPROVED",
                )

            if match_score >= settings.KYC_MATCH_FLAG_THRESHOLD:
                return _persist_decision(
                    db,
                    kyc_record=kyc_record,
                    user=user,
                    status=KYCRecordStatus.flagged,
                    user_status=KYCStatus.flagged,
                    match_score=match_score,
                    liveness_score=liveness_score,
                    rejection_reason=None,
                    notification_type="KYC_FLAGGED",
                )

            return _persist_decision(
                db,
                kyc_record=kyc_record,
                user=user,
                status=KYCRecordStatus.rejected,
                user_status=KYCStatus.rejected,
                match_score=match_score,
                liveness_score=liveness_score,
                rejection_reason="face_mismatch",
                notification_type="KYC_REJECTED",
            )
    except Exception:
        logger.exception(
            "KYC processing failed for record %s",
            kyc_record_id,
            extra={"kyc_record_id": kyc_record_id},
        )
        with SyncSessionLocal() as db:
            kyc_record = db.get(KYCRecord, kyc_record_id)
            if kyc_record is not None:
                user = db.get(User, kyc_record.user_id)
                if user is not None:
                    _persist_decision(
                        db,
                        kyc_record=kyc_record,
                        user=user,
                        status=KYCRecordStatus.flagged,
                        user_status=KYCStatus.flagged,
                        match_score=kyc_record.match_score,
                        liveness_score=kyc_record.liveness_score,
                        rejection_reason="processing_failed",
                        notification_type="KYC_FLAGGED",
                    )
        raise
    finally:
        Path(selfie_temp.name).unlink(missing_ok=True)
        Path(id_temp.name).unlink(missing_ok=True)
