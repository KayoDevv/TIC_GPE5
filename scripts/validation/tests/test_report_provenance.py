"""P0d / M2 — the accuracy headline must exclude circular (av_consensus) labels.

A figure scored against the same AV the sandbox imitates is circular. These
samples must not enter the headline matrix; they are reported separately.

Runnable on a plain host: duckdb is stubbed so report.py (which imports db,
which imports duckdb) loads without the native dependency.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

# Stub the native dep before importing the package (db.py does `import duckdb`).
sys.modules.setdefault("duckdb", types.ModuleType("duckdb"))
# report.py uses `from . import db`, so import it as a package member.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.validation import report  # noqa: E402


def _row(sha, label, score, source):
    return {"run_id": "r", "sha256": sha, "label": label, "anomaly_score": score,
            "timeout_triggered": False, "error": None, "label_source": source}


def test_av_consensus_miss_excluded_from_headline():
    rows = [
        # independent ground truth: 2 malicious detected, 1 missed
        _row("ind1", "malicious", 0.50, "academic_groundtruth"),
        _row("ind2", "malicious", 0.50, "academic_groundtruth"),
        _row("indmiss", "malicious", 0.00, "academic_groundtruth"),
        # circular: a missed malicious that must NOT inflate the headline N
        _row("avmiss", "malicious", 0.00, "av_consensus"),
    ]
    md = report.section_justness(rows, 0.04, 0.15)
    # headline malicious N is 3 (independent only), not 4
    assert "(N=3)" in md, md
    # the M2 exclusion note is present, citing 1 excluded sample
    assert "Label independence (M2)" in md
    assert "1 sample" in md


def test_all_av_consensus_skips_section_with_note():
    rows = [_row("a", "malicious", 0.0, "av_consensus"),
            _row("b", "benign", 0.0, "av_consensus")]
    md = report.section_justness(rows, 0.04, 0.15)
    assert "section skipped" in md
    assert "av_consensus" in md


def test_unspecified_legacy_labels_still_counted():
    # Back-compat: rows without an explicit source default to 'unspecified' and
    # remain in the headline (existing runs keep working).
    rows = [_row("m", "malicious", 0.50, "unspecified"),
            _row("b", "benign", 0.00, "unspecified")]
    md = report.section_justness(rows, 0.04, 0.15)
    assert "(N=1)" in md  # 1 malicious, 1 benign each counted
    assert "Label independence (M2)" not in md  # no exclusion note when none excluded
