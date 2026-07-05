"""D1 + M4 — "absence of signal != benign" guard and liveness observable.

Pure tests, no I/O. Pin the security property that closed the run_v1.4
miss (malicious at score 0.000 classified benign because nothing ran):

  - execution_liveness: normal run = exit 0 + meaningful syscall activity;
  - guarded_verdict: a benign band without liveness escalates, NEVER benign;
  - evasion contentless sub-signal: near-zero activity contributes enough
    score to land in the needs_more_context band on both paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scoring import (
    MIN_MEANINGFUL_SYSCALLS,
    compute_anomaly_score,
    execution_liveness,
    guarded_verdict,
)

import hypotheses.evasion as h_evasion
from models import MemoryObservables, RuntimeSignals, SnapshotDiff
from models.signals import SyscallSummary

import run_analysis as elf
import run_pdf_analysis as pdf


# ---------------------------------------------------------------------------
# execution_liveness (M4)
# ---------------------------------------------------------------------------

def test_liveness_ok_on_normal_run():
    ok, note = execution_liveness(total_syscalls=250, exit_code=0)
    assert ok
    assert "250 syscalls" in note


def test_liveness_fails_on_contentless_run():
    ok, _ = execution_liveness(total_syscalls=5, exit_code=0)
    assert not ok


def test_liveness_fails_on_crash():
    ok, _ = execution_liveness(total_syscalls=5000, exit_code=139)
    assert not ok


def test_liveness_fails_on_timeout_no_exit_code():
    ok, _ = execution_liveness(total_syscalls=5000, exit_code=None)
    assert not ok


# ---------------------------------------------------------------------------
# guarded_verdict (D1)
# ---------------------------------------------------------------------------

def test_zero_score_without_liveness_is_never_benign():
    # The run_v1.4 miss: score 0.000, nothing ran -> must escalate.
    verdict, reason = guarded_verdict(0.0, 0.15, 0.04, liveness_ok=False)
    assert verdict == "needs_more_context"
    assert reason == "no_liveness"


def test_zero_score_with_liveness_stays_benign():
    # "0 signal + normal execution observed" is the ONLY path to benign.
    verdict, reason = guarded_verdict(0.0, 0.15, 0.04, liveness_ok=True)
    assert verdict == "benign"
    assert reason is None


def test_analysis_error_is_never_benign():
    verdict, reason = guarded_verdict(0.0, 0.15, 0.04, liveness_ok=True,
                                      analysis_error=True)
    assert verdict == "needs_more_context"
    assert reason == "analysis_error"


def test_guard_does_not_touch_higher_bands():
    assert guarded_verdict(0.30, 0.15, 0.04, liveness_ok=False) == ("malicious", None)
    assert guarded_verdict(0.05, 0.15, 0.04, liveness_ok=False) == ("needs_more_context", None)


def test_guard_is_threshold_independent():
    # D-calib will raise the suspicious threshold: the hole must stay closed.
    verdict, reason = guarded_verdict(0.0, 0.40, 0.08, liveness_ok=False)
    assert verdict == "needs_more_context"
    assert reason == "no_liveness"


# ---------------------------------------------------------------------------
# evasion contentless sub-signal (score trace, both paths)
# ---------------------------------------------------------------------------

def _signals(total_syscalls: int, exit_code: int | None = 0,
             duration: float = 0.3) -> RuntimeSignals:
    summary = []
    if total_syscalls:
        summary = [SyscallSummary(
            name="openat", call_count=total_syscalls,
            unique_pids=[42], sample_args=[],
        )]
    return RuntimeSignals(
        syscalls_summary=summary,
        execution_duration_s=duration,
        exit_code=exit_code,
    )


def _diff() -> SnapshotDiff:
    return SnapshotDiff(
        execution_duration_s=0.3,
        file_diffs=[], files_created_count=0,
        files_modified_count=0, files_deleted_count=0,
        processes_spawned=[], processes_terminated=[],
        sockets_opened=[], sockets_closed=[],
        crontab_additions=[], crontab_deletions=[],
        systemd_additions=[], persistence_changes=[],
        exit_code=0,
    )


def test_evasion_fires_on_contentless_execution():
    res = h_evasion.evaluate(_diff(), _signals(total_syscalls=3), MemoryObservables())
    assert res.value
    assert res.score >= 0.80
    assert any("contentless" in ev.value for ev in res.evidence)


def test_evasion_silent_on_normal_activity():
    res = h_evasion.evaluate(
        _diff(), _signals(total_syscalls=MIN_MEANINGFUL_SYSCALLS + 50),
        MemoryObservables(),
    )
    assert res.score == 0.0


def test_contentless_lands_in_needs_more_context_band_on_both_paths():
    # The score contribution must clear the validation suspicious threshold
    # (0.04) through each path's evasion weight — that is what makes the fix
    # visible in the validator, the golden compare and the LLM input.
    res = h_evasion.evaluate(_diff(), _signals(total_syscalls=3), MemoryObservables())
    hyp = {"evasion_attempted": res}
    assert compute_anomaly_score(hyp, elf.DEFAULT_WEIGHTS) >= 0.04
    assert compute_anomaly_score(hyp, pdf.PDF_WEIGHTS) >= 0.04
