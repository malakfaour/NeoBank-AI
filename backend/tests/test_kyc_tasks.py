import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.kyc_record import KYCRecord, KYCRecordStatus
from app.models.notification import Notification
from app.models.user import KYCStatus, User, UserRole
from app.tasks import kyc_tasks


def _build_sync_session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine, checkfirst=True)
    KYCRecord.__table__.create(bind=engine, checkfirst=True)
    Notification.__table__.create(bind=engine, checkfirst=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_record(session_factory, *, label: str) -> tuple[int, int]:
    with session_factory() as db:
        user = User(
            full_name="KYC User",
            email=f"{label}@example.com",
            phone=f"+96170{label[-6:]}",
            password_hash="hashed",
            kyc_status=KYCStatus.pending,
            role=UserRole.customer,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        record = KYCRecord(
            user_id=user.id,
            selfie_url=f"{label}/selfie.jpg",
            id_photo_url=f"{label}/id.jpg",
            status=KYCRecordStatus.pending,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return user.id, record.id


def _install_fake_deepface(monkeypatch, *, is_real=True, antispoof_score=0.95):
    fake_module = SimpleNamespace(
        DeepFace=SimpleNamespace(
            extract_faces=lambda **kwargs: [
                {"is_real": is_real, "antispoof_score": antispoof_score}
            ]
        )
    )
    monkeypatch.setitem(sys.modules, "deepface", fake_module)


def _patch_local_files(monkeypatch):
    monkeypatch.setattr(
        kyc_tasks,
        "download_file",
        lambda source_key, destination_path: destination_path,
    )


@pytest.mark.parametrize(
    ("distance", "threshold", "verified", "expected_status", "expected_user_status", "expected_reason"),
    [
        # Confident match: verified and well under the distance/threshold ratio cutoff.
        (0.3, 1.0, True, KYCRecordStatus.approved, KYCStatus.approved, None),
        # Borderline match: verified but close to DeepFace's own threshold.
        (0.9, 1.0, True, KYCRecordStatus.flagged, KYCStatus.flagged, None),
        # Not verified by DeepFace at all.
        (1.2, 1.0, False, KYCRecordStatus.rejected, KYCStatus.rejected, "face_mismatch"),
    ],
)
def test_process_kyc_match_score_matrix(
    monkeypatch,
    distance,
    threshold,
    verified,
    expected_status,
    expected_user_status,
    expected_reason,
):
    session_factory = _build_sync_session()
    user_id, record_id = _seed_record(session_factory, label=f"matrix-{int(distance * 100)}")

    monkeypatch.setattr(kyc_tasks, "SyncSessionLocal", session_factory)
    _patch_local_files(monkeypatch)
    _install_fake_deepface(monkeypatch, is_real=True, antispoof_score=0.91)
    monkeypatch.setattr("ml.kyc.face_verification._detect_face_region", lambda path: object())
    monkeypatch.setattr("ml.kyc.face_verification._write_face_region", lambda face: "face.jpg")
    monkeypatch.setattr(
        "ml.kyc.face_verification._deepface_verify",
        lambda id_face_path, selfie_path: {
            "distance": distance,
            "threshold": threshold,
            "verified": verified,
        },
    )

    result = kyc_tasks.process_kyc(record_id)
    expected_match_score = max(0.0, min(1.0, 1 - (distance / threshold)))

    with session_factory() as db:
        record = db.get(KYCRecord, record_id)
        user = db.get(User, user_id)
        assert record.status == expected_status
        assert user.kyc_status == expected_user_status
        assert record.match_score == pytest.approx(expected_match_score)
        assert record.liveness_score == pytest.approx(0.91)
        assert record.rejection_reason == expected_reason
        assert record.reviewed_at is not None
        assert record.reviewed_by is None

    assert result["status"] == expected_status.value
    assert result["rejection_reason"] == expected_reason


def test_process_kyc_rejects_when_liveness_fails(monkeypatch):
    session_factory = _build_sync_session()
    user_id, record_id = _seed_record(session_factory, label="livefail")

    monkeypatch.setattr(kyc_tasks, "SyncSessionLocal", session_factory)
    _patch_local_files(monkeypatch)
    _install_fake_deepface(monkeypatch, is_real=False, antispoof_score=0.62)

    verify_called = False

    def _never_called(*args, **kwargs):
        nonlocal verify_called
        verify_called = True
        return {}

    monkeypatch.setattr(kyc_tasks, "verify_face", _never_called)

    result = kyc_tasks.process_kyc(record_id)

    with session_factory() as db:
        record = db.get(KYCRecord, record_id)
        user = db.get(User, user_id)
        assert record.status == KYCRecordStatus.rejected
        assert user.kyc_status == KYCStatus.rejected
        assert record.match_score is None
        assert record.liveness_score == pytest.approx(0.62)
        assert record.rejection_reason == "liveness_failed"

    assert verify_called is False
    assert result["status"] == KYCRecordStatus.rejected.value
    assert result["rejection_reason"] == "liveness_failed"


def test_process_kyc_rejects_when_no_face_detected(monkeypatch):
    session_factory = _build_sync_session()
    user_id, record_id = _seed_record(session_factory, label="noface")

    monkeypatch.setattr(kyc_tasks, "SyncSessionLocal", session_factory)
    _patch_local_files(monkeypatch)

    fake_module = SimpleNamespace(
        DeepFace=SimpleNamespace(
            extract_faces=lambda **kwargs: (_ for _ in ()).throw(
                ValueError("Face could not be detected")
            )
        )
    )
    monkeypatch.setitem(sys.modules, "deepface", fake_module)

    verify_called = False

    def _never_called(*args, **kwargs):
        nonlocal verify_called
        verify_called = True
        return {}

    monkeypatch.setattr(kyc_tasks, "verify_face", _never_called)

    result = kyc_tasks.process_kyc(record_id)

    with session_factory() as db:
        record = db.get(KYCRecord, record_id)
        user = db.get(User, user_id)
        assert record.status == KYCRecordStatus.rejected
        assert user.kyc_status == KYCStatus.rejected
        assert record.match_score is None
        assert record.liveness_score == pytest.approx(0.0)
        assert record.rejection_reason == "no_face_detected"

    assert verify_called is False
    assert result["status"] == KYCRecordStatus.rejected.value
    assert result["rejection_reason"] == "no_face_detected"
