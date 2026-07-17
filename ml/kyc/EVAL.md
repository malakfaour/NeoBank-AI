# Liveness / spoof evaluation (DEVATTECH-129)

The committed `eval_data/spoof_dataset` is a small synthetic proxy: three live
face crops and copies labelled `printed_photo` and `screen_replay`. It contains
no real capture data and therefore cannot establish production spoof resistance.
The source face crops are from the existing LFW-derived fixtures; redistribution
and licensing limitations are documented in the parent evaluation materials.

`evaluate_spoofs(dataset_dir)` calls the same `ml.kyc.liveness.check_liveness`
used by the Celery KYC task, with DeepFace anti-spoofing enabled and the single
production threshold `LIVENESS_THRESHOLD = 0.70`. It reports overall pass rate,
false-accept rate (spoofs accepted), false-reject rate (live rejected), and
breakdowns for live, printed-photo, and screen-replay labels. Run:

```powershell
python -c "from ml.kyc.evaluate import evaluate_spoofs; import json; print(json.dumps(evaluate_spoofs('ml/kyc/eval_data/spoof_dataset'), indent=2))"
```

Because DeepFace weights and a capture-realistic dataset are not available in
this environment, no measured production metric is claimed here. The synthetic
proxy is a harness/fixture, not validation. Consequently the MobileNetV2
classifier from the plan is **not needed based on these numbers**: the numbers
are not decision-quality. A representative, consented capture set should be
evaluated first; adding MobileNetV2, if warranted, is a follow-up ticket.
