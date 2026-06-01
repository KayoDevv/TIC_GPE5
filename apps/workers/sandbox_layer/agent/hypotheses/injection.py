"""Hypothesis 3 — Code injection (Linux).

Detects:
- LD_PRELOAD set on any spawned process (classic library injection)
- RWX memory regions found via /proc/[pid]/maps (Layer 3)
- mprotect() calls switching pages to PROT_EXEC (shellcode unpacking)
- ptrace() calls outside of strace itself (PTRACE_ATTACH on another process)

Heuristic:
    score = 0.50 * has_ld_preload
          + 0.40 * any_rwx_region
          + 0.30 * mprotect_to_exec
          + 0.20 * ptrace_attach_observed
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


def evaluate(
    diff: SnapshotDiff,
    signals: RuntimeSignals,
    memory: MemoryObservables,
) -> HypothesisResult:
    evidence: list[Evidence] = []
    score = 0.0

    # LD_PRELOAD on any spawned process
    preload_procs = [p for p in diff.processes_spawned if p.ld_preload]
    if preload_procs:
        score += 0.50
        p = preload_procs[0]
        evidence.append(Evidence(
            source="snapshot_diff",
            field_path=f"processes_spawned[?ld_preload][pid={p.pid}]",
            value=p.ld_preload[:256],
        ))

    # RWX regions from /proc/[pid]/maps (Layer 3)
    rwx_regions = [r for r in memory.suspicious_regions if "rwx" in r.permissions]
    if rwx_regions:
        score += 0.40
        r = rwx_regions[0]
        evidence.append(Evidence(
            source="memory",
            field_path=f"suspicious_regions[pid={r.pid}].permissions",
            value=f"{r.start_addr}-{r.end_addr} {r.permissions}",
        ))

    # mprotect with PROT_EXEC (very common in shellcode unpacking)
    mprotect = next(
        (s for s in signals.syscalls_summary if s.name == "mprotect"),
        None,
    )
    if mprotect:
        # Look for PROT_EXEC in sample args (strace formats it)
        exec_args = [a for a in mprotect.sample_args if "PROT_EXEC" in a]
        if exec_args:
            score += 0.30
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="syscalls_summary[mprotect].sample_args",
                value=exec_args[0][:256],
            ))

    # ptrace observed (other than strace's own attach — heuristic: > 2 calls)
    ptrace_calls = next(
        (s for s in signals.syscalls_summary if s.name == "ptrace"),
        None,
    )
    if ptrace_calls and ptrace_calls.call_count > 2:
        score += 0.20
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="syscalls_summary[ptrace].call_count",
            value=str(ptrace_calls.call_count),
        ))

    score = min(score, 1.0)
    return HypothesisResult(
        value=score >= 0.30,
        score=round(score, 3),
        evidence=evidence,
    )
