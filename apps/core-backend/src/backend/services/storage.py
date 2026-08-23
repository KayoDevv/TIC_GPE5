import asyncio
import logging
import re
from functools import partial
from typing import Any

import boto3

from backend.config import Settings

logger = logging.getLogger(__name__)

# The object name lands in an s3:// URL that consumers re-parse with urlparse,
# so a '?' or '#' in it would silently truncate the key on their side.
UNSAFE_OBJECT_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")
MAX_OBJECT_NAME_LENGTH = 128


def create_s3_client(settings: Settings) -> Any:
    """
    Create a boto3 S3 client configured for S3 or MinIO.

    Returns a standard boto3 S3 client instance.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def safe_object_name(filename: str) -> str:
    """Reduce an attacker-controlled filename to a URL-safe S3 object name."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = UNSAFE_OBJECT_NAME_CHARS.sub("_", name).lstrip(".")
    return name[:MAX_OBJECT_NAME_LENGTH] or "file"


async def upload_file(
    s3_client: Any,
    bucket: str,
    job_id: str,
    filename: str,
    data: bytes,
) -> str:
    """
    Upload raw bytes to S3/MinIO under the key {job_id}/{filename}.

    Runs the blocking boto3 call in a thread executor
    to avoid blocking the async event loop.

    Returns:
        The S3 URL of the uploaded object: s3://{bucket}/{job_id}/{filename}
    """
    key = f"{job_id}/{safe_object_name(filename)}"
    loop = asyncio.get_running_loop()

    await loop.run_in_executor(
        None,
        partial(_upload_sync, s3_client, bucket, key, data),
    )

    s3_url = f"s3://{bucket}/{key}"
    logger.info(f"File uploaded to {s3_url}")
    return s3_url


def _upload_sync(s3_client: Any, bucket: str, key: str, data: bytes) -> None:
    """Synchronous S3 put_object call."""
    s3_client.put_object(Bucket=bucket, Key=key, Body=data)
