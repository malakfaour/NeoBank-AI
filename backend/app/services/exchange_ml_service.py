import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def train_and_evaluate_models(
    latest_rate,
) -> dict:

    ml_python = sys.executable

    result = subprocess.run(
        [
            ml_python,
            "-m",
            "ml.exchange.forecast_models",
            str(latest_rate),
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr
        )

    output_lines = (
        result.stdout
        .strip()
        .splitlines()
    )

    return json.loads(
        output_lines[-1]
    )