from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd


DATA_FILE = (
    Path(__file__).parent
    / "data"
    / "exchange_rates.csv"
)


def generate_synthetic_history(
    start_date,
    end_date,
    latest_rate: float,
) -> pd.DataFrame:
    """
    Generate missing exchange rows.

    Synthetic rows are explicitly marked.
    """

    dates = pd.date_range(
        start=start_date,
        end=end_date,
    )

    trend = np.linspace(
        latest_rate * 0.99,
        latest_rate,
        len(dates),
    )

    noise = np.sin(
        np.arange(len(dates)) / 4
    ) * (latest_rate * 0.002)

    return pd.DataFrame(
        {
            "date": dates.date,
            "rate": trend + noise,
            "synthetic": True,
        }
    )

def load_exchange_dataset(
    latest_rate: float,
) -> pd.DataFrame:
    """
    Load exchange history.
    Backfill to provide enough history for forecasting models.
    """

    df = pd.read_csv(
        DATA_FILE,
        parse_dates=["date"],
    )

    df["date"] = df["date"].dt.date
    df["synthetic"] = (
        df["synthetic"]
        .astype(bool)
    )

    # Extend history to 180 days for ML training
    min_date = df["date"].min()

    required_start = (
        pd.Timestamp(max_date := min_date)
        - pd.Timedelta(days=180)
    ).date()

    existing_dates = set(df["date"])

    missing_dates = sorted(
        set(
            pd.date_range(
                required_start,
                min_date - timedelta(days=1),
            ).date
        )
        - existing_dates
    )

    if missing_dates:
        synthetic_rows = generate_synthetic_history(
            missing_dates[0],
            missing_dates[-1],
            latest_rate,
        )

        df = pd.concat(
            [
                df,
                synthetic_rows,
            ],
            ignore_index=True,
        )

    return df.sort_values(
        "date"
    ).reset_index(drop=True)