"""
DEVATTECH-89: train the XGBoost fraud-detection model on DS-1.

Run from the repo root or backend/ directory:
    python ml/fraud/train_fraud_xgb.py

Produces:
    backend/app/ml_models/fraud_xgb.pkl        -- sklearn Pipeline(StandardScaler, XGBClassifier)
    backend/app/ml_models/fraud_xgb_stats.json -- feature order + training metadata
    ml/fraud/EVAL.md                           -- eval report, generated from this run's actual results

Also logs holdout AUC to the model_metrics table (SyncSessionLocal --
this is an offline script, not a Celery task or FastAPI endpoint, so it
uses the same sync-DB pattern Celery tasks use, per ENGINEERING_RULES.md
section 3: never call async app services from offline scripts).

This is a standalone offline training step -- it does not touch the
running app beyond writing to model_metrics and the ml_models/ artifact
directory. Re-run whenever DS-1 (see generate_ds1.py) or model
hyperparameters change; commit the resulting .pkl/.json/EVAL.md.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    # Needed to import app.models.model_metrics / app.db.sync_session,
    # same convention as backend/tests/conftest.py.
    sys.path.insert(0, str(BACKEND_DIR))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.fraud.generate_ds1 import DS1_FRAUD_RATE, DS1_N_ROWS, DS1_SEED, FEATURE_ORDER, generate_ds1

RANDOM_SEED = DS1_SEED
TARGET_AUC = 0.82
HOLDOUT_FRACTION = 0.2

OUTPUT_DIR = BACKEND_DIR / "app" / "ml_models"
MODEL_PATH = OUTPUT_DIR / "fraud_xgb.pkl"
STATS_PATH = OUTPUT_DIR / "fraud_xgb_stats.json"
EVAL_MD_PATH = REPO_ROOT / "ml" / "fraud" / "EVAL.md"


def _make_pipeline() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("xgb", XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="auc",
            random_state=RANDOM_SEED,
        )),
    ])


def train_and_evaluate(df: pd.DataFrame) -> tuple[Pipeline, dict]:
    X = df[FEATURE_ORDER].values
    y = df["is_fraud"].values

    # --- real holdout split, set aside BEFORE any training/CV happens ---
    X_train_cv, X_holdout, y_train_cv, y_holdout = train_test_split(
        X, y,
        test_size=HOLDOUT_FRACTION,
        stratify=y,
        random_state=RANDOM_SEED,
    )

    # --- 5-fold CV on the train_cv portion only, for internal validation ---
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
    fold_aucs = []
    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X_train_cv, y_train_cv)):
        fold_pipeline = _make_pipeline()
        fold_pipeline.fit(X_train_cv[train_idx], y_train_cv[train_idx])
        val_proba = fold_pipeline.predict_proba(X_train_cv[val_idx])[:, 1]
        fold_auc = roc_auc_score(y_train_cv[val_idx], val_proba)
        fold_aucs.append(fold_auc)
        print(f"CV Fold {fold_idx + 1}/5 AUC: {fold_auc:.4f}")
    cv_mean_auc = float(np.mean(fold_aucs))
    print(f"Mean 5-fold CV AUC (train_cv only): {cv_mean_auc:.4f}")

    # --- real holdout evaluation: train on train_cv, score on UNTOUCHED holdout ---
    holdout_pipeline = _make_pipeline()
    holdout_pipeline.fit(X_train_cv, y_train_cv)
    holdout_proba = holdout_pipeline.predict_proba(X_holdout)[:, 1]
    holdout_auc = float(roc_auc_score(y_holdout, holdout_proba))
    print(f"\nHoldout AUC ({len(y_holdout)} untouched rows): {holdout_auc:.4f} (target >= {TARGET_AUC})")

    meets_target = holdout_auc >= TARGET_AUC
    if not meets_target:
        print(
            "WARNING: holdout AUC is below the target. Do not ship this "
            "artifact as-is -- consider tuning hyperparameters or revisiting "
            "DS-1 generation before deploying."
        )

    # --- shipped model: refit on the FULL dataset (train_cv + holdout) ---
    # Standard practice once holdout evaluation is done -- best use of all
    # available data for the artifact that actually goes to production.
    # holdout_auc above, not this refit, is what's reported as "the" AUC,
    # since the refit pipeline was never evaluated on truly unseen data.
    final_pipeline = _make_pipeline()
    final_pipeline.fit(X, y)

    stats = {
        "feature_order": FEATURE_ORDER,
        "trained_on_rows": len(df),
        "fraud_rate": float(y.mean()),
        "holdout_rows": len(y_holdout),
        "holdout_auc": round(holdout_auc, 4),
        "meets_target_auc": meets_target,
        "cv_auc_scores": [round(a, 4) for a in fold_aucs],
        "cv_auc_mean": round(cv_mean_auc, 4),
        "target_auc": TARGET_AUC,
        "random_seed": RANDOM_SEED,
        "sklearn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return final_pipeline, stats


def _log_auc_to_model_metrics(holdout_auc: float) -> None:
    """
    DEVATTECH-89: log holdout AUC to model_metrics. Uses SyncSessionLocal
    (app/db/sync_session.py) -- this script has no running event loop, so
    it uses the same sync-DB pattern Celery tasks use, per
    ENGINEERING_RULES.md section 3. Does NOT set mae -- mae has no
    meaning for a classification model, and was relaxed to nullable
    specifically so this insert doesn't need a fake value.
    """
    from app.db.sync_session import SyncSessionLocal
    from app.models.model_metrics import ModelMetrics

    with SyncSessionLocal() as session:
        session.add(ModelMetrics(model_name="xgboost", auc=holdout_auc))
        session.commit()
    print(f"Logged holdout_auc={holdout_auc:.4f} to model_metrics (model_name='xgboost').")


def _write_eval_md(stats: dict) -> None:
    """Generates ml/fraud/EVAL.md from this run's ACTUAL results -- never
    hand-written with placeholder/guessed numbers."""
    status_line = "PASS" if stats["meets_target_auc"] else "FAIL"
    content = f"""# Fraud Model (XGBoost) — Evaluation Report

