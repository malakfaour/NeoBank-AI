from decimal import Decimal
import subprocess
import json


def train_and_evaluate_models(
    latest_rate: Decimal,
) -> dict:
    """
    Runs ML evaluation from the top-level ml package.
    Backend does not import ml directly.
    """

    result = subprocess.run(
        [
            "python",
            "-m",
            "ml.exchange.forecast_models",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout)