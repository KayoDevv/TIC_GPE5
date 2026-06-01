"""DuckDB schema + helpers for the validation pipeline.

Two separate DB files to avoid the DuckDB lock conflict (1 writer per file):
  - feeder_state.duckdb  → send state (corpus + sent jobs)   written by feeder only
  - results.duckdb       → results received from Kafka        written by validator only
  - report.py opens both read-only and joins them in memory

All writes are idempotent (INSERT OR IGNORE on natural keys).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import duckdb

_WRITE_LOCK = threading.Lock()

# Default file names (inside the validation/ directory)
FEEDER_DB_NAME   = "feeder_state.duckdb"
RESULTS_DB_NAME  = "results.duckdb"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_FEEDER_SCHEMA = """
-- Catalog of the corpus files, deduplicated by sha256.
-- label: 'benign' | 'malicious' | 'unknown' — inferred from the source folder.
CREATE TABLE IF NOT EXISTS corpus (
    sha256        VARCHAR PRIMARY KEY,
    label         VARCHAR NOT NULL,
    source_path   VARCHAR NOT NULL,
    file_size     BIGINT  NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- One job per (run_id, sha256, repetition_idx).
-- job_id = Kafka UUID published on file.requested.
CREATE TABLE IF NOT EXISTS sent_jobs (
    job_id         VARCHAR PRIMARY KEY,
    run_id         VARCHAR NOT NULL,
    sha256         VARCHAR NOT NULL,
    repetition_idx INTEGER NOT NULL,
    sent_ts        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, sha256, repetition_idx)
);

