import sys
import types

from ml.kyc.liveness import check_liveness, liveness_threshold, require_liveness


def test_check_liveness_uses_deepface_boundary(monkeypatch):
    class FakeDeepFace:
        @staticmethod
        def extract_faces(**kwargs):
            assert kwargs["anti_spoofing"] is True
            return [{"is_real": True, "antispoof_score": 0.8}]
    monkeypatch.setitem(sys.modules, "deepface", types.SimpleNamespace(DeepFace=FakeDeepFace))
    result = check_liveness("fixture.jpg")
    assert result["passed"] is True
    assert liveness_threshold() == 0.7


def test_require_liveness_returns_score(monkeypatch):
    monkeypatch.setattr("ml.kyc.liveness.check_liveness", lambda _: {
        "is_real": True, "antispoof_score": 0.9, "passed": True
    })
    assert require_liveness("fixture.jpg") == 0.9
