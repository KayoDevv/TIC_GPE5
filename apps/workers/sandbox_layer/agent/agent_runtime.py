"""Shared scaffolding for the ELF and PDF agents: the Kafka/MinIO runtime config,
the result publisher, the UTC timestamp helper, logging, and the CLI entry point.

Format-specific logic (download/SSRF guards, weights, IOC typing, the detonation
pipeline) stays in each agent. This module does I/O (Kafka, argv) — deliberately
NOT under core/, which stays pure and golden-tested.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

# Runtime config (env, with the in-cluster defaults).
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.kafka.svc.cluster.local:9092")
TOPIC_OUT       = os.getenv("KAFKA_TOPIC_OUT", "sandbox_layer.result")
MINIO_ENDPOINT  = os.getenv("MINIO_ENDPOINT", "minio.minio.svc.cluster.local:9000")
EMAIL_CONTEXT   = json.loads(os.getenv("EMAIL_CONTEXT_JSON", "{}"))
TIMEOUT_S       = int(os.getenv("SANDBOX_TIMEOUT_S", "120"))


def get_logger(name: str) -> logging.Logger:
    """Configure stdout logging (idempotent) and return the named logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    return logging.getLogger(name)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish(job_id: str, event: dict, log: logging.Logger) -> None:
    """Publish the result event to sandbox_layer.result (sync wrapper)."""
    async def _send() -> None:
        producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await producer.start()
        try:
            await producer.send_and_wait(TOPIC_OUT, value=event)
            log.info("Published to %s job_id=%s", TOPIC_OUT, job_id)
        finally:
            await producer.stop()

    asyncio.run(_send())


def run_cli(description: str, label: str, log: logging.Logger,
            run_fn: Callable[[str, str], None]) -> None:
    """Standard agent entry point: parse --job-id/--s3-url, log start/done, run.

    `label` prefixes the start/done lines ("Agent" / "PDF Agent").
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--s3-url", required=True)
    args = parser.parse_args()

    log.info("%s started: job_id=%s", label, args.job_id)
    run_fn(args.job_id, args.s3_url)
    log.info("%s done: job_id=%s", label, args.job_id)
