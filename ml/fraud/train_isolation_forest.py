"""
DEVATTECH-84: Isolation Forest cold-start fraud model.

Generates a synthetic dataset (2000 rows) and trains an IsolationForest
to flag anomalous transactions for users with fewer than 5 transactions
-- too few for XGBoost (NBL-109) to have meaningful history on.

Run this script directly (from ml/, with ml/venv active) to regenerate
the model. Outputs go to ml/fraud/artifacts/:
  - isolation_forest.pkl        (the trained model)
  - isolation_forest_stats.json (amount mean/std used to compute
    amount_zscore -- inference must reuse these exact values so scores
    are computed consistently, not the live population's stats)
"""

import json
import os

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

RANDOM_SEED = 42
N_ROWS = 2000
CONTAMINATION = 0.05
N_OUTLIERS = int(N_ROWS * CONTAMINATION)
N_NORMAL = N_ROWS - N_OUTLIERS

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "backend", "app", "ml_models"
)

def generate_dataset(rng: np.random.Generator):
    """
    Returns (features, raw_amounts) where features is an (N_ROWS, 4) array
    of [amount_zscore, hour_of_day, is_new_recipient, currency_flag], and
    raw_amounts is the underlying synthetic amount used only to compute
    amount_zscore (not itself a feature).
    """
    # --- normal transactions ---
    # Amounts: right-skewed, like real transaction amounts (lognormal).
    normal_amounts = rng.lognormal(mean=4.0, sigma=1.0, size=N_NORMAL)
    normal_hours = rng.integers(0, 24, size=N_NORMAL)
    # Most transactions are to known recipients.
    normal_is_new_recipient = rng.choice(
        [0, 1], size=N_NORMAL, p=[0.7, 0.3]
    )
    # Currency mismatches are rare in normal traffic.
    normal_currency_flag = rng.choice(
        [0, 1], size=N_NORMAL, p=[0.95, 0.05]
    )

    # --- deliberate outliers ---
    # Mix of unusually large and unusually small/erratic amounts.
    outlier_amounts = np.concatenate([
        rng.lognormal(mean=7.5, sigma=1.2, size=N_OUTLIERS // 2),  # very large
        rng.uniform(0.01, 5, size=N_OUTLIERS - N_OUTLIERS // 2),   # oddly tiny
    ])
    # Late-night hours, associated with unusual activity.
    outlier_hours = rng.integers(1, 5, size=N_OUTLIERS)
    # Outliers skew heavily toward new recipients and currency mismatches.
    outlier_is_new_recipient = rng.choice(
        [0, 1], size=N_OUTLIERS, p=[0.2, 0.8]
    )
    outlier_currency_flag = rng.choice(
        [0, 1], size=N_OUTLIERS, p=[0.2, 0.8]
    )

    all_amounts = np.concatenate([normal_amounts, outlier_amounts])
    all_hours = np.concatenate([normal_hours, outlier_hours])
    all_is_new_recipient = np.concatenate(
        [normal_is_new_recipient, outlier_is_new_recipient]
    )
    all_currency_flag = np.concatenate(
        [normal_currency_flag, outlier_currency_flag]
    )

    amount_mean = float(all_amounts.mean())
    amount_std = float(all_amounts.std())
    amount_zscore = (all_amounts - amount_mean) / amount_std

    features = np.column_stack([
        amount_zscore,
        all_hours,
        all_is_new_recipient,
        all_currency_flag,
    ])

    # Shuffle so outliers aren't all clustered at the end.
    shuffle_idx = rng.permutation(N_ROWS)
    features = features[shuffle_idx]

    return features, amount_mean, amount_std


def main():
    rng = np.random.default_rng(RANDOM_SEED)
    features, amount_mean, amount_std = generate_dataset(rng)

    model = IsolationForest(
        contamination=CONTAMINATION,
        random_state=RANDOM_SEED,
    )
    model.fit(features)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    model_path = os.path.join(OUTPUT_DIR, "isolation_forest.pkl")
    joblib.dump(model, model_path)

    stats_path = os.path.join(OUTPUT_DIR, "isolation_forest_stats.json")
    with open(stats_path, "w") as f:
        json.dump(
            {
                "amount_mean": amount_mean,
                "amount_std": amount_std,
                "feature_order": [
                    "amount_zscore",
                    "hour_of_day",
                    "is_new_recipient",
                    "currency_flag",
                ],
                "trained_on_rows": N_ROWS,
                "contamination": CONTAMINATION,
                "random_seed": RANDOM_SEED,
            },
            f,
            indent=2,
        )

    print(f"Model saved to {model_path}")
    print(f"Stats saved to {stats_path}")
    print(f"amount_mean={amount_mean:.2f}, amount_std={amount_std:.2f}")


if __name__ == "__main__":
    main()
