from pathlib import Path

from ml.kyc import evaluate


def test_evaluate_spoofs_pins_rates(monkeypatch, tmp_path: Path):
    for label in ("live", "printed_photo", "screen_replay"):
        path = tmp_path / label / "sample.jpg"
        path.parent.mkdir()
        path.write_bytes(b"fixture")
    monkeypatch.setattr(evaluate, "check_liveness", lambda path: {
        "is_real": Path(path).parent.name == "live", "antispoof_score": 0.8
    })
    result = evaluate.evaluate_spoofs(tmp_path)
    assert result["overall_pass_rate"] == 1 / 3
    assert result["by_class"]["printed_photo"]["false_accept_rate"] == 0.0
    assert result["by_class"]["live"]["false_reject_rate"] == 0.0
