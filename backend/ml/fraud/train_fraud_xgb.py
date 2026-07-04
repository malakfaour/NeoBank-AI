"""
DEVATTECH-75: train the XGBoost fraud-detection model.

Run from the `backend/` directory:
    python ml/fraud/train_fraud_xgb.py

Produces:
    app/ml_models/fraud_xgb.pkl        -- sklearn Pipeline(StandardScaler, XGBClassifier)
    app/ml_models/fraud_xgb_stats.json -- feature order + training metadata

Requires xgboost (see requirements.txt). This is a standalone offline
training step -- it does not touch the running app, the database, or any
other ticket's code. Re-run it whenever the synthetic data generation or
model hyperparameters change; commit the resulting .pkl/.json.
"""
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

RANDOM_SEED = 42
N_ROWS = 12_000
FRAUD_RATE = 0.05
TARGET_AUC = 0.82

# Order matters -- must match app/services/fraud_scoring.py's
# _compute_xgb_features() return order exactly.
FEATURE_ORDER = [
    "amount",
    "amount_to_user_avg_ratio",
    "is_new_recipient",
    "hour_of_day",
    "day_of_week",
    "sender_tx_count_30d",
    "currency_match",
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "app", "ml_models")
MODEL_PATH = os.path.join(OUTPUT_DIR, "fraud_xgb.pkl")
STATS_PATH = os.path.join(OUTPUT_DIR, "fraud_xgb_stats.json")


def _night_weighted_hour_probs() -> np.ndarray:
    """Fraud is somewhat more likely at odd/night hours (00:00-05:00)."""
    probs = np.ones(24)
    probs[0:6] *= 3.0
    return probs / probs.sum()


def generate_synthetic_dataset(n_rows: int, fraud_rate: float, seed: int) -> pd.DataFrame:
    """
    Synthetic transaction dataset for bootstrapping the model pipeline.
    Fraudulent rows are generated with systematically different feature
    distributions (larger amounts relative to the sender's average, more
    likely to be a new recipient, skewed toward night hours, low prior
    transaction history, more currency mismatches) so there's a learnable
    signal. This is synthetic data for standing up the pipeline -- not a
    claim about real Lebanese transaction patterns. Replace with real
    labeled data (once available) by swapping this function's output for
    an actual DataFrame with the same columns.
    """
    rng = np.random.default_rng(seed)
    n_fraud = int(round(n_rows * fraud_rate))
    n_legit = n_rows - n_fraud

    legit = pd.DataFrame({
        "amount": rng.lognormal(mean=4.5, sigma=1.0, size=n_legit),
        "amount_to_user_avg_ratio": rng.lognormal(mean=0.0, sigma=0.3, size=n_legit),
        "is_new_recipient": rng.choice([0, 1], size=n_legit, p=[0.85, 0.15]),
        "hour_of_day": rng.integers(0, 24, size=n_legit),
        "day_of_week": rng.integers(0, 7, size=n_legit),
        "sender_tx_count_30d": rng.poisson(lam=8, size=n_legit),
        "currency_match": rng.choice([0, 1], size=n_legit, p=[0.05, 0.95]),
        "is_fraud": 0,
    })

    fraud = pd.DataFrame({
        "amount": rng.lognormal(mean=6.0, sigma=1.3, size=n_fraud),
        "amount_to_user_avg_ratio": rng.lognormal(mean=1.5, sigma=0.8, size=n_fraud),
        "is_new_recipient": rng.choice([0, 1], size=n_fraud, p=[0.25, 0.75]),
        "hour_of_day": rng.choice(np.arange(24), size=n_fraud, p=_night_weighted_hour_probs()),
        "day_of_week": rng.integers(0, 7, size=n_fraud),
        "sender_tx_count_30d": rng.poisson(lam=2, size=n_fraud),
        "currency_match": rng.choice([0, 1], size=n_fraud, p=[0.4, 0.6]),
        "is_fraud": 1,
    })

    df = pd.concat([legit, fraud], ignore_index=True)
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    df["amount"] = df["amount"].round(2)
    df["amount_to_user_avg_ratio"] = df["amount_to_user_avg_ratio"].round(3)
    df["sender_tx_count_30d"] = df["sender_tx_count_30d"].clip(lower=0)

    return df


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

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
    fold_aucs = []

    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        fold_pipeline = _make_pipeline()
        fold_pipeline.fit(X_train, y_train)
        val_proba = fold_pipeline.predict_proba(X_val)[:, 1]
        fold_auc = roc_auc_score(y_val, val_proba)
        fold_aucs.append(fold_auc)
        print(f"Fold {fold_idx + 1}/5 AUC: {fold_auc:.4f}")

    mean_auc = float(np.mean(fold_aucs))
    print(f"\nMean 5-fold CV AUC: {mean_auc:.4f} (target >= {TARGET_AUC})")
    if mean_auc < TARGET_AUC:
        print(
            "WARNING: mean CV AUC is below the target. Do not ship this "
            "artifact as-is -- consider tuning hyperparameters or revisiting "
            "the synthetic data generation before deploying."
        )

    # CV above is for evaluation only. The shipped model is refit on the
    # FULL dataset for the best use of available data.
    final_pipeline = _make_pipeline()
    final_pipeline.fit(X, y)

    stats = {
        "feature_order": FEATURE_ORDER,
        "trained_on_rows": len(df),
        "fraud_rate": float(y.mean()),
        "cv_auc_scores": [round(a, 4) for a in fold_aucs],
        "cv_auc_mean": round(mean_auc, 4),
        "target_auc": TARGET_AUC,
        "random_seed": RANDOM_SEED,
    }
    return final_pipeline, stats


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = generate_synthetic_dataset(N_ROWS, FRAUD_RATE, RANDOM_SEED)
    print(f"Generated {len(df)} rows, {int(df['is_fraud'].sum())} fraud ({df['is_fraud'].mean():.2%})")

    pipeline, stats = train_and_evaluate(df)

    joblib.dump(pipeline, MODEL_PATH)
    with open(STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nSaved model to {MODEL_PATH}")
    print(f"Saved stats to {STATS_PATH}")


if __name__ == "__main__":
    main()
    