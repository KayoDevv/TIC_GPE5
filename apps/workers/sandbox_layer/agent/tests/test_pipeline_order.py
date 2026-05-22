"""Unit tests — pipeline v2 orchestrator.

Validates:
  - Correct execution order of the 7 hypotheses
  - Early-exit triggered when partial score >= EARLY_EXIT_THRESHOLD (0.45)
  - Only H3 (code_injection) skipped — H1 (persistence) always runs
  - Early-exit NOT triggered on weak signal
  - hypothesis_timings_ms = 0 for H3 when early-exit fires
  - Sum of DEFAULT_WEIGHTS = 1.0

Run: pytest apps/workers/sandbox_layer/agent/tests/test_pipeline_order.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from models import (
    MemoryObservables,
    NetworkObservables,
    RuntimeSignals,
    SnapshotDiff,
)
from hypotheses._types import HypothesisResult
import run_analysis


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _empty_diff() -> SnapshotDiff:
    return SnapshotDiff(
        execution_duration_s=10.0,
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


def _empty_signals() -> RuntimeSignals:
    return RuntimeSignals(
        syscalls_summary=[],
        inotify_events=[],
        network=NetworkObservables(),
        execution_duration_s=10.0,
        sleep_cumulated_s=0.0,
        exit_code=0,
    )


def _result(score: float) -> HypothesisResult:
    return HypothesisResult(value=score >= 0.3, score=score, evidence=[])


_DIFF = _empty_diff()
_SIG  = _empty_signals()
_MEM  = MemoryObservables()


# ---------------------------------------------------------------------------
# Tests — execution order
# ---------------------------------------------------------------------------

def test_all_hypotheses_executed_when_no_early_exit():
    """All 7 hypotheses run when the partial score stays low."""
    import hypotheses.evasion    as h_ev
    import hypotheses.encryption as h_enc
    import hypotheses.c2         as h_c2
    import hypotheses.lolbins    as h_lo
    import hypotheses.propagation as h_pr
    import hypotheses.persistence as h_pe
    import hypotheses.injection  as h_in

    # Low scores -> early-exit not triggered
    with patch.object(h_ev,  "evaluate", lambda *a: _result(0.0)), \
         patch.object(h_enc, "evaluate", lambda *a: _result(0.05)), \
         patch.object(h_c2,  "evaluate", lambda *a: _result(0.05)), \
         patch.object(h_lo,  "evaluate", lambda *a: _result(0.0)), \
         patch.object(h_pr,  "evaluate", lambda *a: _result(0.0)), \
         patch.object(h_pe,  "evaluate", lambda *a: _result(0.1)), \
         patch.object(h_in,  "evaluate", lambda *a: _result(0.1)):

        results, early_exit, timings = run_analysis._run_hypotheses_ordered(
            _DIFF, _SIG, _MEM
        )

    assert early_exit is False
    assert set(results.keys()) == {
        "evasion_attempted", "file_encryption", "c2_communication",
        "lolbins_abuse", "propagation", "persistence_detected", "code_injection",
    }
    # Timings must be non-negative for every executed hypothesis
    assert timings.get("code_injection", 0) >= 0
    assert timings.get("persistence_detected", 0) >= 0


def test_early_exit_skips_only_h3():
    """Early-exit triggered -> only H3 (code_injection) is skipped, H1 always runs.

    Threshold EARLY_EXIT_THRESHOLD = 0.45.
    Max partial score (first 5 hypotheses) = 0.55.
    To trigger: ~82% of partial weights at max (partial score ~0.45).
    """
    import hypotheses.evasion    as h_ev
    import hypotheses.encryption as h_enc
    import hypotheses.c2         as h_c2
    import hypotheses.lolbins    as h_lo
    import hypotheses.propagation as h_pr
    import hypotheses.persistence as h_pe
    import hypotheses.injection  as h_in

    # High scores on C2 + encryption + lolbins + propagation -> partial > 0.45
    # C2(0.20*1.0) + enc(0.10*1.0) + lolbins(0.15*1.0) + prop(0.05*1.0) = 0.50 > 0.45
    injection_called = []

    def _track_injection(*a):
        injection_called.append(True)
        return _result(0.9)

    with patch.object(h_ev,  "evaluate", lambda *a: _result(0.0)), \
         patch.object(h_enc, "evaluate", lambda *a: _result(1.0)), \
         patch.object(h_c2,  "evaluate", lambda *a: _result(1.0)), \
         patch.object(h_lo,  "evaluate", lambda *a: _result(1.0)), \
         patch.object(h_pr,  "evaluate", lambda *a: _result(1.0)), \
         patch.object(h_pe,  "evaluate", lambda *a: _result(0.5)), \
         patch.object(h_in,  "evaluate", _track_injection):

        results, early_exit, timings = run_analysis._run_hypotheses_ordered(
            _DIFF, _SIG, _MEM
        )

    assert early_exit is True
    # H3 must have been skipped
    assert "code_injection" not in results
    assert timings.get("code_injection") == 0.0
    assert not injection_called, "H3 should not have been called"
    # H1 must still be present
    assert "persistence_detected" in results


def test_early_exit_not_triggered_on_low_score():
    """Low score -> no early-exit, full pipeline runs."""
    import hypotheses.evasion    as h_ev
    import hypotheses.encryption as h_enc
    import hypotheses.c2         as h_c2
    import hypotheses.lolbins    as h_lo
    import hypotheses.propagation as h_pr
    import hypotheses.persistence as h_pe
    import hypotheses.injection  as h_in

    # Max partial score with these values:
    # enc(0.10*0.1) + c2(0.20*0.1) + lolbins(0.15*0.0) + prop(0.05*0.0) = 0.03 < 0.45
    with patch.object(h_ev,  "evaluate", lambda *a: _result(0.0)), \
         patch.object(h_enc, "evaluate", lambda *a: _result(0.1)), \
         patch.object(h_c2,  "evaluate", lambda *a: _result(0.1)), \
         patch.object(h_lo,  "evaluate", lambda *a: _result(0.0)), \
         patch.object(h_pr,  "evaluate", lambda *a: _result(0.0)), \
         patch.object(h_pe,  "evaluate", lambda *a: _result(0.1)), \
         patch.object(h_in,  "evaluate", lambda *a: _result(0.1)):

        results, early_exit, timings = run_analysis._run_hypotheses_ordered(
            _DIFF, _SIG, _MEM
        )

    assert early_exit is False
    assert "code_injection" in results
    assert "persistence_detected" in results


# ---------------------------------------------------------------------------
# Tests — anomaly_score
# ---------------------------------------------------------------------------

def test_compute_anomaly_score_uses_weights():
    """All scores at 1.0 -> anomaly_score = 1.0 (sum of weights = 1.0)."""
    hyp = {k: _result(1.0) for k in run_analysis.DEFAULT_WEIGHTS}
    score = run_analysis._compute_anomaly_score(hyp)
    assert score == pytest.approx(1.0, abs=0.001)


def test_compute_anomaly_score_zero_on_empty():
    assert run_analysis._compute_anomaly_score({}) == 0.0


def test_default_weights_sum_to_one():
    total = sum(run_analysis.DEFAULT_WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=0.001)


def test_all_7_keys_in_default_weights():
    """DEFAULT_WEIGHTS must contain exactly the 7 keys of pipeline v2."""
    expected = {
        "persistence_detected", "c2_communication", "code_injection",
        "lolbins_abuse", "file_encryption", "evasion_attempted", "propagation",
    }
    assert set(run_analysis.DEFAULT_WEIGHTS.keys()) == expected


def test_early_exit_threshold_reachable():
    """EARLY_EXIT_THRESHOLD must be <= sum of weights of the first 5 hypotheses."""
    # Weights of the 5 hypotheses run before H1+H3 in the pipeline order
    pre_h1_h3_keys = {
        "evasion_attempted", "file_encryption", "c2_communication",
        "lolbins_abuse", "propagation",
    }
    max_partial = sum(
        v for k, v in run_analysis.DEFAULT_WEIGHTS.items()
        if k in pre_h1_h3_keys
    )
    assert run_analysis.EARLY_EXIT_THRESHOLD <= max_partial, (
        f"Threshold {run_analysis.EARLY_EXIT_THRESHOLD} > max partial score "
        f"{max_partial:.2f} — early-exit can never trigger"
    )
