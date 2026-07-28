# KYC face-verification accuracy evaluation

`eval_face_accuracy.py` measures real-world matching accuracy of
`ml.kyc.face_verification.verify_face` using the LFW (Labeled Faces in
the Wild) dataset. It is **not** committed with any dataset - LFW is tens
of thousands of images and does not belong in git history.

It reports two things:

1. **The actual production decision** (approved / flagged / rejected),
   computed the same way as `backend/app/tasks/kyc_tasks.py`: DeepFace's
   own `verified` boolean, gated by a distance/threshold ratio against
   `MATCH_CONFIDENT_RATIO` (currently duplicated as a constant at the top
   of the eval script - keep it in sync with `kyc_tasks.py` if you change
   one).
2. **`match_score` distribution** - informational only. This score
   (`1 - distance/threshold`) is *not* used for decisioning; it does not
   separate genuine from impostor pairs cleanly enough to threshold on
   (see `ml/kyc/face_verification.py` for why). It's reported purely so
   you can see it's not being relied on.

## Getting the dataset

Download the LFW "deepfunneled" image set plus the pair-list CSVs. The
Kaggle mirror used for this project is:
https://www.kaggle.com/datasets/jessicali9530/lfw-dataset

(Any LFW deepfunneled distribution works, as long as the pair CSVs listed
below are included or downloaded alongside it from
http://vis-www.cs.umass.edu/lfw/)

## Where to place it

Create a `Data-kyc/` folder at the repo root (already gitignored) and
extract the archive into it, so the layout looks like: