from __future__ import annotations

import tempfile
from pathlib import Path


def _detect_face_region(image_path: str):
    import cv2

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to load image: {image_path}")

    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    try:
        from mtcnn import MTCNN

        detector = MTCNN()
        detections = detector.detect_faces(rgb_image)
    except Exception:
        detections = []

    if detections:
        x, y, width, height = detections[0]["box"]
        x = max(x, 0)
        y = max(y, 0)
        return image[y : y + max(height, 1), x : x + max(width, 1)]

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(grayscale, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        raise ValueError("No face detected in ID photo")

    x, y, width, height = faces[0]
    return image[y : y + height, x : x + width]


def _write_face_region(face_region) -> str:
    import cv2

    if face_region.size == 0:
        raise ValueError("Detected face region is empty")

    temp_file = tempfile.NamedTemporaryFile(prefix="kyc_id_face_", suffix=".jpg", delete=False)
    temp_file.close()
    if not cv2.imwrite(temp_file.name, face_region):
        raise ValueError("Failed to persist extracted ID face")
    return temp_file.name


def _deepface_verify(id_face_path: str, selfie_path: str) -> dict:
    from deepface import DeepFace

    return DeepFace.verify(
        img1_path=id_face_path,
        img2_path=selfie_path,
        model_name="ArcFace",
        enforce_detection=True,
    )


def verify_face(selfie_path: str, id_photo_path: str) -> dict:
    extracted_face_path: str | None = None

    try:
        face_region = _detect_face_region(id_photo_path)
        extracted_face_path = _write_face_region(face_region)
        result = _deepface_verify(extracted_face_path, selfie_path)

        raw_distance = float(result["distance"])
        threshold = float(result["threshold"])
        # ArcFace distance is normalized against the threshold returned by DeepFace
        # so the score stays in a stable 0-1 range where 1 is the best possible match.
        match_score = max(0.0, 1 - (raw_distance / threshold))

        return {
            "match_score": match_score,
            "verified": bool(result["verified"]),
            "raw_distance": raw_distance,
            "threshold": threshold,
        }
    finally:
        if extracted_face_path:
            Path(extracted_face_path).unlink(missing_ok=True)
