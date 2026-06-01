"""Memory observables (/proc forensics, post-execution, SIGSTOP protocol).

Covers `MemoryObservables` and its sub-models (pslist, RWX regions, syscall
hooks, decoded strings). Replaces Volatility3 — no kernel profile required.
Self-contained (no dependency on the other `models/` submodules).

NB: this module holds the memory *models*. The actual collection (I/O on /proc)
lives in `agent/memory.py` (imperative shell), not here.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .constants import MAX_DECODED_STRING_CHARS, MAX_DECODED_STRINGS


class PslistEntry(BaseModel):
    """Process seen in /proc (pslist via procfs).

    Cross-checked with SnapshotDiff.processes_spawned to detect hidden processes
    (present in /proc but absent from ps auxf — classic rootkit).
    """

    model_config = ConfigDict(frozen=True)

    pid: int
    ppid: int
    comm: str


class MemoryRegion(BaseModel):
    """Suspicious memory region extracted from /proc/[pid]/maps.

    Main criterion: RWX permissions (readable + writable + executable).
    start_addr / end_addr in hex: "0x7f1234abcd".
    No raw bytes — only metadata (security + volumetry).

    SIGSTOP protocol:
        1. os.kill(pid, signal.SIGSTOP)  → freeze the process
        2. parse /proc/{pid}/maps        → identify RWX regions
        3. read /proc/{pid}/mem          → dump the suspicious regions
        4. extract strings               → decoded_strings in MemoryObservables
        5. os.kill(pid, signal.SIGKILL)  → terminate
    """

    model_config = ConfigDict(frozen=True)

    pid: int
    comm: str
    start_addr: str  # "0x7f..."
    end_addr: str  # "0x7f..."
    permissions: str  # "rwx", "rw-", "r-x", etc.
    size_bytes: int


class SyscallHook(BaseModel):
    """Modified syscall-table entry (detected by comparing /proc/kallsyms).

    is_kernel_symbol: True if the handler points to a known kernel symbol.
    False = suspicious hook (rootkit, malicious LKM).
    """

    model_config = ConfigDict(frozen=True)

    syscall_index: int
    handler_addr: str  # "0xffffffff..."
    symbol: str | None = None  # None if unresolved
    is_kernel_symbol: bool


class MemoryObservables(BaseModel):
    """Raw observables extracted via /proc forensics (SIGSTOP).

    Replaces Volatility3 — no kernel profile required.
    Everything here is an OBSERVED FACT — no classification.
    The data goes into features.memory_observables for the LLM.

    hidden_pids: PIDs present in /proc but absent from ps auxf
        → hidden process (classic rootkit).

    decoded_strings: strings extracted from RWX regions via /proc/[pid]/mem.
        Capped at MAX_DECODED_STRINGS × MAX_DECODED_STRING_CHARS (anti-injection).
        May contain URLs, IPs, commands decrypted at runtime.
    """

    model_config = ConfigDict(frozen=True)

    # pslist via /proc
    pslist: list[PslistEntry] = Field(default_factory=list)
    hidden_pids: list[int] = Field(default_factory=list)  # /proc vs ps cross-check

    # RWX regions from /proc/[pid]/maps
    suspicious_regions: list[MemoryRegion] = Field(default_factory=list)

    # Syscall-table hooks (comparison against /proc/kallsyms)
    syscall_hooks: list[SyscallHook] = Field(default_factory=list)

    # Strings decoded in the suspicious regions (via /proc/[pid]/mem + SIGSTOP)
    decoded_strings: Annotated[
        list[Annotated[str, Field(max_length=MAX_DECODED_STRING_CHARS)]],
        Field(max_length=MAX_DECODED_STRINGS),
    ] = Field(default_factory=list)
