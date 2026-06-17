"""Corpus feeder — iterates a folder, uploads to MinIO, publishes to file.requested.

Idempotent: the feeder writes its state to validation/feeder_state.duckdb
(corpus + sent jobs). Received results go to validation/results.duckdb, written
by the validator (see db.py — DBs are split to avoid the lock conflict).
  - Re-run with the same --run-id → skips what was already sent.
  - --repetitions N → sends each file N times (determinism test).
  - --max-inflight N → throttle so KEDA/the queue is not saturated.

Expected corpus layout:
    <corpus_root>/
      benign/       → label = benign
      malicious/    → label = malicious
      unknown/      → label = unknown    (or any other folder name not listed)

Usage:
    python -m scripts.validation.feeder \\
        --corpus validation/corpus \\
        --run-id 2026-04-29_run1 \\
        --repetitions 2 \\
        --max-inflight 30
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiokafka import AIOKafkaProducer
from minio import Minio

from . import db

# ---------------------------------------------------------------------------
# Config (env vars, docker-compose defaults)
# ---------------------------------------------------------------------------

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "sandbox-reports")
MINIO_PRESIGN_ENDPOINT = os.getenv("MINIO_PRESIGN_ENDPOINT", MINIO_ENDPOINT)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_OUT = os.getenv("KAFKA_TOPIC_IN", "file.requested")

DEFAULT_DB_DIR = Path("validation")
KNOWN_LABELS = {"benign", "malicious", "suspicious", "unknown"}


# ---------------------------------------------------------------------------
# Corpus discovery
# ---------------------------------------------------------------------------

def discover_corpus(root: Path) -> list[tuple[Path, str]]:
    """Return [(file_path, label), ...] — label inferred from the first-level sub-folder name."""
    if not root.is_dir():
        raise SystemExit(f"[FATAL] corpus root not found: {root}")

    samples: list[tuple[Path, str]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        label = child.name if child.name in KNOWN_LABELS else "unknown"
        for f in sorted(child.rglob("*")):
            if f.is_file():
                samples.append((f, label))
    return samples


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# MinIO upload — key = sha256 → idempotent by construction
# ---------------------------------------------------------------------------

def make_minio() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def upload_if_absent(client: Minio, sha256: str, path: Path) -> str:
    """Upload the sample if absent from the bucket, return object_name (MinIO key)."""
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    object_name = f"validation/{sha256}"
    try:
        client.stat_object(MINIO_BUCKET, object_name)
        # already uploaded → no-op
    except Exception:
        client.fput_object(MINIO_BUCKET, object_name, str(path))
    return object_name


def presign(object_name: str, expires_h: int = 24) -> str:
    """Presigned URL usable by the sandbox pods (pod-accessible endpoint).

    Note: MINIO_PRESIGN_ENDPOINT may point to a hostname the feeder *cannot*
    resolve (e.g. the K8s DNS `minio.minio.svc.cluster.local` when the feeder
    runs on the host). The MinIO SDK normally calls `_get_region()` when
    presigned_get_object starts — an HTTP HEAD to the bucket → DNS failure on
    the host side. We pass an explicit `region` to skip that call: the presigned
    URL is generated 100% locally (V4 signature), and only the K3s pod will
    consume the URL with a DNS that resolves.
    """
    presign_client = Minio(
        MINIO_PRESIGN_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
        region="us-east-1",
    )
    return presign_client.presigned_get_object(
        MINIO_BUCKET, object_name, expires=timedelta(hours=expires_h)
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def feed(
    corpus_root: Path,
    run_id: str,
    repetitions: int,
    max_inflight: int,
    db_dir: Path,
    rate_per_s: float | None,
    label_source: str = "unspecified",
) -> None:
    samples = discover_corpus(corpus_root)
    if not samples:
        raise SystemExit(f"[FATAL] no file under {corpus_root}")

    # feeder_state.duckdb — exclusive lock for the feeder only.
    # No read of results.duckdb: the validator holds its exclusive lock.
    # The inflight throttle is handled in memory via asyncio.Semaphore.
    conn_f = db.connect_feeder(db_dir)

    minio_client = make_minio()
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)

    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda v: v.encode("utf-8") if v else None,
    )
    await producer.start()

    # In-memory semaphore: limits the number of jobs awaiting a result.
    # Each slot is acquired before sending and released automatically after
    # avg_job_duration_s seconds (estimate). This is a conservative approximation
    # — we do not read results.duckdb to avoid any lock conflict.
    avg_job_duration_s = 60.0
    semaphore = asyncio.Semaphore(max_inflight)

    async def _release_after(delay: float) -> None:
        await asyncio.sleep(delay)
        semaphore.release()

    total_planned = len(samples) * repetitions
    sent_now = 0
    skipped = 0
    min_interval = (1.0 / rate_per_s) if rate_per_s else 0.0
    last_send = 0.0

    print(f"[feeder] run_id={run_id}  corpus={corpus_root}  "
          f"samples={len(samples)} × reps={repetitions} = {total_planned} jobs")
    print(f"[feeder] DB={db_dir}  max_inflight={max_inflight}  rate={rate_per_s or 'unlimited'}/s")

    release_tasks: list[asyncio.Task] = []
    try:
        for path, label in samples:
            sha256 = sha256_of(path)
            size = path.stat().st_size
            db.register_sample(conn_f, sha256, label, str(path), size, label_source)

            for rep in range(repetitions):
                if db.already_sent(conn_f, run_id, sha256, rep):
                    skipped += 1
                    continue

                # Wait for a free slot (inflight throttle)
                await semaphore.acquire()

                # The permit acquired above is handed to the _release_after timer
                # ONLY if the send succeeds. On a transient error
                # (MinIO/presign/Kafka), the `finally` releases it so we don't
                # leak a slot, and we `continue` to the next sample — a feed of
                # several thousand jobs thus survives a network hiccup.
                released = False
                try:
                    # Rate throttle
                    if min_interval:
                        delta = time.monotonic() - last_send
                        if delta < min_interval:
                            await asyncio.sleep(min_interval - delta)

                    job_id = str(uuid.uuid4())
                    object_name = upload_if_absent(minio_client, sha256, path)
                    url = presign(object_name)
                    event = {
                        "job_id": job_id,
                        "s3_url": url,
                        "sha256": sha256,
                        "email_context": {
                            "sender": "validation@corpus.local",
                            "subject": f"[validation] {run_id} rep={rep}",
                            "body_text": f"Automated validation run for {label} sample.",
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                    # Record BEFORE publishing — idempotence guaranteed even on crash.
                    # Tradeoff: if send_and_wait fails below, the job stays marked
                    # "sent" and will be skipped on re-run (already_sent). Acceptable for v1.
                    db.record_sent(conn_f, job_id, run_id, sha256, rep)
                    await producer.send_and_wait(TOPIC_OUT, value=event, key=sha256)
                    last_send = time.monotonic()
                    sent_now += 1

                    # Release the slot after a job's estimated duration
                    t = asyncio.create_task(_release_after(avg_job_duration_s))
                    release_tasks.append(t)
                    released = True  # the permit is now held by the timer

                    if sent_now % 50 == 0 or sent_now == 1:
                        print(f"[feeder] sent {sent_now}  skipped {skipped}  "
                              f"inflight~{max_inflight - semaphore._value}")
                except Exception as exc:
                    print(f"[feeder] error on {path} rep={rep}: {exc} — skip "
                          f"(the job may be marked sent in DB and skipped on re-run)")
                finally:
                    if not released:
                        semaphore.release()

    finally:
        await producer.stop()
        conn_f.close()
        # Cancel the remaining release timers
        for t in release_tasks:
            t.cancel()

    print(f"\n[feeder] done — sent {sent_now}, skipped {skipped} (already present in DB)")
    print(f"[feeder] run the validator in another terminal: make validate-collect")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", required=True, type=Path, help="Corpus root (contains benign/, malicious/, unknown/)")
    p.add_argument("--run-id", required=True, help="Campaign identifier (e.g. 2026-04-29_run1)")
    p.add_argument("--repetitions", type=int, default=1, help="Number of repetitions per file (determinism: 2)")
    p.add_argument("--max-inflight", type=int, default=30, help="Cap on jobs awaiting a result")
    p.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR, help="DB folder (default: validation/)")
    p.add_argument("--rate", type=float, default=None, help="Max throughput msg/s (default: unlimited)")
    p.add_argument("--label-source", default="unspecified",
                   choices=["academic_groundtruth", "av_consensus", "synthetic", "unspecified"],
                   help="Provenance of the labels (anti-circularity M2). 'av_consensus' is "
                        "excluded from the independence figure in the report.")
    args = p.parse_args()

    if args.repetitions < 1:
        sys.exit("--repetitions must be ≥ 1")
    if args.max_inflight < 1:
        sys.exit("--max-inflight must be ≥ 1")

    asyncio.run(feed(
        corpus_root=args.corpus.resolve(),
        run_id=args.run_id,
        repetitions=args.repetitions,
        max_inflight=args.max_inflight,
        db_dir=args.db_dir.resolve(),
        rate_per_s=args.rate,
        label_source=args.label_source,
    ))


if __name__ == "__main__":
    main()
