"""Intermediate data models — the sandbox pipeline's source-of-truth contract,
exchanged between collection, the behavioural hypotheses, the memory-forensics
runner, and the report builder.

Split into focused submodules (snapshot / signals / memory / constants); this
`__init__` re-exports every public name so `from models import X` keeps working.

Design constraints: all models frozen; timestamps relative to t=0; no raw bytes;
strings truncated before ingestion (anti prompt-injection + volumetry); syscalls
aggregated, inotify capped; watched FS = /etc /home /tmp /var /opt /root.

Flow: SnapshotDiff + RuntimeSignals + MemoryObservables → HypothesisResult ×N →
anomaly_score → core/report.py.
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
    EvasionTells,
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
    "EvasionTells",
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
