"""Hypothesis 4 — File encryption (ransomware).

Detects:
- Many file modifications in a short window (mass rewrite)
- File deletions paired with creations (rename-with-extension pattern)
- Ransom note patterns in created file names
- High write() syscall count

Note: real entropy delta computation requires raw bytes which we don't
collect (privacy + volumetry). Phase 4 uses indirect indicators based
on file_diffs metadata only.

Heuristic:
    score = 0.40 * mass_modify          (>= 10 modifs in <60s)
          + 0.30 * created_eq_deleted   (rename pattern)
          + 0.40 * ransom_note_present
          + 0.20 * high_write_volume    (write syscall count > 1000)
    capped at 1.0.

Pure function. Phase 4.
"""

from __future__ import annotations

from models import (
    MemoryObservables,
    RuntimeSignals,
    SnapshotDiff,
)

from hypotheses._types import Evidence, HypothesisResult

_RANSOM_KEYWORDS = (
    "decrypt", "ransom", "bitcoin", "btc", "readme",
    "how_to_recover", "your_files", "recover_files",
    "_locked", ".locked", ".enc",
)


def evaluate(
    diff: SnapshotDiff,
    signals: RuntimeSignals,
    memory: MemoryObservables,  # noqa: ARG001
) -> HypothesisResult:
    evidence: list[Evidence] = []
    score = 0.0

    duration = max(diff.execution_duration_s, 1.0)
    mass_modify = (
        diff.files_modified_count >= 10
        and diff.files_modified_count / duration > 0.5
    )
    if mass_modify:
        score += 0.40
        evidence.append(Evidence(
            source="snapshot_diff",
            field_path="files_modified_count",
            value=f"{diff.files_modified_count} in {duration:.1f}s",
        ))

    # Rename pattern: comparable created and deleted counts, both significant
    if (
        diff.files_created_count >= 5
        and diff.files_deleted_count >= 5
        and abs(diff.files_created_count - diff.files_deleted_count) <= 3
    ):
        score += 0.30
        evidence.append(Evidence(
            source="snapshot_diff",
            field_path="files_created_count|files_deleted_count",
            value=f"created={diff.files_created_count} deleted={diff.files_deleted_count}",
        ))

    # Ransom note pattern
    for d in diff.file_diffs:
        if d.kind != "created":
            continue
        name = d.path.lower()
        if any(kw in name for kw in _RANSOM_KEYWORDS):
            score += 0.40
            evidence.append(Evidence(
                source="snapshot_diff",
                field_path="file_diffs[?ransom_note].path",
                value=d.path,
            ))
            break

    # High write volume
    write_calls = next(
        (s for s in signals.syscalls_summary if s.name == "write"),
        None,
    )
    if write_calls and write_calls.call_count > 1000:
        score += 0.20
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="syscalls_summary[write].call_count",
            value=str(write_calls.call_count),
        ))

    score = min(score, 1.0)
    return HypothesisResult(
        value=score >= 0.40,
        score=round(score, 3),
        evidence=evidence,
    )
