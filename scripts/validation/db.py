"""Schéma DuckDB + helpers pour le pipeline de validation.

Deux fichiers DB séparés pour éviter le conflit de lock DuckDB (1 writer par fichier) :
  - feeder_state.duckdb  → état d'envoi (corpus + jobs envoyés)   écrit par feeder seul
  - results.duckdb       → résultats reçus depuis Kafka           écrit par validator seul
  - report.py charge les deux en lecture et les joint en mémoire

Toutes les écritures sont idempotentes (INSERT OR IGNORE sur clés naturelles).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import duckdb

_WRITE_LOCK = threading.Lock()

# Noms de fichiers par défaut (dans le dossier validation/)
FEEDER_DB_NAME   = "feeder_state.duckdb"
RESULTS_DB_NAME  = "results.duckdb"


# ---------------------------------------------------------------------------
# Schémas
# ---------------------------------------------------------------------------

_FEEDER_SCHEMA = """
-- Catalogue des fichiers du corpus, dédupliqué par sha256.
-- label : 'benign' | 'malicious' | 'unknown' — déduit du dossier source.
CREATE TABLE IF NOT EXISTS corpus (
    sha256        VARCHAR PRIMARY KEY,
    label         VARCHAR NOT NULL,
    source_path   VARCHAR NOT NULL,
    file_size     BIGINT  NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Un job par (run_id, sha256, repetition_idx).
-- job_id = UUID Kafka publié sur file.requested.
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
-- Résultats reçus depuis sandbox_layer.result.
-- job_id = clé de jointure avec feeder_state.sent_jobs.
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
# Connexions
# ---------------------------------------------------------------------------

def connect_feeder(db_dir: Path) -> duckdb.DuckDBPyConnection:
    """Ouvre (ou crée) feeder_state.duckdb en écriture."""
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_dir / FEEDER_DB_NAME))
    conn.execute(_FEEDER_SCHEMA)
    return conn


def connect_results(db_dir: Path) -> duckdb.DuckDBPyConnection:
    """Ouvre (ou crée) results.duckdb en écriture."""
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_dir / RESULTS_DB_NAME))
    conn.execute(_RESULTS_SCHEMA)
    return conn


def connect_readonly(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Ouvre une DB existante en lecture seule (pas de lock exclusif)."""
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
    """Enregistre un fichier dans corpus si absent (idempotent)."""
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
    """Insère le job AVANT publication Kafka — garantit l'idempotence en cas de crash."""
    with _WRITE_LOCK:
        conn.execute(
            "INSERT OR IGNORE INTO sent_jobs(job_id, run_id, sha256, repetition_idx) "
            "VALUES (?, ?, ?, ?)",
            [job_id, run_id, sha256, repetition_idx],
        )


def sent_count(conn_feeder: duckdb.DuckDBPyConnection, run_id: str) -> int:
    """Nombre de jobs envoyés pour un run (depuis feeder_state uniquement)."""
    row = conn_feeder.execute(
        "SELECT COUNT(*) FROM sent_jobs WHERE run_id=?", [run_id]
    ).fetchone()
    return int(row[0]) if row else 0


def sent_count_readonly(db_dir: Path, run_id: str) -> int:
    """Lit le nombre de jobs envoyés pour un run sans lock (feeder terminé)."""
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
    """Retourne l'ensemble des job_ids attendus pour un run (lecture seule).

    Utilisé par le validator pour rejeter les messages Kafka d'autres runs
    qui traîneraient dans le topic et provoqueraient des faux matched.
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
    """Insère le résultat si absent (idempotent).

    Retourne True UNIQUEMENT si une nouvelle ligne a été insérée, False si le
    job_id existait déjà. NB : on teste l'existence AVANT l'insert plutôt que de
    relire received_ts après — sinon une ligne pré-existante (replay Kafka,
    auto_offset_reset=earliest) renverrait True à tort et gonflerait `matched`
    côté validator, provoquant un arrêt prématuré de la collecte.

    Le SELECT puis l'INSERT sont sérialisés par _WRITE_LOCK (1 writer/fichier),
    donc pas de race entre les deux.
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
# Reporting helpers — lit les deux DB en read-only et joint en mémoire
# ---------------------------------------------------------------------------

def fetch_run_results(
    db_dir: Path,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Joint feeder_state + results. Retourne les résultats reçus avec leur label."""
    feeder_path  = db_dir / FEEDER_DB_NAME
    results_path = db_dir / RESULTS_DB_NAME

    if not feeder_path.exists():
        raise SystemExit(f"feeder_state.duckdb introuvable dans {db_dir}. Lance d'abord le feeder.")
    if not results_path.exists():
        raise SystemExit(f"results.duckdb introuvable dans {db_dir}. Lance d'abord le validator.")

    cf = connect_readonly(feeder_path)
    cr = connect_readonly(results_path)

    # Charger en mémoire puis joindre (les deux DB sont dans des fichiers séparés)
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
            continue  # pas encore reçu
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
    """Nombre de jobs envoyés sans résultat reçu (tous runs confondus)."""
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
