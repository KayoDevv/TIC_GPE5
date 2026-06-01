"""Signals collected DURING execution (temporal dimension).

Covers aggregated syscalls (strace), inotify, and network observables
(`RuntimeSignals` + sub-models). Complementary to `SnapshotDiff` (before/after).
Self-contained (no dependency on the other `models/` submodules).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .constants import (
    MAX_INOTIFY_EVENTS,
    MAX_SYSCALL_ARG_CHARS,
    MAX_SYSCALL_SAMPLE_ARGS,
)


class SyscallSummary(BaseModel):
    """Aggregated summary of one syscall — no raw events (too large).

    Collected via strace -f -tt -e trace=all (SYS_PTRACE cap required).
    sample_args: the first few argument occurrences, truncated.
    Interesting syscalls include: openat, connect, clone, ptrace, execve, mmap,
    mprotect, write, unlink.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    call_count: int
    unique_pids: list[int]
    sample_args: Annotated[
        list[Annotated[str, Field(max_length=MAX_SYSCALL_ARG_CHARS)]],
        Field(max_length=MAX_SYSCALL_SAMPLE_ARGS),
    ] = Field(default_factory=list)


class InotifyEvent(BaseModel):
    """Timestamped inotify event (relative to t=0).

    Collected via inotifywait -m -r on WATCHED_PATHS.
    The full list is capped at MAX_INOTIFY_EVENTS in RuntimeSignals.
    """

    model_config = ConfigDict(frozen=True)

    relative_ts_s: float
    kind: Literal["CREATE", "MODIFY", "DELETE", "MOVED_FROM", "MOVED_TO", "ATTRIB"]
    path: str
    filename: str


class DnsQuery(BaseModel):
    """DNS query captured via INetSim (fake DNS resolver).

    answers: IP addresses returned (INetSim always returns a fake IP).
    """

    model_config = ConfigDict(frozen=True)

    query: str
    qtype: str  # A, AAAA, MX, TXT, CNAME, ...
    answers: list[str]
    relative_ts_s: float


class HttpRequest(BaseModel):
    """HTTP/S request captured via INetSim.

    response_code: None if the connection was cut before the response.
    """

    model_config = ConfigDict(frozen=True)

    method: str
    host: str
    uri: str
    user_agent: str | None = None
    response_code: int | None = None
    relative_ts_s: float


class NetworkFlow(BaseModel):
    """TCP or UDP flow — aggregated by 5-tuple from the PCAP.

    bytes_sent and packet_count are from the sample's point of view (src = container).
    """

    model_config = ConfigDict(frozen=True)

    proto: Literal["tcp", "udp"]
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    bytes_sent: int
    packet_count: int
    first_seen_relative_s: float


class NetworkObservables(BaseModel):
    """All network observables collected during execution.

    Structure inspired by Cuckoo's network section (the only portable part of Cuckoo).
    dns_queries and http_requests come from INetSim.
    tcp_flows and udp_flows come from the PCAP (tcpdump sidecar).
    """

    model_config = ConfigDict(frozen=True)

    dns_queries: list[DnsQuery] = Field(default_factory=list)
    http_requests: list[HttpRequest] = Field(default_factory=list)
    tcp_flows: list[NetworkFlow] = Field(default_factory=list)
    udp_flows: list[NetworkFlow] = Field(default_factory=list)


class RuntimeSignals(BaseModel):
    """Signals collected DURING the sample's execution.

    Complementary to SnapshotDiff (which is before/after). RuntimeSignals captures
    the temporal dimension: what happened, in which order, at what frequency.

    syscalls_summary: aggregated from strace -f -tt -e trace=all (SYS_PTRACE).
    inotify_events: capped at MAX_INOTIFY_EVENTS.
    sleep_cumulated_s: sum of all sleep/nanosleep — used by hypothesis_evasion to
        detect anti-sandbox sleeps.
    """

    model_config = ConfigDict(frozen=True)

    # Aggregated syscalls (strace -f → parsed line by line → aggregated)
    syscalls_summary: list[SyscallSummary] = Field(default_factory=list)

    # Real-time filesystem events (inotifywait)
    inotify_events: Annotated[
        list[InotifyEvent],
        Field(max_length=MAX_INOTIFY_EVENTS),
    ] = Field(default_factory=list)

    # Network
    network: NetworkObservables = Field(default_factory=NetworkObservables)

    # Execution metadata
    execution_duration_s: float
    sleep_cumulated_s: float = 0.0  # anti-sandbox sleep detection
    exit_code: int | None = None
