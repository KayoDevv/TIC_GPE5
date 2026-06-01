"""System-state snapshot models and their before→after diff.

Covers the state snapshot (`SnapshotState`) and the computed diff (`SnapshotDiff`),
the main INPUT of the behavioural hypotheses. All frozen. No dependency on the
other `models/` submodules (self-contained).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .constants import MAX_CMDLINE_CHARS


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class FileEntry(BaseModel):
    """A file observed at instant T.

    sha256 is None if the file is not readable (permissions, socket, etc.).
    mtime_relative_s is relative to the start of execution (t=0).
    """

    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str | None = None
    size_bytes: int
    permissions: str  # symbolic (stat %A output), e.g. "-rwxr-xr-x"
    owner: str  # e.g. "root" or "user"
    mtime_relative_s: float  # seconds since t=0


class ProcessEntry(BaseModel):
    """Process entry (from ps auxf or /proc).

    cmdline truncated to MAX_CMDLINE_CHARS before storage.
    ld_preload extracted only from /proc/[pid]/environ (not the full env).
    """

    model_config = ConfigDict(frozen=True)

    pid: int
    ppid: int
    user: str
    comm: str  # short name (15 chars max, ps COMM field)
    cmdline: Annotated[str, Field(max_length=MAX_CMDLINE_CHARS)]
    stat: str  # R/S/D/Z/T
    ld_preload: str | None = None  # value of LD_PRELOAD if present


class ProcessNode(BaseModel):
    """Process-tree node — parent/child hierarchy.

    Call ProcessNode.model_rebuild() after the class definition to resolve the
    forward reference.
    """

    model_config = ConfigDict(frozen=True)

    entry: ProcessEntry
    children: list[ProcessNode] = Field(default_factory=list)


ProcessNode.model_rebuild()


class SocketEntry(BaseModel):
    """Open network socket (from ss --json).

    remote_addr / remote_port are None for LISTEN sockets.
    pid is None if the process→socket association could not be resolved.
    """

    model_config = ConfigDict(frozen=True)

    proto: Literal["tcp", "tcp6", "udp", "udp6"]
    local_addr: str
    local_port: int
    remote_addr: str | None = None
    remote_port: int | None = None
    state: str  # ESTABLISHED, LISTEN, TIME_WAIT, etc.
    pid: int | None = None


class PersistenceEntry(BaseModel):
    """Known persistence path + a fingerprint of its content.

    Watches: cron.d, profile.d, authorized_keys, rc.local, init.d, bashrc.
    content_sha256 detects any modification between before/after.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    content_sha256: str  # SHA-256 of the file content


# ---------------------------------------------------------------------------
# SnapshotState (system state at instant T)
# ---------------------------------------------------------------------------


class SnapshotState(BaseModel):
    """Complete photograph of the system state at instant T.

    captured_at_relative_s = 0.0 for the BEFORE-execution snapshot.
    captured_at_relative_s > 0 for the AFTER-execution snapshot.

    filesystem: only the paths under WATCHED_PATHS.
    process_tree: full hierarchical tree (all processes visible via ps).
    persistence_entries: only the existing PERSISTENCE_PATHS paths.
    """

    model_config = ConfigDict(frozen=True)

    captured_at_relative_s: float
    filesystem: list[FileEntry]
    process_tree: list[ProcessNode]
    sockets: list[SocketEntry]
    crontab_lines: list[str]
    systemd_active_units: list[str]
    persistence_entries: list[PersistenceEntry]


# ---------------------------------------------------------------------------
# SnapshotDiff (before → after differential)
# ---------------------------------------------------------------------------


class FileDiff(BaseModel):
    """File change between the before and after snapshots.

    kind:
        created  — file absent before, present after
        modified — sha256 differs between before and after
        deleted  — file present before, absent after
    """

    model_config = ConfigDict(frozen=True)

    path: str
    kind: Literal["created", "modified", "deleted"]
    sha256_before: str | None = None
    sha256_after: str | None = None
    size_delta_bytes: int = 0
    permissions_before: str | None = None
    permissions_after: str | None = None


class SnapshotDiff(BaseModel):
    """Differential computed between the before and after SnapshotState.

    This is the MAIN INPUT of the behavioural hypotheses (Layer 2).
    Immutable — computed once per analysis, shared across all modules.

    files_created_count / files_deleted_count: quick counts used by
    hypothesis_encryption to detect a mass rename.
    """

    model_config = ConfigDict(frozen=True)

    execution_duration_s: float

    # --- Filesystem ---
    file_diffs: list[FileDiff]
    files_created_count: int  # len([d for d in file_diffs if d.kind == "created"])
    files_modified_count: int
    files_deleted_count: int

    # --- Processes ---
    processes_spawned: list[ProcessEntry]  # in after, absent from before
    processes_terminated: list[ProcessEntry]  # in before, absent from after

    # --- Sockets ---
    sockets_opened: list[SocketEntry]  # in after, absent from before
    sockets_closed: list[SocketEntry]  # in before, absent from after

    # --- Persistence ---
    crontab_additions: list[str]  # added lines
    crontab_deletions: list[str]  # removed lines
    systemd_additions: list[str]  # newly active units
    persistence_changes: list[PersistenceEntry]  # entries created or modified

    # --- Execution metadata ---
    exit_code: int | None = None
