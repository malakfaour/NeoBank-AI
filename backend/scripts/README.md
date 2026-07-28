# KYC face-verification accuracy evaluation

`eval_face_accuracy.py` measures real-world matching accuracy (True Accept
Rate / False Accept Rate) of `ml.kyc.face_verification.verify_face` using
the LFW (Labeled Faces in the Wild) dataset. It is **not** committed with
any dataset - LFW is tens of thousands of images and does not belong in
git history.

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

```
NeoBank-AI/
  Data-kyc/
    archive/
      lfw-deepfunneled/
        lfw-deepfunneled/           <- note: Kaggle nests an extra level
          George_W_Bush/
            George_W_Bush_0001.jpg
            George_W_Bush_0002.jpg
            ...
          Colin_Powell/
            ...
      matchpairsDevTest.csv
      matchpairsDevTrain.csv
      mismatchpairsDevTest.csv
      mismatchpairsDevTrain.csv
      pairs.csv
      people.csv
      peopleDevTest.csv
      peopleDevTrain.csv
      lfw_allnames.csv
      lfw_readme.csv
```

Verify the exact nesting before running the script:

```powershell
dir Data-kyc\archive\lfw-deepfunneled
dir Data-kyc\archive\lfw-deepfunneled\lfw-deepfunneled
```

If the second `dir` shows person-name folders (e.g. `George_W_Bush`),
use that nested path as `--images-dir`.

## Running the evaluation

```powershell
python backend\scripts\eval_face_accuracy.py `
  --images-dir Data-kyc\archive\lfw-deepfunneled\lfw-deepfunneled `
  --match-csv Data-kyc\archive\matchpairsDevTest.csv `
  --match-csv Data-kyc\archive\matchpairsDevTrain.csv `
  --mismatch-csv Data-kyc\archive\mismatchpairsDevTest.csv `
  --limit 300
```

Drop `--limit` (or raise it) once a smoke run with a small limit succeeds
cleanly, to run the full dataset.

Requires the ML dependencies installed (`pip install -r backend/requirements.txt -r ml/requirements.txt`).

Note: LFW only tests face-matching accuracy (same person vs. different
person). It has no spoof/liveness samples, so it cannot be used to
evaluate `_run_liveness_check`'s anti-spoofing accuracy.
