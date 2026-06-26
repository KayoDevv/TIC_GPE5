"""Hypothesis 5 — Evasion attempted.

Detects anti-sandbox / anti-analysis behaviour: early exit with few syscalls,
long cumulated sleep (stalling), ptrace(TRACEME) self-attach, VM/container
fingerprinting, contentless execution (D1 — silence != benign), TracerPid read
(D1bis). Per-tell weights are the named constants below. Pure function.
"""

from __future__ import annotations

from core.scoring import MIN_MEANINGFUL_SYSCALLS

from models import (
    MemoryObservables,
    RuntimeSignals,
    SnapshotDiff,
    SyscallSummary,
)

from hypotheses._types import Evidence, HypothesisResult


def _find_syscall(signals: RuntimeSignals, name: str) -> SyscallSummary | None:
    """The summary for one syscall by name, or None if the sample never called it."""
    return next((s for s in signals.syscalls_summary if s.name == name), None)

_VM_FINGERPRINT_PATHS = (
    "/sys/class/dmi/",
    "/proc/cpuinfo",
    "/proc/scsi/scsi",
    "/proc/ide/",
    "/sys/devices/virtual/dmi/",
)

# Per-tell weights (summed, capped at 1.0); arch_prctl was dropped (environmental).
W_SLEEP_STALL          = 0.40
W_TRACEME              = 0.30
W_VM_FINGERPRINT       = 0.40
W_EARLY_EXIT           = 0.30
W_CONTENTLESS          = 0.80
W_READS_TRACERPID      = 0.50
W_CONTAINER_FINGERPRINT = 0.40

# Decision thresholds.
SLEEP_STALL_THRESHOLD_S = 60.0   # cumulated sleep above this = anti-sandbox stall
EARLY_EXIT_MAX_DURATION_S = 5.0  # "short" run
EARLY_EXIT_MAX_SYSCALLS = 50     # "quiet" run
POSITIVE_THRESHOLD = 0.30        # score at/above which the hypothesis fires


def evaluate(
    diff: SnapshotDiff,
    signals: RuntimeSignals,
    memory: MemoryObservables,  # noqa: ARG001
) -> HypothesisResult:
    evidence: list[Evidence] = []
    score = 0.0

    def flag(weight: float, field_path: str, value: str) -> None:
        """Record one positive tell: add its weight and its evidence (in order)."""
        nonlocal score
        score += weight
        evidence.append(Evidence(
            source="runtime_signals", field_path=field_path, value=value,
        ))

    # Long cumulated sleep — anti-sandbox stall
    if signals.sleep_cumulated_s > SLEEP_STALL_THRESHOLD_S:
        flag(W_SLEEP_STALL, "sleep_cumulated_s", f"{signals.sleep_cumulated_s:.1f}s")

    # Early exit + minimal syscall activity — only suspicious if combined with
    # an explicit fingerprinting attempt (cpuid / dmi / cpuinfo). A short,
    # quiet program is otherwise just a benign tool.
    total_syscalls = sum(s.call_count for s in signals.syscalls_summary)
    early_exit = (
        signals.execution_duration_s < EARLY_EXIT_MAX_DURATION_S
        and total_syscalls < EARLY_EXIT_MAX_SYSCALLS
        and signals.exit_code == 0
    )

    # ptrace(PTRACE_TRACEME, ...) — anti-debug
    ptrace_calls = _find_syscall(signals, "ptrace")
    if ptrace_calls:
        traceme = [a for a in ptrace_calls.sample_args if "TRACEME" in a]
        if traceme:
            flag(W_TRACEME, "syscalls_summary[ptrace].sample_args", traceme[0][:256])

    # VM fingerprinting via openat on DMI/cpuinfo
    openat_calls = _find_syscall(signals, "openat")
    fingerprint_hits: list[str] = []
    if openat_calls:
        fingerprint_hits = [
            a for a in openat_calls.sample_args
            if any(p in a for p in _VM_FINGERPRINT_PATHS)
        ]
        if fingerprint_hits:
            flag(W_VM_FINGERPRINT, "syscalls_summary[openat].sample_args",
                 fingerprint_hits[0][:256])

    # Early exit only counts as evasion when combined with a fingerprinting
    # signal — otherwise every short benign tool would trip the hypothesis.
    if early_exit and fingerprint_hits:
        flag(W_EARLY_EXIT, "execution_duration_s|total_syscalls",
             f"{signals.execution_duration_s:.2f}s/{total_syscalls} syscalls")

    # Contentless execution (D1 — silence != benign): near-zero activity means
    # the sample bailed out instantly, the signature of sandbox detection, and
    # must escalate rather than wash to benign. Weighted so the contribution
    # clears the suspicious threshold through the per-path weight (ELF 0.040).
    if total_syscalls < MIN_MEANINGFUL_SYSCALLS:
        flag(W_CONTENTLESS, "total_syscalls",
             f"contentless execution: {total_syscalls} syscalls in "
             f"{signals.execution_duration_s:.2f}s, exit_code={signals.exit_code}")

    # Anti-analysis probes (D1bis — the probe IS the confession). A benign program
    # does not fingerprint its execution environment; each tell escalates instead
    # of waiting for the bailout to surface as a contentless run. Strong but not
    # auto-malicious: on the PDF path tracerpid clears the suspicious threshold
    # (0.50 * 0.08 = 0.04) and routes to the LLM, never straight to "malicious".
    # NB: arch_prctl(0x3001) was dropped after validation — the benign detonation
    # runtime (Node/PDF.js, recent glibc) issues it under gVisor, so like
    # rseq->ENOSYS it is environmental and cannot discriminate.
    tells = signals.evasion_tells
    if tells.reads_tracerpid:
        flag(W_READS_TRACERPID, "evasion_tells.reads_tracerpid",
             "read /proc/self/status: TracerPid anti-debug check")
    if tells.container_fingerprint:
        flag(W_CONTAINER_FINGERPRINT, "evasion_tells.container_fingerprint",
             "accessed /.dockerenv or /proc/1/cgroup: container detection")

    score = min(score, 1.0)
    return HypothesisResult(
        value=score >= POSITIVE_THRESHOLD,
        score=round(score, 3),
        evidence=evidence,
    )
