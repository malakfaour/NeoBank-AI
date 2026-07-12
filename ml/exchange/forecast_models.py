import json
from pathlib import Path

import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error

from dataset import load_exchange_dataset


def prepare_lightgbm_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    data = df.copy()

    data["day_index"] = range(len(data))

    data["day_of_week"] = data["date"].apply(
        lambda x: x.weekday()
    )

    return data


def train_lightgbm(
    df: pd.DataFrame,
) -> dict[str, float]:

    data = prepare_lightgbm_features(df)

    validation_size = 7

    train = data.iloc[:-validation_size]
    validation = data.iloc[-validation_size:]

    model = LGBMRegressor(
        n_estimators=100,
        learning_rate=0.05,
        random_state=42,
        n_jobs=1,
    )

    model.fit(
        train[
            [
                "day_index",
                "day_of_week",
            ]
        ],
        train["rate"],
    )

    predictions = model.predict(
        validation[
            [
                "day_index",
                "day_of_week",
            ]
        ]
    )

    mae = mean_absolute_error(
        validation["rate"],
        predictions,
    )

    return {
        "model": "LightGBM",
        "mae": float(mae),
    }


def train_prophet(
    df: pd.DataFrame,
) -> dict[str, float]:

    from prophet import Prophet

    prophet_df = df[
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

    validation_size = 7

    train = prophet_df.iloc[:-validation_size]
    validation = prophet_df.iloc[-validation_size:]

    model = Prophet(
        daily_seasonality=True,
    )

    model.fit(
        train
    )

    future = model.make_future_dataframe(
        periods=validation_size,
    )

    forecast = model.predict(
        future
    )

    predictions = forecast.tail(
        validation_size
    )["yhat"]

    mae = mean_absolute_error(
        validation["y"],
        predictions,
    )

    return {
        "model": "Prophet",
        "mae": float(mae),
    }


def evaluate_models(
    latest_rate: float,
) -> dict:

    dataset = load_exchange_dataset(
        latest_rate
    )

    lightgbm_result = train_lightgbm(
        dataset
    )

    prophet_result = train_prophet(
        dataset
    )

    results = [
        lightgbm_result,
        prophet_result,
    ]

    winner = min(
        results,
        key=lambda item: item["mae"],
    )

    return {
        "results": results,
        "winner": winner["model"],
    }


def write_eval_report(
    result: dict,
) -> None:

    lines = [
        "# Exchange Forecast Evaluation\n\n",
        "| Model | MAE |\n",
        "|---|---:|\n",
    ]

    for item in result["results"]:
        lines.append(
            f"| {item['model']} | {item['mae']:.4f} |\n"
        )

    lines.append(
        f"\n## Winner\n\n{result['winner']}\n"
    )

    eval_path = (
        Path(__file__).parent / "EVAL.md"
    )

    with open(
        eval_path,
        "w",
        encoding="utf-8",
    ) as file:
        file.writelines(lines)


if __name__ == "__main__":

    result = evaluate_models(
        89500
    )

    write_eval_report(
        result
    )

    print(
        json.dumps(result)
    )