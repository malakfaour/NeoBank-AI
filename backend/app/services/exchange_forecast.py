from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor


def _build_synthetic_history(latest_rate: Decimal, history_days: int = 60) -> pd.DataFrame:
    latest_rate_float = float(latest_rate)
    historical_dates = [
        date.today() - timedelta(days=history_days - i)
        for i in range(history_days)
    ]

    trend = np.linspace(latest_rate_float * 0.97, latest_rate_float, history_days)
    seasonal_noise = np.sin(np.arange(history_days) / 4) * (latest_rate_float * 0.002)
    rates = trend + seasonal_noise

    return pd.DataFrame(
        {
            "date": historical_dates,
            "day_index": np.arange(history_days),
            "day_of_week": [d.weekday() for d in historical_dates],
            "rate": rates,
        }
    )


def train_evaluate_and_forecast_usd_lbp(
    latest_rate: Decimal,
    days: int = 7,
) -> dict[str, float | list[dict[str, Decimal | date]]]:
    """
    Simple LightGBM forecast model for USD -> LBP.

    Since we do not have real historical exchange-rate data yet,
    this creates a small synthetic training series around the latest rate.
    Later, this can be replaced with real historical exchange_rate rows.
    """
    history_df = _build_synthetic_history(latest_rate)

    validation_window = min(7, max(1, len(history_df) // 4))
    train_df = history_df.iloc[:-validation_window]
    validation_df = history_df.iloc[-validation_window:]

    model = LGBMRegressor(n_estimators=80, learning_rate=0.05, random_state=42, n_jobs=1)
    model.fit(train_df[["day_index", "day_of_week"]], train_df["rate"])
    validation_predictions = model.predict(validation_df[["day_index", "day_of_week"]])
    mae = float(np.mean(np.abs(validation_predictions - validation_df["rate"].to_numpy())))

    model.fit(history_df[["day_index", "day_of_week"]], history_df["rate"])
    history_days = len(history_df)

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

    return {
        "mae": round(mae, 4),
        "predictions": [
            {
                "date": future_dates[i],
                "predicted_rate": Decimal(str(round(float(predictions[i]), 4))),
            }
            for i in range(days)
        ],
    }


def train_and_forecast_usd_lbp(
    latest_rate: Decimal,
    days: int = 7,
) -> list[dict[str, Decimal | date]]:
    return train_evaluate_and_forecast_usd_lbp(latest_rate, days)["predictions"]
async def fetch_exchange_rates() -> dict[tuple[str, str], Decimal]:
    """
    Async exchange-rate fetcher for API endpoints.
    Fetches live rates from open.er-api.com.
    """
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get("https://open.er-api.com/v6/latest/USD")
        response.raise_for_status()

    data = response.json()
    if data.get("result") != "success":
        raise RuntimeError("Exchange rate provider returned unsuccessful response")

    provider_rates = data.get("rates", {})
    usd_to_lbp = provider_rates.get("LBP")
    usd_to_eur = provider_rates.get("EUR")

    if usd_to_lbp is None:
        raise RuntimeError("LBP rate was not found")

    rates = {
        ("USD", "LBP"): Decimal(str(usd_to_lbp)),
        ("LBP", "USD"): Decimal("1") / Decimal(str(usd_to_lbp)),
    }
    if usd_to_eur:
        rates[("USD", "EUR")] = Decimal(str(usd_to_eur))
        rates[("EUR", "USD")] = Decimal("1") / Decimal(str(usd_to_eur))

    return rates