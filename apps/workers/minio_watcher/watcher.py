"""minio-watcher — MinIO events → FileRequestedEvent transformer.

Listens on the `minio.events` topic (native MinIO S3 notifications),
extracts the key of the uploaded object, generates a presigned URL and
publishes a FileRequestedEvent to `file.requested`.

No human interaction required: as soon as a file lands in the MinIO
bucket, the sandbox pipeline triggers automatically.

Environment variables:
    KAFKA_BOOTSTRAP          default: kafka:29092
    MINIO_TOPIC_IN           default: minio.events
    KAFKA_TOPIC_OUT          default: file.requested
    MINIO_ENDPOINT           default: minio:9000
    MINIO_PRESIGN_ENDPOINT   default: MINIO_ENDPOINT
    MINIO_ACCESS_KEY         default: minioadmin
    MINIO_SECRET_KEY         default: minioadmin
    MINIO_BUCKET             default: sandbox-reports
    PRESIGN_TTL_HOURS        default: 1
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from minio import Minio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("minio-watcher")

KAFKA_BOOTSTRAP        = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
MINIO_TOPIC_IN         = os.getenv("MINIO_TOPIC_IN", "minio.events")
KAFKA_TOPIC_OUT        = os.getenv("KAFKA_TOPIC_OUT", "file.requested")
MINIO_ENDPOINT         = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_PRESIGN_ENDPOINT = os.getenv("MINIO_PRESIGN_ENDPOINT", MINIO_ENDPOINT)
MINIO_ACCESS_KEY       = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY       = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET           = os.getenv("MINIO_BUCKET", "sandbox-reports")
PRESIGN_TTL_HOURS      = int(os.getenv("PRESIGN_TTL_HOURS", "1"))


def _minio_client(endpoint: str) -> Minio:
    return Minio(endpoint, access_key=MINIO_ACCESS_KEY,
                 secret_key=MINIO_SECRET_KEY, secure=False)


def _sha256_object(client: Minio, bucket: str, key: str) -> str:
    """Compute the SHA-256 of the MinIO object without writing it to disk."""
    response = client.get_object(bucket, key)
    try:
        h = hashlib.sha256()
        for chunk in response.stream(1024 * 64):
            h.update(chunk)
        return h.hexdigest()
    finally:
        response.close()
        response.release_conn()


def _presigned_url(key: str) -> str:
    client = _minio_client(MINIO_PRESIGN_ENDPOINT)
    return client.presigned_get_object(
        MINIO_BUCKET, key, expires=timedelta(hours=PRESIGN_TTL_HOURS)
    )


def _parse_minio_event(raw: dict) -> list[dict]:
    """Extract object keys from a MinIO S3-style event.

    MinIO sends either a root object with a 'Records' key, or the list of
    records directly, depending on the version.
    """
    records = raw.get("Records") or raw.get("records") or []
    objects = []
    for record in records:
        event_name = record.get("eventName", "")
        if "ObjectCreated" not in event_name:
            continue
        s3 = record.get("s3", {})
        bucket = s3.get("bucket", {}).get("name", "")
        key = s3.get("object", {}).get("key", "")
        if bucket and key:
            objects.append({"bucket": bucket, "key": key})
    return objects


async def process(raw_value: bytes, producer: AIOKafkaProducer) -> None:
    try:
        payload = json.loads(raw_value.decode("utf-8"))
    except json.JSONDecodeError:
        log.warning("Non-JSON message ignored")
        return

    objects = _parse_minio_event(payload)
    if not objects:
        return

    client = _minio_client(MINIO_ENDPOINT)

    for obj in objects:
        bucket = obj["bucket"]
        key = obj["key"]

        if bucket != MINIO_BUCKET:
            log.debug("Bucket %s ignored (expected: %s)", bucket, MINIO_BUCKET)
            continue

        log.info("New file detected: %s/%s", bucket, key)

        try:
            sha256 = _sha256_object(client, bucket, key)
            url = _presigned_url(key)
        except Exception as exc:
            log.error("MinIO access error for %s: %s", key, exc)
            continue

        job_id = str(uuid.uuid4())
        event = {
            "job_id": job_id,
            "s3_url": url,
            "sha256": sha256,
            "email_context": {
                "sender": "unknown@ingestion.internal",
                "subject": f"Auto-ingested: {key.split('/')[-1]}",
                "body_text": f"File automatically ingested from MinIO: {key}",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await producer.send_and_wait(
            KAFKA_TOPIC_OUT,
            value=json.dumps(event).encode("utf-8"),
        )
        log.info(
            "FileRequestedEvent published: job_id=%s sha256=%s...",
            job_id, sha256[:16],
        )


async def run() -> None:
    consumer = AIOKafkaConsumer(
        MINIO_TOPIC_IN,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="minio-watcher-v1",
        auto_offset_reset="latest",
    )
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)

    await consumer.start()
    await producer.start()
    log.info(
        "minio-watcher started — listening %s → publishing to %s",
        MINIO_TOPIC_IN, KAFKA_TOPIC_OUT,
    )

    try:
        async for msg in consumer:
            await process(msg.value, producer)
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Stop requested")


if __name__ == "__main__":
    main()