Generated by `ml/fraud/train_fraud_xgb.py` on {stats['trained_at_utc']}.
This file is a build artifact -- re-run the training script to regenerate it
with fresh numbers; do not hand-edit the results below.

## Dataset

DS-1, generated by `ml/fraud/generate_ds1.py` (committed, seeded, fully
deterministic -- no external or manually-sourced data).

- Rows: {stats['trained_on_rows']}
- Fraud rate: {stats['fraud_rate']:.2%}
- Seed: {stats['random_seed']}

## Feature Order

Confirmed matching `app/services/fraud_scoring.py`'s `_compute_xgb_features()`
return order exactly (unchanged by this ticket):

```
{json.dumps(stats['feature_order'], indent=2)}
```

## Holdout Evaluation

- Holdout rows (never used in training): {stats['holdout_rows']}
- **Holdout AUC: {stats['holdout_auc']:.4f}**
- Target AUC: {stats['target_auc']}
- Result: **{status_line}**

5-fold CV (on the train portion only, for internal validation):
- Per-fold AUC: {stats['cv_auc_scores']}
- Mean CV AUC: {stats['cv_auc_mean']:.4f}

Note: the shipped `fraud_xgb.pkl` is refit on the FULL dataset (train +
holdout) after holdout evaluation, which is standard practice for the
production artifact. The holdout AUC above measures a pipeline trained
only on the non-holdout portion -- it is the honest generalization
estimate; it does not describe the exact shipped artifact, which has
seen more data.

## Artifact

- Model: `backend/app/ml_models/fraud_xgb.pkl`
- Stats: `backend/app/ml_models/fraud_xgb_stats.json`

## Versions Used

- scikit-learn: {stats['sklearn_version']}
- xgboost: {stats['xgboost_version']}

(Pinned identically in `backend/requirements.txt` and `ml/requirements.txt`
per ENGINEERING_RULES.md section 8.)

## How to Rerun

```bash
python ml/fraud/train_fraud_xgb.py
```

Regenerates `fraud_xgb.pkl`, `fraud_xgb_stats.json`, this file, and logs a
new `model_metrics` row (`model_name="xgboost"`, `auc=<holdout_auc>`).
"""
    EVAL_MD_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {EVAL_MD_PATH}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = generate_ds1(DS1_N_ROWS, DS1_FRAUD_RATE, DS1_SEED)
    print(f"Generated DS-1: {len(df)} rows, {int(df['is_fraud'].sum())} fraud ({df['is_fraud'].mean():.2%})")

    pipeline, stats = train_and_evaluate(df)

    joblib.dump(pipeline, MODEL_PATH)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"\nSaved model to {MODEL_PATH}")
    print(f"Saved stats to {STATS_PATH}")

    _log_auc_to_model_metrics(stats["holdout_auc"])
    _write_eval_md(stats)

    if not stats["meets_target_auc"]:
        print("\nExiting with error status: holdout AUC did not meet target.")
        sys.exit(1)


if __name__ == "__main__":
    main()
