from moto import mock_aws

from app.core import storage


def _configure_storage(monkeypatch):
    monkeypatch.setattr(storage.settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(storage.settings, "S3_REGION", "eu-central-1")
    monkeypatch.setattr(storage.settings, "AWS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(storage.settings, "AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(storage.settings, "S3_ENDPOINT_URL", "")
    client = storage._build_storage_client()
    storage.storage_client = client
    client.create_bucket(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
    )
    return client


@mock_aws
def test_upload_file_uploads_object_with_sse(monkeypatch, tmp_path):
    client = _configure_storage(monkeypatch)
    upload_path = tmp_path / "dummy-selfie.jpg"
    upload_path.write_bytes(b"sample-selfie")

    result = storage.upload_file(
        str(upload_path),
        "kyc/dummy-selfie.jpg",
        extra_args={"ServerSideEncryption": "AES256"},
    )

    object_head = client.head_object(Bucket="test-bucket", Key="kyc/dummy-selfie.jpg")
    assert result == "kyc/dummy-selfie.jpg"
    assert object_head["ServerSideEncryption"] == "AES256"


@mock_aws
def test_get_presigned_url_returns_url_for_existing_object(monkeypatch):
    client = _configure_storage(monkeypatch)
    client.put_object(Bucket="test-bucket", Key="kyc/dummy-selfie.jpg", Body=b"sample-selfie")

    presigned_url = storage.get_presigned_url("kyc/dummy-selfie.jpg")

    assert presigned_url.startswith("https://")
    assert "kyc/dummy-selfie.jpg" in presigned_url
