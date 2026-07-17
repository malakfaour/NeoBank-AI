from __future__ import annotations

LIVENESS_THRESHOLD = 0.7


def _extract_faces(image_path: str) -> list[dict]:
    """Call the external DeepFace anti-spoofing boundary."""
    from deepface import DeepFace

    return DeepFace.extract_faces(
        img_path=image_path,
        anti_spoofing=True,
        enforce_detection=True,
    )


def check_liveness(image_path: str) -> dict[str, bool | float]:
    """Return the deployed DeepFace decision, score, and thresholded outcome."""
    faces = _extract_faces(image_path)
    if not faces:
        raise ValueError("No face detected in selfie")

    face = faces[0]
    is_real = bool(face.get("is_real", False))
    score = float(face.get("antispoof_score", 0.0))
    return {
        "is_real": is_real,
        "antispoof_score": score,
        "passed": is_real and score >= LIVENESS_THRESHOLD,
    }


def require_liveness(image_path: str) -> float:
    """Return the score for a live image or raise the production rejection."""
    result = check_liveness(image_path)
    score = float(result["antispoof_score"])
    if not result["passed"]:
        raise RuntimeError(f"liveness_failed:{score}")
    return score
