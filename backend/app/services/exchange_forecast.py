from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor


def train_and_forecast_usd_lbp(
    latest_rate: Decimal,
    days: int = 7,
) -> list[dict[str, Decimal | date]]:
    """
    Simple LightGBM forecast model for USD -> LBP.

    Since we do not have real historical exchange-rate data yet,
    this creates a small synthetic training series around the latest rate.
    Later, this can be replaced with real historical exchange_rate rows.
    """

    latest_rate_float = float(latest_rate)
    history_days = 60

    historical_dates = [
        date.today() - timedelta(days=history_days - i)
        for i in range(history_days)
    ]

    trend = np.linspace(
        latest_rate_float * 0.97,
        latest_rate_float,
        history_days,
    )
    seasonal_noise = np.sin(np.arange(history_days) / 4) * (
        latest_rate_float * 0.002
    )

    rates = trend + seasonal_noise

    df = pd.DataFrame(
        {
            "date": historical_dates,
            "day_index": np.arange(history_days),
            "day_of_week": [d.weekday() for d in historical_dates],
            "rate": rates,
        }
    )

    x_train = df[["day_index", "day_of_week"]]
    y_train = df["rate"]

    model = LGBMRegressor(
        n_estimators=80,
        learning_rate=0.05,
        random_state=42,
    )

    model.fit(x_train, y_train)

    future_dates = [
        date.today() + timedelta(days=i)
        for i in range(1, days + 1)
    ]

    future_df = pd.DataFrame(
        {
            "day_index": np.arange(history_days, history_days + days),
            "day_of_week": [d.weekday() for d in future_dates],
        }
    )

    predictions = model.predict(future_df)

    return [
        {
            "date": future_dates[i],
            "predicted_rate": Decimal(str(round(float(predictions[i]), 4))),
        }
        for i in range(days)
    ]