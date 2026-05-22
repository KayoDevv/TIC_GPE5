"""Feeder corpus — itère un dossier, upload MinIO, publie sur file.requested.

Idempotent : le feeder écrit son état dans validation/feeder_state.duckdb
(corpus + jobs envoyés). Les résultats reçus vont dans validation/results.duckdb,
écrit par le validator (cf. db.py — DB splittées pour éviter le conflit de lock).
  - Re-run avec même --run-id → skip ce qui est déjà envoyé.
  - --repetitions N → envoie chaque fichier N fois (test déterminisme).
  - --max-inflight N → throttle pour ne pas saturer KEDA/queue.

Layout corpus attendu :
    <corpus_root>/
      benign/       → label = benign
      malicious/    → label = malicious
      unknown/      → label = unknown    (ou tout autre nom de dossier non listé)

Usage :
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
# Config (env vars, défauts docker-compose)
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
    """Retourne [(file_path, label), ...] — label déduit du nom du sous-dossier de 1er niveau."""
    if not root.is_dir():
        raise SystemExit(f"[FATAL] corpus root introuvable : {root}")

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
# MinIO upload — clé = sha256 → idempotent par construction
# ---------------------------------------------------------------------------

def make_minio() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def upload_if_absent(client: Minio, sha256: str, path: Path) -> str:
    """Upload sample si absent du bucket, retourne object_name (clé MinIO)."""
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    object_name = f"validation/{sha256}"
    try:
        client.stat_object(MINIO_BUCKET, object_name)
        # déjà uploadé → no-op
    except Exception:
        client.fput_object(MINIO_BUCKET, object_name, str(path))
    return object_name


def presign(object_name: str, expires_h: int = 24) -> str:
    """Presigned URL utilisable par les pods sandbox (endpoint pod-accessible).

    Note : MINIO_PRESIGN_ENDPOINT peut pointer sur un hostname que le feeder
    *ne peut pas* résoudre (ex : DNS K8s `minio.minio.svc.cluster.local` quand
    le feeder tourne sur le host). Le SDK MinIO appelle normalement
    `_get_region()` au démarrage de presigned_get_object — un HEAD HTTP vers
    le bucket → DNS failure côté host. On passe `region` explicite pour
    skip ce call : la presigned URL est générée 100 % localement (signature V4),
    et seul le pod K3s consommera l'URL avec un DNS qui résout.
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
# Boucle principale
# ---------------------------------------------------------------------------

async def feed(
    corpus_root: Path,
    run_id: str,
    repetitions: int,
    max_inflight: int,
    db_dir: Path,
    rate_per_s: float | None,
) -> None:
    samples = discover_corpus(corpus_root)
    if not samples:
        raise SystemExit(f"[FATAL] aucun fichier sous {corpus_root}")

    # feeder_state.duckdb — lock exclusif pour le feeder uniquement.
    # Pas de lecture de results.duckdb : le validator en a le lock exclusif.
    # Le throttle inflight est géré en mémoire via asyncio.Semaphore.
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

    # Semaphore en mémoire : limite le nombre de jobs en attente de résultat.
    # Chaque slot est acquis avant l'envoi et libéré automatiquement après
    # avg_job_duration_s secondes (estimation). C'est une approximation conservative
    # — on ne lit pas results.duckdb pour éviter tout conflit de lock.
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
    print(f"[feeder] DB={db_dir}  max_inflight={max_inflight}  rate={rate_per_s or 'illimité'}/s")

    release_tasks: list[asyncio.Task] = []
    try:
        for path, label in samples:
            sha256 = sha256_of(path)
            size = path.stat().st_size
            db.register_sample(conn_f, sha256, label, str(path), size)

            for rep in range(repetitions):
                if db.already_sent(conn_f, run_id, sha256, rep):
                    skipped += 1
                    continue

                # Attend un slot libre (throttle inflight)
                await semaphore.acquire()

                # Le permit acquis ci-dessus est cédé au timer _release_after
                # UNIQUEMENT si l'envoi réussit. En cas d'erreur transitoire
                # (MinIO/presign/Kafka), le `finally` le relâche pour ne pas
                # fuiter de slot, et on `continue` au sample suivant — un feed
                # de plusieurs milliers de jobs survit ainsi à un hoquet réseau.
                released = False
                try:
                    # Throttle débit
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

                    # Enregistre AVANT publication — idempotence garantie même si crash.
                    # Tradeoff : si send_and_wait échoue ci-dessous, le job reste marqué
                    # « sent » et sera skippé au re-run (already_sent). Acceptable pour v1.
                    db.record_sent(conn_f, job_id, run_id, sha256, rep)
                    await producer.send_and_wait(TOPIC_OUT, value=event, key=sha256)
                    last_send = time.monotonic()
                    sent_now += 1

                    # Libère le slot après la durée estimée d'un job
                    t = asyncio.create_task(_release_after(avg_job_duration_s))
                    release_tasks.append(t)
                    released = True  # le permit est désormais détenu par le timer

                    if sent_now % 50 == 0 or sent_now == 1:
                        print(f"[feeder] envoyé {sent_now}  skipped {skipped}  "
                              f"inflight~{max_inflight - semaphore._value}")
                except Exception as exc:
                    print(f"[feeder] erreur sur {path} rep={rep} : {exc} — skip "
                          f"(le job peut être marqué sent en DB et skippé au re-run)")
                finally:
                    if not released:
                        semaphore.release()

    finally:
        await producer.stop()
        conn_f.close()
        # Annuler les timers de release restants
        for t in release_tasks:
            t.cancel()

    print(f"\n[feeder] terminé — envoyé {sent_now}, skipped {skipped} (déjà présents en DB)")
    print(f"[feeder] lance le validator dans un autre terminal : make validate-collect")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", required=True, type=Path, help="Racine du corpus (contient benign/, malicious/, unknown/)")
    p.add_argument("--run-id", required=True, help="Identifiant de campagne (ex: 2026-04-29_run1)")
    p.add_argument("--repetitions", type=int, default=1, help="Nombre de répétitions par fichier (déterminisme: 2)")
    p.add_argument("--max-inflight", type=int, default=30, help="Plafond de jobs en attente de résultat")
    p.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR, help="Dossier DB (défaut: validation/)")
    p.add_argument("--rate", type=float, default=None, help="Débit max msg/s (défaut: illimité)")
    args = p.parse_args()

    if args.repetitions < 1:
        sys.exit("--repetitions doit être ≥ 1")
    if args.max_inflight < 1:
        sys.exit("--max-inflight doit être ≥ 1")

    asyncio.run(feed(
        corpus_root=args.corpus.resolve(),
        run_id=args.run_id,
        repetitions=args.repetitions,
        max_inflight=args.max_inflight,
        db_dir=args.db_dir.resolve(),
        rate_per_s=args.rate,
    ))


if __name__ == "__main__":
    main()
