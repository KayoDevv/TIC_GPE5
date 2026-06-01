"""Intermediate data models — the sandbox pipeline's central contract.

This package is the **source of truth** for all the types exchanged between:
    - the linux_docker backend (collection)
    - the behavioural hypotheses (Layer 2)
    - the /proc memory forensics runner (Layer 3)
    - the report builder (Layer 4)

Split into submodules (focused files rather than a ~500-line god file):
    - models/snapshot.py   → SnapshotState, SnapshotDiff + FS/process/socket primitives
    - models/signals.py    → RuntimeSignals + syscall/inotify/network observables
    - models/memory.py     → MemoryObservables + RWX regions, hooks, pslist
    - models/constants.py  → anti-volumetry caps + watched paths

This `__init__` RE-EXPORTS every public name: `from models import X` keeps working
identically for all consumers (hypotheses, snapshot, strace_collector, run_*.py,
tests). No imports to change anywhere else.

Design principles (from the expert-council brainstorm):
    - All models are **frozen** (immutable after creation).
    - Timestamps are **relative to t=0 (start of execution)**, never absolute.
    - No raw bytes embedded (security + volumetry).
    - Strings truncated before ingestion (anti LLM-prompt-injection).
    - Syscalls: aggregated (SyscallSummary), not raw (millions of events possible).
    - inotify: capped at MAX_INOTIFY_EVENTS.
    - Watched filesystem: /etc /home /tmp /var /opt /root only.

Model hierarchy:

    SnapshotState  (before) ─┐
                              ├──► SnapshotDiff ──┐
    SnapshotState  (after)  ─┘                    ├──► HypothesisResult (× N)
    RuntimeSignals ───────────────────────────────┤
    MemoryObservables ────────────────────────────┘

    HypothesisResult × N ──► anomaly_score ──► core/report.py
"""

from __future__ import annotations

from .constants import (
    MAX_CMDLINE_CHARS,
    MAX_DECODED_STRING_CHARS,
    MAX_DECODED_STRINGS,
    MAX_INOTIFY_EVENTS,
    MAX_SYSCALL_ARG_CHARS,
    MAX_SYSCALL_SAMPLE_ARGS,
    PERSISTENCE_PATHS,
    WATCHED_PATHS,
)
from .memory import (
    MemoryObservables,
    MemoryRegion,
    PslistEntry,
    SyscallHook,
)
from .signals import (
    DnsQuery,
    HttpRequest,
    InotifyEvent,
    NetworkFlow,
    NetworkObservables,
    RuntimeSignals,
    SyscallSummary,
)
from .snapshot import (
    FileDiff,
    FileEntry,
    PersistenceEntry,
    ProcessEntry,
    ProcessNode,
    SnapshotDiff,
    SnapshotState,
    SocketEntry,
)

# Full bundle passed to the hypotheses. See hypotheses/_types.py for evaluate().
AnalysisBundle = tuple[SnapshotDiff, RuntimeSignals, MemoryObservables]

__all__ = [
    # constants
    "MAX_CMDLINE_CHARS",
    "MAX_DECODED_STRING_CHARS",
    "MAX_DECODED_STRINGS",
    "MAX_INOTIFY_EVENTS",
    "MAX_SYSCALL_ARG_CHARS",
    "MAX_SYSCALL_SAMPLE_ARGS",
    "PERSISTENCE_PATHS",
    "WATCHED_PATHS",
    # snapshot
    "FileEntry",
    "ProcessEntry",
    "ProcessNode",
    "SocketEntry",
    "PersistenceEntry",
    "SnapshotState",
    "FileDiff",
    "SnapshotDiff",
    # signals
    "SyscallSummary",
    "InotifyEvent",
    "DnsQuery",
    "HttpRequest",
    "NetworkFlow",
    "NetworkObservables",
    "RuntimeSignals",
    # memory
    "PslistEntry",
    "MemoryRegion",
    "SyscallHook",
    "MemoryObservables",
    # bundle
    "AnalysisBundle",
]
