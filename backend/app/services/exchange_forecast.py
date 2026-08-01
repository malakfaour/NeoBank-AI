import logging
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

logger = logging.getLogger(__name__)


def _build_synthetic_history(
    latest_rate: Decimal,
    history_days: int = 60,
) -> pd.DataFrame:

    latest_rate_float = float(latest_rate)

    historical_dates = [
        date.today() - timedelta(days=history_days - i)
        for i in range(history_days)
    ]

    trend = np.linspace(
        latest_rate_float * 0.97,
        latest_rate_float,
        history_days,
    )

    seasonal_noise = (
        np.sin(np.arange(history_days) / 4)
        * (latest_rate_float * 0.002)
    )

    rates = trend + seasonal_noise

    return pd.DataFrame(
        {
            "date": historical_dates,
            "day_index": np.arange(history_days),
            "day_of_week": [
                d.weekday()
                for d in historical_dates
            ],
            "rate": rates,
        }
    )


def _train_lightgbm(
    history_df: pd.DataFrame,
    days: int,
):

    model = LGBMRegressor(
        n_estimators=80,
        learning_rate=0.05,
        random_state=42,
        n_jobs=1,
    )

    validation_window = min(
        7,
        max(
            1,
            len(history_df) // 4,
        ),
    )

    train_df = history_df.iloc[:-validation_window]
    validation_df = history_df.iloc[-validation_window:]

    model.fit(
        train_df[
            [
                "day_index",
                "day_of_week",
            ]
        ],
        train_df["rate"],
    )

    validation_predictions = model.predict(
        validation_df[
            [
                "day_index",
                "day_of_week",
            ]
        ]
    )

    mae = float(
        np.mean(
            np.abs(
                validation_predictions
                - validation_df["rate"].to_numpy()
            )
        )
    )

    model.fit(
        history_df[
            [
                "day_index",
                "day_of_week",
            ]
        ],
        history_df["rate"],
    )

    future_dates = [
        date.today() + timedelta(days=i)
        for i in range(1, days + 1)
    ]

    future_df = pd.DataFrame(
        {
            "day_index": np.arange(
                len(history_df),
                len(history_df) + days,
            ),
            "day_of_week": [
                d.weekday()
                for d in future_dates
            ],
        }
    )

    predictions = model.predict(
        future_df
    )

    return {
        "mae": round(mae, 4),
        "predictions": [
            {
                "date": future_dates[i],
                "predicted_rate": Decimal(
                    str(
                        round(
                            float(predictions[i]),
                            4,
                        )
                    )
                ),
            }
            for i in range(days)
        ],
    }


def _train_prophet(
    history_df: pd.DataFrame,
    days: int,
):

    try:
        from prophet import Prophet

        train = history_df[
            [
                "date",
                "rate",
            ]
        ].rename(
            columns={
                "date": "ds",
                "rate": "y",
            }
        )

        model = Prophet()

        model.fit(train)

        future = model.make_future_dataframe(
            periods=days
        )

        forecast = model.predict(
            future
        )

        predictions = forecast.tail(days)

        return {
            "mae": 0.0,
            "predictions": [
                {
                    "date": row.ds.date(),
                    "predicted_rate": Decimal(
                        str(
                            round(
                                float(row.yhat),
                                4,
                            )
                        )
                    ),
                }
                for _, row in predictions.iterrows()
            ],
        }

    except Exception as e:

        logger.exception(
            "Prophet forecast failed: %s",
            e,
        )

        return {
            "mae": float("inf"),
            "predictions": [],
            "error": str(e),
        }


def train_evaluate_and_forecast_usd_lbp(
    latest_rate: Decimal,
    days: int = 7,
    model_name: str = "LightGBM",
):

    history_df = _build_synthetic_history(
        latest_rate
    )

    if model_name.lower() == "prophet":
        return _train_prophet(
            history_df,
            days,
        )

    return _train_lightgbm(
        history_df,
        days,
    )


def train_and_forecast_usd_lbp(
    latest_rate: Decimal,
    days: int = 7,
    model_name: str = "LightGBM",
):

    return train_evaluate_and_forecast_usd_lbp(
        latest_rate,
        days,
        model_name,
    )["predictions"]