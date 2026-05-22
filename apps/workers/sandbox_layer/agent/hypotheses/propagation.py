"""Hypothesis 6 — Lateral propagation.

Detects internal network scanning / lateral-movement attempts:
- TCP connections to private RFC1918 ranges other than localhost
- Multiple distinct internal destinations (scan pattern)
- Connections to SMB(445), RPC(135), RDP(3389), SSH(22), WinRM(5985/5986)
- Mounting of remote filesystems (cifs, nfs)

Heuristic:
    score = 0.30 * any_internal_target
          + 0.30 * multiple_distinct_targets  (>= 3)
          + 0.30 * lateral_service_port      (445/135/3389/22/5985)
          + 0.20 * mount_remote_fs
    capped at 1.0.

Pure function. Phase 4.
"""

from __future__ import annotations

import ipaddress
import re

_INET_ADDR_RE = re.compile(r'inet_addr\("(\d+\.\d+\.\d+\.\d+)"\)')
_SIN_PORT_RE = re.compile(r'sin_port=htons\((\d+)\)')


def _targets_from_connect_args(args: list[str]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for a in args:
        ip_m = _INET_ADDR_RE.search(a)
        port_m = _SIN_PORT_RE.search(a)
        if ip_m and port_m:
            out.append((ip_m.group(1), int(port_m.group(1))))
    return out

from models import (
    MemoryObservables,
    RuntimeSignals,
    SnapshotDiff,
)

from hypotheses._types import Evidence, HypothesisResult

_LATERAL_PORTS = {22, 135, 139, 445, 3389, 5985, 5986}


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private and not addr.is_loopback


def evaluate(
    diff: SnapshotDiff,
    signals: RuntimeSignals,
    memory: MemoryObservables,  # noqa: ARG001
) -> HypothesisResult:
    evidence: list[Evidence] = []
    score = 0.0

    targets = []
    for f in signals.network.tcp_flows:
        if _is_private(f.dst_ip):
            targets.append((f.dst_ip, f.dst_port))
    for s in diff.sockets_opened:
        if s.remote_addr and s.remote_port and _is_private(s.remote_addr):
            targets.append((s.remote_addr, s.remote_port))

    connect_calls = next(
        (s for s in signals.syscalls_summary if s.name == "connect"),
        None,
    )
    if connect_calls:
        for ip, port in _targets_from_connect_args(connect_calls.sample_args):
            if _is_private(ip):
                targets.append((ip, port))

    distinct_targets = {t[0] for t in targets}
    # Require >=2 distinct private targets to trigger — a single private IP is
    # almost always an incidental libc/resolver connect (Docker bridge gateway,
    # systemd-resolved fallback, etc.). Real lateral movement scans multiple
    # hosts.
    if len(distinct_targets) >= 2:
        score += 0.30
        ip, port = targets[0]
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="network.tcp_flows[?private][0]",
            value=f"{ip}:{port}",
        ))

    distinct = distinct_targets
    if len(distinct) >= 3:
        score += 0.30
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="network.tcp_flows[?private]",
            value=f"{len(distinct)} distinct internal hosts",
        ))

    lateral = [t for t in targets if t[1] in _LATERAL_PORTS]
    if lateral:
        score += 0.30
        ip, port = lateral[0]
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="network.tcp_flows[?lateral_port][0]",
            value=f"{ip}:{port}",
        ))

    # Remote filesystem mount via mount syscall (cifs, nfs)
    mount_calls = next(
        (s for s in signals.syscalls_summary if s.name == "mount"),
        None,
    )
    if mount_calls:
        remote_mount = [
            a for a in mount_calls.sample_args
            if any(fs in a for fs in ("cifs", "nfs", "smb"))
        ]
        if remote_mount:
            score += 0.20
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="syscalls_summary[mount].sample_args",
                value=remote_mount[0][:256],
            ))

    score = min(score, 1.0)
    return HypothesisResult(
        value=score >= 0.30,
        score=round(score, 3),
        evidence=evidence,
    )
