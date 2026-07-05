from __future__ import annotations

from typing import Any

try:
    import boto3
except ImportError:  # pragma: no cover - covered indirectly once boto3 is installed
    boto3 = None

from app.core.config import settings


def _get_bucket_name() -> str:
    return settings.S3_BUCKET or settings.AWS_BUCKET_NAME or "neobank-kyc"


def _get_region_name() -> str:
    return settings.S3_REGION or settings.AWS_REGION


def _build_storage_client() -> Any | None:
    if boto3 is None:
        return None

    bucket_name = _get_bucket_name()
    region_name = _get_region_name()

    if not all(
        [
            bucket_name,
            region_name,
            settings.AWS_ACCESS_KEY_ID,
            settings.AWS_SECRET_ACCESS_KEY,
        ]
    ):
        return None

    client_kwargs = {
        "service_name": "s3",
        "region_name": region_name,
        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
    }

    if settings.S3_ENDPOINT_URL:
        client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

    return boto3.client(**client_kwargs)


storage_client = _build_storage_client()


def _require_storage_client() -> Any:
    global storage_client
    if storage_client is None:
        storage_client = _build_storage_client()
    if storage_client is None:
        raise RuntimeError("S3 storage client is not configured")
    return storage_client


def upload_file(
    file_source: str | bytes,
    destination_key: str,
    bucket_name: str | None = None,
    extra_args: dict[str, Any] | None = None,
) -> str:
    client = _require_storage_client()
    resolved_bucket = bucket_name or _get_bucket_name()
    resolved_extra_args = extra_args or {}

    if isinstance(file_source, bytes):
        client.put_object(
            Bucket=resolved_bucket,
            Key=destination_key,
            Body=file_source,
            **resolved_extra_args,
        )
        return destination_key

    upload_kwargs: dict[str, Any] = {}
    if resolved_extra_args:
        upload_kwargs["ExtraArgs"] = resolved_extra_args
    client.upload_file(file_source, resolved_bucket, destination_key, **upload_kwargs)
    return destination_key


def get_presigned_url(s3_key: str, ttl_seconds: int = 3600) -> str:
    client = _require_storage_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _get_bucket_name(), "Key": s3_key},
        ExpiresIn=ttl_seconds,
    )
