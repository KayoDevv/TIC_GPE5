"""Hypothesis 2 — C2 communication.

Detects outbound network activity: DNS queries, HTTP requests,
non-loopback TCP/UDP flows, sockets opened to remote endpoints,
high count of connect() syscalls.

Heuristic (thresholds tuned in Phase 7):
    score = 0.40 * has_dns_query
          + 0.40 * has_http_request
          + 0.30 * non_local_tcp_flow
          + 0.20 * remote_socket_opened
          + 0.40 * connect_to_external_ip
          + 0.10 * frequent_connect_syscall  (> 5 calls)
    capped at 1.0.

Pure function, no I/O. Phase 4. Reputation lookups deferred to Phase 9.
"""

from __future__ import annotations

import ipaddress
import re

from models import MemoryObservables, RuntimeSignals, SnapshotDiff
from hypotheses._types import Evidence, HypothesisResult

_DOTTED_QUAD_RE = re.compile(r'(?<!\d)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?!\d)')

_RFC1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def _is_external_ip(ip: str) -> bool:
    """True if the IP is a public/Internet endpoint.

    Excludes loopback, link-local, unspecified, and RFC1918 ranges.
    Intentionally does NOT use addr.is_private — Python flags TEST-NET ranges
    (RFC 5737: 192.0.2/24, 198.51.100/24, 203.0.113/24) as private, but those
    are used by synthetic samples to simulate C2 and must count as external.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
        return False
    return not any(addr in net for net in _RFC1918_NETWORKS)


def _extract_external_ips_from_args(args: list[str]) -> list[str]:
    """Return external IPv4 addresses found in connect() syscall args."""
    return [
        ip
        for arg in args
        for ip in _DOTTED_QUAD_RE.findall(arg)
        if _is_external_ip(ip)
    ]


def _add_signal(
    evidence: list[Evidence],
    score: float,
    weight: float,
    source: str,
    field_path: str,
    value: str,
) -> float:
    evidence.append(Evidence(source=source, field_path=field_path, value=value))
    return score + weight


def _score_dns(network_signals: RuntimeSignals.network, evidence: list[Evidence], score: float) -> float:  # type: ignore[name-defined]
    if not network_signals.dns_queries:
        return score
    return _add_signal(
        evidence, score, weight=0.40,
        source="runtime_signals",
        field_path="network.dns_queries[0].query",
        value=network_signals.dns_queries[0].query[:256],
    )


def _score_http(network_signals: RuntimeSignals.network, evidence: list[Evidence], score: float) -> float:  # type: ignore[name-defined]
    if not network_signals.http_requests:
        return score
    request = network_signals.http_requests[0]
    return _add_signal(
        evidence, score, weight=0.40,
        source="runtime_signals",
        field_path="network.http_requests[0]",
        value=f"{request.method} {request.host}{request.uri}"[:256],
    )


def _score_external_tcp_flows(network_signals: RuntimeSignals.network, evidence: list[Evidence], score: float) -> float:  # type: ignore[name-defined]
    external_flows = [flow for flow in network_signals.tcp_flows if _is_external_ip(flow.dst_ip)]
    if not external_flows:
        return score
    first_flow = external_flows[0]
    return _add_signal(
        evidence, score, weight=0.30,
        source="runtime_signals",
        field_path="network.tcp_flows[?ext][0]",
        value=f"{first_flow.dst_ip}:{first_flow.dst_port}",
    )


def _score_remote_sockets(diff: SnapshotDiff, evidence: list[Evidence], score: float) -> float:
    remote_sockets = [sock for sock in diff.sockets_opened if sock.remote_addr and _is_external_ip(sock.remote_addr)]
    if not remote_sockets:
        return score
    first_socket = remote_sockets[0]
    return _add_signal(
        evidence, score, weight=0.20,
        source="snapshot_diff",
        field_path="sockets_opened[?remote][0]",
        value=f"{first_socket.proto} {first_socket.remote_addr}:{first_socket.remote_port}",
    )


def _score_connect_syscalls(syscalls_summary: list, evidence: list[Evidence], score: float) -> float:
    connect_syscall = next((s for s in syscalls_summary if s.name == "connect"), None)
    if not connect_syscall:
        return score

    external_ips = _extract_external_ips_from_args(connect_syscall.sample_args)
    if external_ips:
        score = _add_signal(
            evidence, score, weight=0.40,
            source="runtime_signals",
            field_path="syscalls_summary[connect].sample_args",
            value=f"connect -> {external_ips[0]}",
        )

    if connect_syscall.call_count > 5:
        score = _add_signal(
            evidence, score, weight=0.10,
            source="runtime_signals",
            field_path="syscalls_summary[connect].call_count",
            value=str(connect_syscall.call_count),
        )

    return score


def evaluate(
    diff: SnapshotDiff,
    signals: RuntimeSignals,
    memory: MemoryObservables,  # noqa: ARG001
) -> HypothesisResult:
    evidence: list[Evidence] = []
    score = 0.0

    network_signals = signals.network
    score = _score_dns(network_signals, evidence, score)
    score = _score_http(network_signals, evidence, score)
    score = _score_external_tcp_flows(network_signals, evidence, score)
    score = _score_remote_sockets(diff, evidence, score)
    score = _score_connect_syscalls(signals.syscalls_summary, evidence, score)

    score = min(score, 1.0)
    return HypothesisResult(
        value=score >= 0.30,
        score=round(score, 3),
        evidence=evidence,
    )
