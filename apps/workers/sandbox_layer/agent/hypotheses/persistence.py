"""Hypothesis 1 — Active persistence (Linux).

Detects: changes in cron, systemd, profile.d, rc.local, init.d,
~/.bashrc, ~/.ssh/authorized_keys, /etc/sudoers.d.

Heuristic (Phase 4 — thresholds tuned in Phase 7):
    score = clamp(
        0.50 * has_persistence_change
      + 0.30 * has_crontab_addition
      + 0.20 * has_systemd_addition
      + 0.30 * created_file_in_persistence_path,
        0.0, 1.0
    )

Pure function, no I/O. Phase 4.
"""

from __future__ import annotations

from models import (
    PERSISTENCE_PATHS,
    MemoryObservables,
    RuntimeSignals,
    SnapshotDiff,
)

from hypotheses._types import Evidence, HypothesisResult

# Glob-like prefixes flagged as persistence locations.
# /tmp userspace paths: writable by UID 10001 (emptyDir + fsGroup=10001).
# Real malware drops loaders, cron-like scripts and .bashrc overrides in /tmp
# when it cannot reach /etc or /home.
_PERSISTENCE_PREFIXES = (
    "/etc/cron",
    "/etc/profile.d",
    "/etc/init.d",
    "/etc/systemd/system",
    "/etc/rc.local",
    "/etc/sudoers.d",
    "/root/.ssh",
    "/root/.bashrc",
    "/root/.profile",
    "/home/",
    "/tmp/.bashrc",
    "/tmp/.profile",
    "/tmp/cron",
    "/tmp/systemd",
    "/tmp/init",
    "/tmp/rc.",
    "/tmp/autorun",
    "/tmp/persist",
    "/tmp/startup",
    "/tmp/payload",
    "/tmp/stage",
    "/tmp/backdoor",
    "/tmp/loader",
)


def _is_persistence_path(path: str) -> bool:
    if path in PERSISTENCE_PATHS:
        return True
    return any(path.startswith(p) for p in _PERSISTENCE_PREFIXES)


def evaluate(
    diff: SnapshotDiff,
    signals: RuntimeSignals,  # noqa: ARG001
    memory: MemoryObservables,  # noqa: ARG001
) -> HypothesisResult:
    evidence: list[Evidence] = []
    score = 0.0

    # Direct persistence changes (sha256 diff on known persistence files)
    if diff.persistence_changes:
        score += 0.50
        for i, p in enumerate(diff.persistence_changes[:3]):
            evidence.append(Evidence(
                source="snapshot_diff",
                field_path=f"persistence_changes[{i}].path",
                value=p.path,
            ))

    # Crontab additions
    if diff.crontab_additions:
        score += 0.30
        evidence.append(Evidence(
            source="snapshot_diff",
            field_path="crontab_additions[0]",
            value=diff.crontab_additions[0][:256],
        ))

    # Systemd new active units
    if diff.systemd_additions:
        score += 0.20
        evidence.append(Evidence(
            source="snapshot_diff",
            field_path="systemd_additions[0]",
            value=diff.systemd_additions[0],
        ))

    # File created in a persistence location
    created_in_persist = [
        d for d in diff.file_diffs
        if d.kind == "created" and _is_persistence_path(d.path)
    ]
    if created_in_persist:
        score += 0.30
        for i, d in enumerate(created_in_persist[:3]):
            evidence.append(Evidence(
                source="snapshot_diff",
                field_path=f"file_diffs[{i}].path",
                value=d.path,
            ))

    score = min(score, 1.0)
    return HypothesisResult(
        value=score >= 0.30,
        score=round(score, 3),
        evidence=evidence,
    )
