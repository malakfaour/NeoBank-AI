"""Evaluate KYC face-match thresholds and DeepFace anti-spoofing on local data."""

from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from statistics import mean

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.config import settings  # noqa: E402
from ml.kyc.face_verification import check_liveness, verify_face  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent / "eval_data"
GENUINE_DIR = EVAL_DIR / "genuine_pairs"
SPOOF_DIR = EVAL_DIR / "spoof_pairs"
LIVENESS_THRESHOLD = 0.70
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@contextmanager
def detector_ready_pair(selfie: Path, id_photo: Path):
    """Upscale low-resolution LFW crops for detectors without changing their content."""
    with tempfile.TemporaryDirectory(prefix="kyc_eval_") as temp_dir:
        prepared = []
        for source in (selfie, id_photo):
            image = Image.open(source).convert("RGB")
            if min(image.size) < 224:
                scale = max(3, (224 + min(image.size) - 1) // min(image.size))
                image = image.resize(
                    (image.width * scale, image.height * scale), Image.Resampling.LANCZOS
                )
            destination = Path(temp_dir) / source.name
            image.save(destination, quality=95)
            prepared.append(destination)
        yield prepared[0], prepared[1]


def classify(scores: list[float], approve: float, flag: float) -> dict[str, int | float]:
    total = len(scores)
    counts = {
        "approved": sum(score >= approve for score in scores),
        "flagged": sum(flag <= score < approve for score in scores),
        "rejected": sum(score < flag for score in scores),
    }
    return {
        **counts,
        **{f"{name}_fraction": count / total for name, count in counts.items()},
    }


def evaluate_genuine() -> dict:
    scores = []
    failures = []
    for pair_dir in sorted(GENUINE_DIR.iterdir()):
        if not pair_dir.is_dir():
            continue
        selfie = pair_dir / "selfie.jpg"
        id_photo = pair_dir / "id_photo.jpg"
        try:
            with detector_ready_pair(selfie, id_photo) as (ready_selfie, ready_id):
                result = verify_face(str(ready_selfie), str(ready_id))
            scores.append(float(result["match_score"]))
        except Exception as exc:  # keep the full evaluation running and report bad samples
            failures.append({"pair": pair_dir.name, "error": str(exc)})

    if not scores:
        raise RuntimeError("No genuine pairs were evaluated successfully")
    current_approve = settings.KYC_MATCH_APPROVE_THRESHOLD
    current_flag = settings.KYC_MATCH_FLAG_THRESHOLD
    scenarios = {}
    for offset in (-0.05, 0.0, 0.05):
        approve = min(1.0, max(0.0, current_approve + offset))
        flag = min(approve, max(0.0, current_flag + offset))
        scenarios[f"offset_{offset:+.2f}"] = {
            "approve_threshold": approve,
            "flag_threshold": flag,
            **classify(scores, approve, flag),
        }
    return {
        "successful_pairs": len(scores),
        "failed_pairs": failures,
        "mean_score": mean(scores),
        "min_score": min(scores),
        "max_score": max(scores),
        "scenarios": scenarios,
    }


def evaluate_spoofs() -> dict:
    images = sorted(
        path for path in SPOOF_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ) if SPOOF_DIR.exists() else []
    results = []
    failures = []
    for image in images:
        try:
            result = check_liveness(str(image))
            score = float(result["antispoof_score"])
            results.append({
                "image": str(image.relative_to(SPOOF_DIR)),
                "is_real": bool(result["is_real"]),
                "antispoof_score": score,
                "incorrectly_passed": bool(result["is_real"]) and score >= LIVENESS_THRESHOLD,
            })
        except Exception as exc:
            failures.append({"image": str(image.relative_to(SPOOF_DIR)), "error": str(exc)})
    scores = [item["antispoof_score"] for item in results]
    return {
        "images_found": len(images),
        "successful_checks": len(results),
        "failed_checks": failures,
        "mean_antispoof_score": mean(scores) if scores else None,
        "min_antispoof_score": min(scores) if scores else None,
        "max_antispoof_score": max(scores) if scores else None,
        "incorrectly_passed_as_real": sum(item["incorrectly_passed"] for item in results),
        "results": results,
    }


def main() -> None:
    report = {
        "thresholds": {
            "approve": settings.KYC_MATCH_APPROVE_THRESHOLD,
            "flag": settings.KYC_MATCH_FLAG_THRESHOLD,
            "liveness": LIVENESS_THRESHOLD,
        },
        "genuine": evaluate_genuine(),
        "spoof": evaluate_spoofs(),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