CREATE INDEX IF NOT EXISTS idx_sent_run  ON sent_jobs(run_id);
CREATE INDEX IF NOT EXISTS idx_sent_sha  ON sent_jobs(sha256);
"""

_RESULTS_SCHEMA = """
-- Results received from sandbox_layer.result.
-- job_id = join key with feeder_state.sent_jobs.
CREATE TABLE IF NOT EXISTS results (
    job_id            VARCHAR PRIMARY KEY,
    received_ts       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    anomaly_score     DOUBLE,
    ioc_count         INTEGER,
    timeout_triggered BOOLEAN,
    behavior_summary  VARCHAR,
    raw_result_json   VARCHAR,
    error             VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_res_received ON results(received_ts);
"""


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

def connect_feeder(db_dir: Path) -> duckdb.DuckDBPyConnection:
    """Open (or create) feeder_state.duckdb for writing."""
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_dir / FEEDER_DB_NAME))
    conn.execute(_FEEDER_SCHEMA)
    return conn


def connect_results(db_dir: Path) -> duckdb.DuckDBPyConnection:
    """Open (or create) results.duckdb for writing."""
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_dir / RESULTS_DB_NAME))
    conn.execute(_RESULTS_SCHEMA)
    return conn


def connect_readonly(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open an existing DB read-only (no exclusive lock)."""
    return duckdb.connect(str(db_path), read_only=True)


# ---------------------------------------------------------------------------
# Feeder helpers
# ---------------------------------------------------------------------------

def register_sample(
    conn: duckdb.DuckDBPyConnection,
    sha256: str,
    label: str,
    source_path: str,
    file_size: int,
) -> None:
    """Register a file in corpus if absent (idempotent)."""
    with _WRITE_LOCK:
        conn.execute(
            "INSERT OR IGNORE INTO corpus(sha256, label, source_path, file_size) "
            "VALUES (?, ?, ?, ?)",
            [sha256, label, source_path, file_size],
        )


def already_sent(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    sha256: str,
    repetition_idx: int,
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sent_jobs WHERE run_id=? AND sha256=? AND repetition_idx=?",
        [run_id, sha256, repetition_idx],
    ).fetchone()
    return row is not None


def record_sent(
    conn: duckdb.DuckDBPyConnection,
    job_id: str,
    run_id: str,
    sha256: str,
    repetition_idx: int,
) -> None:
    """Insert the job BEFORE the Kafka publish — guarantees idempotence on crash."""
    with _WRITE_LOCK:
        conn.execute(
            "INSERT OR IGNORE INTO sent_jobs(job_id, run_id, sha256, repetition_idx) "
            "VALUES (?, ?, ?, ?)",
            [job_id, run_id, sha256, repetition_idx],
        )


def sent_count(conn_feeder: duckdb.DuckDBPyConnection, run_id: str) -> int:
    """Number of jobs sent for a run (from feeder_state only)."""
    row = conn_feeder.execute(
        "SELECT COUNT(*) FROM sent_jobs WHERE run_id=?", [run_id]
    ).fetchone()
    return int(row[0]) if row else 0


def sent_count_readonly(db_dir: Path, run_id: str) -> int:
    """Read the number of jobs sent for a run without a lock (feeder finished)."""
    feeder_path = db_dir / FEEDER_DB_NAME
    if not feeder_path.exists():
        return 0
    conn = connect_readonly(feeder_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sent_jobs WHERE run_id=?", [run_id]
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def sent_job_ids_readonly(db_dir: Path, run_id: str) -> set[str]:
    """Return the set of expected job_ids for a run (read-only).

    Used by the validator to reject Kafka messages from other runs that linger
    in the topic and would otherwise cause false matches.
    """
    feeder_path = db_dir / FEEDER_DB_NAME
    if not feeder_path.exists():
        return set()
    conn = connect_readonly(feeder_path)
    try:
        rows = conn.execute(
            "SELECT job_id FROM sent_jobs WHERE run_id=?", [run_id]
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Validator helpers
# ---------------------------------------------------------------------------

def record_result(
    conn: duckdb.DuckDBPyConnection,
    job_id: str,
    anomaly_score: float | None,
    ioc_count: int,
    timeout_triggered: bool,
    behavior_summary: str,
    raw_result_json: str,
    error: str | None = None,
) -> bool:
    """Insert the result if absent (idempotent).

    Returns True ONLY if a new row was inserted, False if the job_id already
    existed. NB: we test for existence BEFORE the insert rather than re-reading
    received_ts afterwards — otherwise a pre-existing row (Kafka replay,
    auto_offset_reset=earliest) would wrongly return True and inflate `matched`
    on the validator side, causing collection to stop prematurely.

    The SELECT then the INSERT are serialized by _WRITE_LOCK (1 writer/file),
    so there is no race between them.
    """
    with _WRITE_LOCK:
        exists = conn.execute(
            "SELECT 1 FROM results WHERE job_id=?", [job_id]
        ).fetchone() is not None
        if exists:
            return False
        conn.execute(
            "INSERT OR IGNORE INTO results("
            "  job_id, anomaly_score, ioc_count, timeout_triggered,"
            "  behavior_summary, raw_result_json, error"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            [job_id, anomaly_score, ioc_count, timeout_triggered,
             behavior_summary, raw_result_json, error],
        )
        return True


# ---------------------------------------------------------------------------
# Reporting helpers — open both DBs read-only and join in memory
# ---------------------------------------------------------------------------

def fetch_run_results(
    db_dir: Path,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Join feeder_state + results. Return the received results with their label."""
    feeder_path  = db_dir / FEEDER_DB_NAME
    results_path = db_dir / RESULTS_DB_NAME

    if not feeder_path.exists():
        raise SystemExit(f"feeder_state.duckdb not found in {db_dir}. Run the feeder first.")
    if not results_path.exists():
        raise SystemExit(f"results.duckdb not found in {db_dir}. Run the validator first.")

    cf = connect_readonly(feeder_path)
    cr = connect_readonly(results_path)

    # Load into memory then join (the two DBs live in separate files)
    sent_rows = cf.execute(
        "SELECT job_id, run_id, sha256, repetition_idx FROM sent_jobs"
        + (" WHERE run_id=?" if run_id else ""),
        [run_id] if run_id else [],
    ).fetchall()

    corpus_map: dict[str, tuple[str, str]] = {}  # sha256 -> (label, source_path)
    for sha, label, src, _ in cf.execute(
        "SELECT sha256, label, source_path, file_size FROM corpus"
    ).fetchall():
        corpus_map[sha] = (label, src)

    if not sent_rows:
        return []

    job_ids = [r[0] for r in sent_rows]
    placeholders = ",".join("?" * len(job_ids))
    res_map: dict[str, tuple] = {
        r[0]: r for r in cr.execute(
            f"SELECT job_id, anomaly_score, ioc_count, timeout_triggered, error "
            f"FROM results WHERE job_id IN ({placeholders})",
            job_ids,
        ).fetchall()
    }

    cf.close()
    cr.close()

    out = []
    for job_id, run_id_, sha256, rep_idx in sent_rows:
        res = res_map.get(job_id)
        if res is None:
            continue  # not received yet
        label, _ = corpus_map.get(sha256, ("unknown", ""))
        out.append({
            "job_id":            job_id,
            "run_id":            run_id_,
            "sha256":            sha256,
            "repetition_idx":    rep_idx,
            "anomaly_score":     res[1],
            "ioc_count":         res[2],
            "timeout_triggered": res[3],
            "error":             res[4],
            "label":             label,
        })
    return out


def list_run_ids(db_dir: Path) -> list[str]:
    feeder_path = db_dir / FEEDER_DB_NAME
    if not feeder_path.exists():
        return []
    conn = connect_readonly(feeder_path)
    rows = conn.execute("SELECT DISTINCT run_id FROM sent_jobs ORDER BY run_id").fetchall()
    conn.close()
    return [r[0] for r in rows]


def inflight_total(db_dir: Path) -> int:
    """Number of jobs sent without a received result (across all runs)."""
    feeder_path  = db_dir / FEEDER_DB_NAME
    results_path = db_dir / RESULTS_DB_NAME
    if not feeder_path.exists() or not results_path.exists():
        return 0
    cf = connect_readonly(feeder_path)
    cr = connect_readonly(results_path)
    total_sent     = cf.execute("SELECT COUNT(*) FROM sent_jobs").fetchone()[0]
    total_received = cr.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    cf.close()
    cr.close()
    return max(0, int(total_sent) - int(total_received))
