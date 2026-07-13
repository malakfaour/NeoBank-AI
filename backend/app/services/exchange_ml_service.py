import json
import pickle
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

from app.services.model_artifact import (
    TEMP_MODEL_PATH,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def save_temp_model_artifact(
    evaluation: dict,
):
    """
    Creates a temporary exchange forecast artifact.

    The task later decides whether to promote it
    or rollback.
    """

    TEMP_MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact = {
        "model": evaluation["winner"],
        "mae": min(
            item["mae"]
            for item in evaluation["results"]
        ),
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    with open(
        TEMP_MODEL_PATH,
        "wb",
    ) as file:
        pickle.dump(
            artifact,
            file,
        )


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

    evaluation = json.loads(
        output_lines[-1]
    )

    # DEVATTECH-98
    save_temp_model_artifact(
        evaluation
    )

    return evaluation