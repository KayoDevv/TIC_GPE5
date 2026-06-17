"""P0d — the label_source migration must run on a PRE-EXISTING corpus table.

The first cut shipped `ALTER TABLE ... ADD COLUMN ... NOT NULL`, which DuckDB
rejects ("Adding columns with constraints not yet supported"). It slipped
through because fresh-DB tests take the CREATE TABLE path, never the ALTER. This
test reproduces the upgrade: an old corpus table (no label_source) opened by
connect_feeder must migrate cleanly and backfill existing rows.

Requires a real duckdb (skipped if absent).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

duckdb = pytest.importorskip("duckdb")

import db  # noqa: E402

# The pre-label_source schema, verbatim from the original migration baseline.
_OLD_CORPUS = """
CREATE TABLE corpus (
    sha256        VARCHAR PRIMARY KEY,
    label         VARCHAR NOT NULL,
    source_path   VARCHAR NOT NULL,
    file_size     BIGINT  NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def test_migration_backfills_existing_rows(tmp_path):
    # 1. Build an OLD feeder DB with one row and no label_source column.
    old = duckdb.connect(str(tmp_path / db.FEEDER_DB_NAME))
    old.execute(_OLD_CORPUS)
    old.execute("INSERT INTO corpus(sha256, label, source_path, file_size) "
                "VALUES ('abc', 'malicious', '/x', 10)")
    old.close()

    # 2. connect_feeder must run the ALTER without error...
    conn = db.connect_feeder(tmp_path)

    # 3. ...the column exists and the legacy row is backfilled to 'unspecified'.
    val = conn.execute("SELECT label_source FROM corpus WHERE sha256='abc'").fetchone()[0]
    assert val == "unspecified"

    # 4. ...and a fresh insert carrying a provenance works.
    db.register_sample(conn, "def", "benign", "/y", 20, "academic_groundtruth")
    val2 = conn.execute("SELECT label_source FROM corpus WHERE sha256='def'").fetchone()[0]
    assert val2 == "academic_groundtruth"
    conn.close()


def test_connect_is_idempotent(tmp_path):
    # Opening twice (ALTER IF NOT EXISTS on an already-migrated DB) must not raise.
    db.connect_feeder(tmp_path).close()
    db.connect_feeder(tmp_path).close()
