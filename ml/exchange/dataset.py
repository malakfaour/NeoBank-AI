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
    Load real exchange history and
    backfill missing dates synthetically.
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

    min_date = df["date"].min()
    max_date = df["date"].max()

    expected_dates = set(
        pd.date_range(
            min_date,
            max_date,
        ).date
    )

    existing_dates = set(
        df["date"]
    )

    missing_dates = sorted(
        expected_dates - existing_dates
    )

    if missing_dates:
        synthetic_rows = pd.DataFrame(
            {
                "date": missing_dates,
                "rate": latest_rate,
                "synthetic": True,
            }
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