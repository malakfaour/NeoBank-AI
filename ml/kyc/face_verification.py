from __future__ import annotations


def _deepface_verify(id_photo_path: str, selfie_path: str) -> dict:
    from deepface import DeepFace

    # Let DeepFace detect the face in both the raw ID photo and the raw
    # selfie itself, rather than pre-cropping the ID photo ourselves first.
    # retinaface (a strong pretrained detector, more robust to angle/lighting
    # than DeepFace's weak "opencv" default) fails when run on an already
    # tightly-cropped face-only image with no surrounding context, so
    # detection must run on the original uncropped photos.
    return DeepFace.verify(
        img1_path=id_photo_path,
        img2_path=selfie_path,
        model_name="ArcFace",
        detector_backend="retinaface",
        enforce_detection=True,
    )


def verify_face(selfie_path: str, id_photo_path: str) -> dict:
    result = _deepface_verify(id_photo_path, selfie_path)

    raw_distance = float(result["distance"])
    threshold = float(result["threshold"])
    # Genuine ArcFace matches typically sit well under the verification
    # threshold (not near zero), so scale relative to a distance of
    # 0 = perfect match and threshold = the boundary DeepFace itself
    # already calibrated as "same person". This keeps match_score
    # informational/diagnostic - the approve/reject decision uses
    # DeepFace's own `verified` boolean, not a threshold on this score.
    match_score = max(0.0, min(1.0, 1 - (raw_distance / threshold)))

    return {
        "match_score": match_score,
        "verified": bool(result["verified"]),
        "raw_distance": raw_distance,
        "threshold": threshold,
    }