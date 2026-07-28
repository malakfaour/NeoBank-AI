from ml.kyc.face_verification import verify_face


def test_verify_face_perfect_match(monkeypatch):
    monkeypatch.setattr(
        "ml.kyc.face_verification._deepface_verify",
        lambda id_photo_path, selfie_path: {
            "distance": 0.0,
            "threshold": 0.68,
            "verified": True,
        },
    )

    result = verify_face("selfie.jpg", "id.jpg")

    assert result == {
        "match_score": 1.0,
        "verified": True,
        "raw_distance": 0.0,
        "threshold": 0.68,
    }


def test_verify_face_partial_match(monkeypatch):
    monkeypatch.setattr(
        "ml.kyc.face_verification._deepface_verify",
        lambda id_photo_path, selfie_path: {
            "distance": 0.34,
            "threshold": 0.68,
            "verified": True,
        },
    )

    result = verify_face("selfie.jpg", "id.jpg")

    assert result["match_score"] == 0.5
    assert result["verified"] is True
    assert result["raw_distance"] == 0.34
    assert result["threshold"] == 0.68


def test_verify_face_no_match(monkeypatch):
    monkeypatch.setattr(
        "ml.kyc.face_verification._deepface_verify",
        lambda id_photo_path, selfie_path: {
            "distance": 1.2,
            "threshold": 0.68,
            "verified": False,
        },
    )

    result = verify_face("selfie.jpg", "id.jpg")

    assert result["match_score"] == 0.0
    assert result["verified"] is False


def test_verify_face_propagates_deepface_exception(monkeypatch):
    def _raise(id_photo_path, selfie_path):
        raise ValueError("No face detected")

    monkeypatch.setattr("ml.kyc.face_verification._deepface_verify", _raise)

    try:
        verify_face("selfie.jpg", "id.jpg")
    except ValueError as exc:
        assert str(exc) == "No face detected"
    else:
        raise AssertionError("Expected DeepFace exception to propagate")