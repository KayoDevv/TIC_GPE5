import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from backend.config import Settings
from backend.services.storage import create_s3_client, upload_file

SETTINGS = Settings(
    s3_endpoint_url="https://s3.amazonaws.com",
    s3_access_key="testing",
    s3_secret_key="testing",
    s3_bucket_name="zero-trust-files",
    s3_region="us-east-1",
)


@pytest.fixture
def s3_client():
    """Create a mocked S3 client with the bucket already provisioned."""
    with mock_aws():
        client = boto3.client("s3", region_name=SETTINGS.s3_region)
        client.create_bucket(Bucket=SETTINGS.s3_bucket_name)
        yield client


class TestUploadFile:
    """Tests for S3 file upload."""

    async def test_upload_returns_s3_url(self, s3_client) -> None:
        """Upload must return an S3 URL containing bucket and job_id."""
        job_id = "abc-123"
        filename = "facture.pdf"
        data = b"fake pdf content"

        url = await upload_file(
            s3_client=s3_client,
            bucket=SETTINGS.s3_bucket_name,
            job_id=job_id,
            filename=filename,
            data=data,
        )

        assert SETTINGS.s3_bucket_name in url
        assert job_id in url
        assert filename in url

    async def test_uploaded_content_matches(self, s3_client) -> None:
        """The file stored in S3 must match the original bytes."""
        job_id = "def-456"
        filename = "malware.exe"
        data = b"\x00\x01\x02 evil bytes"

        await upload_file(
            s3_client=s3_client,
            bucket=SETTINGS.s3_bucket_name,
            job_id=job_id,
            filename=filename,
            data=data,
        )

        # Extract the S3 key from the URL
        key = f"{job_id}/{filename}"
        response = s3_client.get_object(Bucket=SETTINGS.s3_bucket_name, Key=key)
        stored_data = response["Body"].read()

        assert stored_data == data

    async def test_upload_to_missing_bucket_raises(self, s3_client) -> None:
        """Upload to a non-existent bucket must raise an exception."""
        with pytest.raises(ClientError):
            await upload_file(
                s3_client=s3_client,
                bucket="bucket-qui-nexiste-pas",
                job_id="xyz-789",
                filename="test.txt",
                data=b"content",
            )


class TestCreateS3Client:
    """Tests for S3 client factory."""

    def test_create_client_returns_client(self) -> None:
        """create_s3_client must return a boto3 S3 client."""
        with mock_aws():
            client = create_s3_client(SETTINGS)
            assert client is not None
