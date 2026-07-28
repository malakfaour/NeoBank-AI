"""
One-time setup: creates the neobank-kyc bucket in local MinIO if it
doesn't exist yet, and uploads the two trained fraud model artifacts
to the exact S3 keys fraud_scoring.py's _ensure_model_file_available()
fetches from (ml-models/fraud/fraud_xgb.pkl,
ml-models/fraud/isolation_forest.pkl).

Run from backend/, with the venv active:
    python upload_fraud_models.py

Requires: MinIO running (docker compose up minio -d), and the two
.pkl files already present locally at app/ml_models/ (produced by
running ml/fraud/train_fraud_xgb.py and
ml/fraud/train_isolation_forest.py from the repo root).
"""
import pathlib

from app.core.storage import _get_bucket_name, _get_region_name, _require_storage_client, upload_file

MODELS_DIR = pathlib.Path(__file__).resolve().parent / "app" / "ml_models"

FILES_TO_UPLOAD = [
    (MODELS_DIR / "fraud_xgb.pkl", "ml-models/fraud/fraud_xgb.pkl"),
    (MODELS_DIR / "isolation_forest.pkl", "ml-models/fraud/isolation_forest.pkl"),
]


def ensure_bucket_exists() -> None:
    client = _require_storage_client()
    bucket = _get_bucket_name()
    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if bucket in existing:
        print(f"Bucket '{bucket}' already exists.")
        return

    region = _get_region_name()
    # S3's CreateBucket API only accepts a bare Bucket= call for
    # us-east-1 -- every other region requires an explicit
    # LocationConstraint or AWS rejects it with
    # IllegalLocationConstraintException. MinIO is lenient about this,
    # but doing it correctly here means this also works unmodified if
    # this ever points at real AWS S3 instead of local MinIO.
    if region and region != "us-east-1":
        client.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
    else:
        client.create_bucket(Bucket=bucket)
    print(f"Created bucket '{bucket}'.")


def main() -> None:
    ensure_bucket_exists()

    for local_path, s3_key in FILES_TO_UPLOAD:
        if not local_path.exists():
            print(f"SKIP (not found locally): {local_path}")
            continue
        upload_file(str(local_path), s3_key)
        size_kb = local_path.stat().st_size / 1024
        print(f"Uploaded {local_path.name} ({size_kb:.0f} KB) -> s3://{_get_bucket_name()}/{s3_key}")

    print("\nDone. Restart uvicorn and the Celery worker so the next fraud score fetches these fresh.")


if __name__ == "__main__":
    main()