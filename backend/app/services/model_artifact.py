from pathlib import Path
import os
import shutil


MODEL_DIR = Path(__file__).resolve().parents[1] / "ml_models"

MODEL_PATH = MODEL_DIR / "exchange_forecast.pkl"
PREVIOUS_MODEL_PATH = MODEL_DIR / "exchange_forecast.pkl.prev"
TEMP_MODEL_PATH = MODEL_DIR / "exchange_forecast.pkl.tmp"


def ensure_model_dir():
    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def backup_current_model():
    ensure_model_dir()

    if MODEL_PATH.exists():
        shutil.copy2(
            MODEL_PATH,
            PREVIOUS_MODEL_PATH,
        )


def atomic_save(temp_path: Path = TEMP_MODEL_PATH):
    ensure_model_dir()

    os.replace(
        temp_path,
        MODEL_PATH,
    )


def rollback_model():
    if PREVIOUS_MODEL_PATH.exists():
        shutil.copy2(
            PREVIOUS_MODEL_PATH,
            MODEL_PATH,
        )


def model_exists():
    return MODEL_PATH.exists()