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


def test_evaluate_spoofs_records_failures_by_class(monkeypatch, tmp_path: Path):
    image = tmp_path / "screen_replay" / "broken.jpg"
    image.parent.mkdir()
    image.write_bytes(b"fixture")

    def fail_liveness(_path):
        raise RuntimeError("unreadable image")

    monkeypatch.setattr(evaluate, "check_liveness", fail_liveness)

    result = evaluate.evaluate_spoofs(tmp_path)

    assert result["failed_checks"] == [
        {"image": str(Path("screen_replay") / "broken.jpg"), "error": "unreadable image"}
    ]
    assert result["by_class"]["screen_replay"]["errors"] == 1
