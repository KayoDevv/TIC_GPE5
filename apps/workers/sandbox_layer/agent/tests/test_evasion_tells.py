"""D1bis — evasion as a POSITIVE signal: anti-analysis probe detection.

Pure tests, no I/O. Two layers:

  - extract_evasion_tells: the raw-log matchers find the discriminating tells
    (TracerPid read, container fingerprint) and stay silent on a clean trace —
    including the deliberate exclusions rseq->ENOSYS and arch_prctl(0x3001), both
    environmental (fire for every process / the benign detonation runtime);
  - hypotheses.evasion: each tell adds its weight and exposes evidence, and the
    tracerpid tell alone reaches the PDF suspicious threshold (0.50 * 0.08 = 0.04).

Runnable on a plain host (imports only models / core.scoring / strace_collector,
never the POSIX-only run_*.py orchestrators).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import hypotheses.evasion as h_evasion
from models import EvasionTells, MemoryObservables, RuntimeSignals, SnapshotDiff
from models.signals import SyscallSummary
from strace_collector import extract_evasion_tells

# PDF path evasion weight (run_pdf_analysis.PDF_WEIGHTS["evasion_attempted"]),
# duplicated here so this test stays importable off the agent image.
_PDF_EVASION_WEIGHT = 0.08
_PDF_SUSPICIOUS = 0.04


# ---------------------------------------------------------------------------
# extract_evasion_tells (raw-log matchers)
# ---------------------------------------------------------------------------

def test_tracerpid_read_detected():
    log = '1234 12:00:00.1 openat(AT_FDCWD, "/proc/self/status", O_RDONLY) = 3'
    assert extract_evasion_tells(log).reads_tracerpid


def test_tracerpid_pid_variant_detected():
    log = '1234 12:00:00.1 openat(AT_FDCWD, "/proc/1234/status", O_RDONLY) = 3'
    assert extract_evasion_tells(log).reads_tracerpid


def test_arch_prctl_probe_is_not_a_tell():
    # Dropped after validation: the benign detonation runtime issues 0x3001 under
    # gVisor, so it inflates every score and cannot discriminate.
    log = '1234 12:00:00.1 arch_prctl(0x3001 /* ARCH_??? */, 0x7ffd) = -1 EINVAL'
    t = extract_evasion_tells(log)
    assert not (t.reads_tracerpid or t.container_fingerprint)


def test_rseq_enosys_is_not_a_tell():
    # Universal under gVisor → deliberately ignored (would fire on benign too).
    log = '1234 12:00:00.1 rseq(0x7f00, 0x20, 0, 0x53053053) = -1 ENOSYS'
    t = extract_evasion_tells(log)
    assert not (t.reads_tracerpid or t.container_fingerprint)


def test_container_fingerprint_detected():
    log = '1234 12:00:00.1 openat(AT_FDCWD, "/.dockerenv", O_RDONLY) = -1 ENOENT'
    assert extract_evasion_tells(log).container_fingerprint


def test_clean_trace_has_no_tells():
    log = (
        '1234 12:00:00.1 execve("/bin/cat", ["cat"], 0x7ff) = 0\n'
        '1234 12:00:00.2 openat(AT_FDCWD, "/etc/passwd", O_RDONLY) = 3\n'
        '1234 12:00:00.3 read(3, "root:x:0:0", 4096) = 1024\n'
    )
    t = extract_evasion_tells(log)
    assert not (t.reads_tracerpid or t.container_fingerprint)


# ---------------------------------------------------------------------------
# hypotheses.evasion — tells become a positive score + evidence
# ---------------------------------------------------------------------------

def _diff() -> SnapshotDiff:
    return SnapshotDiff(
        execution_duration_s=2.0,
        file_diffs=[], files_created_count=0,
        files_modified_count=0, files_deleted_count=0,
        processes_spawned=[], processes_terminated=[],
        sockets_opened=[], sockets_closed=[],
        crontab_additions=[], crontab_deletions=[],
        systemd_additions=[], persistence_changes=[],
        exit_code=0,
    )


def _signals(tells: EvasionTells) -> RuntimeSignals:
    # 100 syscalls > MIN_MEANINGFUL_SYSCALLS so the contentless sub-signal does
    # NOT fire — the score under test is the tell's contribution in isolation.
    return RuntimeSignals(
        syscalls_summary=[SyscallSummary(
            name="openat", call_count=100, unique_pids=[42], sample_args=[],
        )],
        execution_duration_s=2.0,
        exit_code=0,
        evasion_tells=tells,
    )


def test_tracerpid_read_scores_and_escalates_on_pdf():
    res = h_evasion.evaluate(
        _diff(), _signals(EvasionTells(reads_tracerpid=True)), MemoryObservables(),
    )
    assert res.value
    assert res.score == 0.50
    assert any("TracerPid" in ev.value for ev in res.evidence)
    # Reaches the PDF suspicious threshold -> needs_more_context (LLM), not benign.
    assert res.score * _PDF_EVASION_WEIGHT >= _PDF_SUSPICIOUS


def test_container_fingerprint_scores():
    res = h_evasion.evaluate(
        _diff(), _signals(EvasionTells(container_fingerprint=True)), MemoryObservables(),
    )
    assert res.score == 0.40
    assert any("container" in ev.value for ev in res.evidence)


def test_tells_stack():
    res = h_evasion.evaluate(
        _diff(),
        _signals(EvasionTells(reads_tracerpid=True, container_fingerprint=True)),
        MemoryObservables(),
    )
    # 0.50 + 0.40 = 0.90
    assert res.score == 0.90
    assert len(res.evidence) == 2


def test_no_tells_no_score():
    # Regression guard: normal activity + no tells must stay 0.0 (no FP).
    res = h_evasion.evaluate(_diff(), _signals(EvasionTells()), MemoryObservables())
    assert res.score == 0.0
    assert res.evidence == []
