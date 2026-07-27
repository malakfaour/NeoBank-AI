from unittest.mock import Mock

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
        extra_args={"ContentType": "image/jpeg"},
    )

    object_head = client.head_object(Bucket="test-bucket", Key="kyc/dummy-selfie.jpg")
    assert result == "kyc/dummy-selfie.jpg"
    assert object_head["ServerSideEncryption"] == "AES256"


def test_upload_file_forces_sse_in_client_params(monkeypatch):
    client = Mock()
    monkeypatch.setattr(storage, "storage_client", client)
    monkeypatch.setattr(storage.settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(storage.settings, "S3_ENDPOINT_URL", "")

    storage.upload_file(
        b"avatar",
        "avatars/user.jpg",
        extra_args={"ContentType": "image/jpeg"},
    )

    client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="avatars/user.jpg",
        Body=b"avatar",
        ContentType="image/jpeg",
        ServerSideEncryption="AES256",
    )


def test_upload_file_omits_sse_for_minio_and_preserves_metadata(monkeypatch):
    client = Mock()
    monkeypatch.setattr(storage, "storage_client", client)
    monkeypatch.setattr(storage.settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(
        storage.settings, "S3_ENDPOINT_URL", "http://localhost:9100"
    )

    storage.upload_file(
        b"selfie",
        "kyc/selfie.jpg",
        extra_args={"ContentType": "image/jpeg"},
    )

    client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="kyc/selfie.jpg",
        Body=b"selfie",
        ContentType="image/jpeg",
    )


def test_upload_file_removes_caller_sse_for_minio_after_merge(monkeypatch):
    client = Mock()
    monkeypatch.setattr(storage, "storage_client", client)
    monkeypatch.setattr(storage.settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(
        storage.settings, "S3_ENDPOINT_URL", "http://localhost:9100"
    )

    storage.upload_file(
        "selfie.jpg",
        "kyc/selfie.jpg",
        extra_args={
            "ContentType": "image/jpeg",
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": "test-key-id",
            "SSECustomerAlgorithm": "AES256",
            "SSECustomerKey": "test-customer-key",
            "SSECustomerKeyMD5": "test-customer-key-md5",
        },
    )

    client.upload_file.assert_called_once_with(
        "selfie.jpg",
        "test-bucket",
        "kyc/selfie.jpg",
        ExtraArgs={"ContentType": "image/jpeg"},
    )


@mock_aws
def test_get_presigned_url_returns_url_for_existing_object(monkeypatch):
    client = _configure_storage(monkeypatch)
    client.put_object(Bucket="test-bucket", Key="kyc/dummy-selfie.jpg", Body=b"sample-selfie")

    presigned_url = storage.get_presigned_url("kyc/dummy-selfie.jpg")

    assert presigned_url.startswith("https://")
    assert "kyc/dummy-selfie.jpg" in presigned_url


def test_get_presigned_url_caps_ttl_at_one_hour(monkeypatch):
    client = Mock()
    client.generate_presigned_url.return_value = "https://example.test/presigned"
    monkeypatch.setattr(storage, "storage_client", client)
    monkeypatch.setattr(storage.settings, "S3_BUCKET", "test-bucket")

    storage.get_presigned_url("kyc/document.jpg", ttl_seconds=7200)

    client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "kyc/document.jpg"},
        ExpiresIn=3600,
    )


def test_delete_file_deletes_object(monkeypatch):
    client = Mock()
    monkeypatch.setattr(storage, "storage_client", client)
    monkeypatch.setattr(storage.settings, "S3_BUCKET", "test-bucket")

    storage.delete_file("avatars/old.jpg")

    client.delete_object.assert_called_once_with(
        Bucket="test-bucket", Key="avatars/old.jpg"
    )
