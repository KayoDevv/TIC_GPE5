"""Hypothesis 5 — Evasion attempted.

Detects anti-sandbox / anti-analysis behavior:
- Early exit (< 5 s) with very few syscalls (probable sandbox detection)
- Long cumulated sleep (> 60 s) — common stalling tactic
- ptrace(PTRACE_TRACEME, ...) — anti-debug self-attach
- uname/sysinfo + read on /sys/class/dmi/* (VM fingerprinting)
- Total absence of meaningful syscall activity

Heuristic:
    score = 0.40 * sleep_cumulated > 60s
          + 0.30 * early_exit_low_syscalls
          + 0.30 * traceme_observed
          + 0.20 * vm_fingerprinting_files
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

_VM_FINGERPRINT_PATHS = (
    "/sys/class/dmi/",
    "/proc/cpuinfo",
    "/proc/scsi/scsi",
    "/proc/ide/",
    "/sys/devices/virtual/dmi/",
)


def evaluate(
    diff: SnapshotDiff,
    signals: RuntimeSignals,
    memory: MemoryObservables,  # noqa: ARG001
) -> HypothesisResult:
    evidence: list[Evidence] = []
    score = 0.0

    # Long cumulated sleep — anti-sandbox stall
    if signals.sleep_cumulated_s > 60.0:
        score += 0.40
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="sleep_cumulated_s",
            value=f"{signals.sleep_cumulated_s:.1f}s",
        ))

    # Early exit + minimal syscall activity — only suspicious if combined with
    # an explicit fingerprinting attempt (cpuid / dmi / cpuinfo). A short,
    # quiet program is otherwise just a benign tool.
    total_syscalls = sum(s.call_count for s in signals.syscalls_summary)
    early_exit = (
        signals.execution_duration_s < 5.0
        and total_syscalls < 50
        and signals.exit_code == 0
    )

    # ptrace(PTRACE_TRACEME, ...) — anti-debug
    ptrace_calls = next(
        (s for s in signals.syscalls_summary if s.name == "ptrace"),
        None,
    )
    if ptrace_calls:
        traceme = [a for a in ptrace_calls.sample_args if "TRACEME" in a]
        if traceme:
            score += 0.30
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="syscalls_summary[ptrace].sample_args",
                value=traceme[0][:256],
            ))

    # VM fingerprinting via openat on DMI/cpuinfo
    openat_calls = next(
        (s for s in signals.syscalls_summary if s.name == "openat"),
        None,
    )
    fingerprint_hits: list[str] = []
    if openat_calls:
        fingerprint_hits = [
            a for a in openat_calls.sample_args
            if any(p in a for p in _VM_FINGERPRINT_PATHS)
        ]
        if fingerprint_hits:
            score += 0.40
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="syscalls_summary[openat].sample_args",
                value=fingerprint_hits[0][:256],
            ))

    # Early exit only counts as evasion when combined with a fingerprinting
    # signal — otherwise every short benign tool would trip the hypothesis.
    if early_exit and fingerprint_hits:
        score += 0.30
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="execution_duration_s|total_syscalls",
            value=f"{signals.execution_duration_s:.2f}s/{total_syscalls} syscalls",
        ))

    score = min(score, 1.0)
    return HypothesisResult(
        value=score >= 0.30,
        score=round(score, 3),
        evidence=evidence,
    )
