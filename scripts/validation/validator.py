"""Validator — dedicated Kafka consumer that materializes sandbox_layer.result into results.duckdb.

Opens feeder_state.duckdb read-only, and only after the feeder has finished
(no more exclusive lock). Each process has its own DuckDB file.

Stop modes (by priority):
  - --run-id <id>    : stops as soon as matched = total sent by the feeder
                       (matched counts each persisted result, errors included —
                       errors is a subset of matched, not a term to add)
  - --until-drained  : stops after --idle-timeout seconds without a new result
  - Ctrl-C           : immediate stop (Kafka offset committed → clean resume)

Usage:
    python -m scripts.validation.validator
    python -m scripts.validation.validator --run-id pilot5
    python -m scripts.validation.validator --until-drained --idle-timeout 120
    python -m scripts.validation.validator --run-id pilot5 --idle-timeout 120
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import time
from pathlib import Path

from aiokafka import AIOKafkaConsumer

from . import db

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_IN  = os.getenv("KAFKA_TOPIC_OUT", "sandbox_layer.result")
GROUP_ID  = os.getenv("VALIDATOR_GROUP_ID", "charon-validation-collector")

DEFAULT_DB_DIR       = Path("validation")
DEFAULT_IDLE_TIMEOUT = 120   # seconds without a result → considered drained

_ANOMALY_RE = re.compile(r"anomaly_score\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def parse_anomaly_score(behavior_summary: str) -> float | None:
    if not behavior_summary:
        return None
    m = _ANOMALY_RE.search(behavior_summary)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------

async def collect(
    db_dir: Path,
    run_id: str | None,
    until_drained: bool,
    idle_timeout_s: int,
    poll_ms: int = 5000,
) -> None:
    # results.duckdb — exclusive lock for this process only
    conn_r = db.connect_results(db_dir)

    # Number of expected results — read from feeder_state.duckdb (read-only;
    # the feeder is finished by this point so no more exclusive lock).
    expected: int | None = None
    if run_id:
        expected = db.sent_count_readonly(db_dir, run_id)
        if expected == 0:
            print(f"[validator] WARNING: no job found for run_id={run_id} in feeder_state.duckdb")
            expected = None
        else:
            print(f"[validator] run_id={run_id}  expected={expected} results")

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    await consumer.start()

    stop = asyncio.Event()

    def _on_signal() -> None:
        print("\n[validator] stop requested (Ctrl-C).")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            pass  # Windows

    matched = 0
    unknown = 0
    errors  = 0
    last_match_ts = time.monotonic()

    # Set of job_ids expected for this run — used to reject messages from other
    # runs that may linger in the Kafka topic.
    expected_job_ids: set[str] = set()
    if run_id:
        expected_job_ids = db.sent_job_ids_readonly(db_dir, run_id)

    if expected:
        mode = f"run_id={run_id} ({expected} expected)"
    elif until_drained:
        mode = f"idle-timeout={idle_timeout_s}s"
    else:
        mode = "continuous (Ctrl-C)"

    print(f"[validator] topic={TOPIC_IN}  group={GROUP_ID}  mode={mode}")
    print(f"[validator] DB → {db_dir / db.RESULTS_DB_NAME}")

    try:
        while not stop.is_set():
            batch = await consumer.getmany(timeout_ms=poll_ms, max_records=100)

            new_this_poll = 0
            for _tp, msgs in batch.items():
                for msg in msgs:
                    payload = msg.value
                    job_id  = payload.get("job_id")
                    if not job_id:
                        continue

                    # Reject messages that do not belong to this run
                    if expected_job_ids and job_id not in expected_job_ids:
                        unknown += 1
                        continue

                    # Score + error: read the STRUCTURED _meta fields first
                    # (robust), with a regex fallback on the text for older
                    # messages that exposed "anomaly_score=X" in plain text.
                    meta = payload.get("_meta") or {}
                    score = meta.get("anomaly_score")
                    if score is None:
                        score = parse_anomaly_score(payload.get("behavior_summary", ""))
                    err = meta.get("error") or payload.get("error")
                    is_error = bool(err)
                    ok = db.record_result(
                        conn_r,
                        job_id=job_id,
                        anomaly_score=score,
                        ioc_count=len(payload.get("iocs") or []),
                        timeout_triggered=bool(payload.get("timeout_triggered")),
                        behavior_summary=payload.get("behavior_summary", ""),
                        raw_result_json=json.dumps(payload, ensure_ascii=False),
                        error=err,
                    )
                    if ok:
                        matched += 1
                        new_this_poll += 1
                        if is_error:
                            errors += 1
                    else:
                        unknown += 1

            if new_this_poll:
                last_match_ts = time.monotonic()
                received = matched
                suffix = f"  errors={errors}" if errors else ""
                if expected:
                    pct = 100 * received / expected
                    print(f"[validator] +{new_this_poll} results  "
                          f"total={received}/{expected} ({pct:.0f}%){suffix}")
                else:
                    print(f"[validator] +{new_this_poll} results  "
                          f"total matched={received}  unknown={unknown}{suffix}")

            # Stop once all expected results are received
            if expected and matched >= expected:
                print(f"[validator] ✓ all results received ({matched}/{expected}) — stopping.")
                break

            # Stop on idle-timeout (fallback if run_id not provided)
            if until_drained or expected:
                idle_s = time.monotonic() - last_match_ts
                remaining = idle_timeout_s - int(idle_s)
                if idle_s >= idle_timeout_s:
                    print(f"[validator] idle for {int(idle_s)}s ≥ {idle_timeout_s}s — fully drained.")
                    break
                elif not new_this_poll:
                    if expected:
                        print(f"[validator] waiting… {matched}/{expected}  "
                              f"idle={int(idle_s)}s  timeout in {remaining}s")
                    else:
                        print(f"[validator] waiting… idle={int(idle_s)}s  "
                              f"timeout in {remaining}s  matched={matched}")

    finally:
        await consumer.stop()
        conn_r.close()

    print(f"\n[validator] done — matched={matched}  errors={errors}  unknown={unknown}")
    if matched > 0:
        print(f"[validator] run the report: make validate-report")


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR,
                   help="DB folder (default: validation/)")
    p.add_argument("--run-id", default=None,
                   help="Stops as soon as all jobs of the run are received")
    p.add_argument("--until-drained", action="store_true",
                   help="Stops after --idle-timeout seconds without a new result")
    p.add_argument("--idle-timeout", type=int, default=DEFAULT_IDLE_TIMEOUT,
                   help=f"Seconds of inactivity before stopping (default: {DEFAULT_IDLE_TIMEOUT})")
    args = p.parse_args()

    asyncio.run(collect(
        db_dir=args.db_dir.resolve(),
        run_id=args.run_id,
        until_drained=args.until_drained,
        idle_timeout_s=args.idle_timeout,
    ))


if __name__ == "__main__":
    main()
