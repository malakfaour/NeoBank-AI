import sys
import types

from ml.kyc.liveness import LIVENESS_THRESHOLD, check_liveness


def test_check_liveness_uses_deepface_boundary(monkeypatch):
    class FakeDeepFace:
        @staticmethod
        def extract_faces(**kwargs):
            assert kwargs["anti_spoofing"] is True
            return [{"is_real": True, "antispoof_score": 0.8}]
    monkeypatch.setitem(sys.modules, "deepface", types.SimpleNamespace(DeepFace=FakeDeepFace))
    result = check_liveness("fixture.jpg")
    assert result["passed"] is True
    assert LIVENESS_THRESHOLD == 0.7
