# Liveness / spoof evaluation (DEVATTECH-129)

Real captured evaluation images are still pending. Place 5–10 images per
class in `eval_data/spoof_dataset/` as described by its README: a live selfie,
a photo of that selfie printed on paper, and a photo of it displayed on a
screen. No evaluation result is claimed until those real images exist.

`evaluate_spoofs(dataset_dir)` calls the same `ml.kyc.liveness.check_liveness`
used by the Celery KYC task, with DeepFace anti-spoofing enabled and the
configured `KYC_LIVENESS_THRESHOLD` (currently 0.70). It reports overall pass,
false-accept, false-reject, and per-class rates.

```powershell
python -c "from ml.kyc.evaluate import evaluate_spoofs; import json; print(json.dumps(evaluate_spoofs('ml/kyc/eval_data/spoof_dataset'), indent=2))"
```

No decision about MobileNetV2 can be made from synthetic proxy data. Do not
treat this as validating that MobileNetV2 is unnecessary—re-evaluate once the
dataset contains real captured images. If warranted, adding MobileNetV2 is a
follow-up ticket.
