"""D-obs — low-observability beacon (knowing when we probably missed).

Pure tests on core.scoring.low_observability_alert. The run_OpusV1.4 miss went
by silently; this beacon must light up on that exact shape (no liveness, or a
quiet zero-score benign) so operators can grep/alert on it — even after the D1
guard escalated the verdict.

Runnable on a plain host (imports only core.scoring).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scoring import low_observability_alert


def test_no_liveness_alerts():
    # Timeout / crash / instant bailout — nothing meaningful ran.
    assert low_observability_alert(
        verdict="needs_more_context", anomaly_score=0.0,
        duration_s=120.0, n_iocs=0, liveness_ok=False,
    ) == "no_liveness"


def test_quiet_benign_alerts():
    # The contentless signature: benign, zero score, zero IOC, sub-5s.
    assert low_observability_alert(
        verdict="benign", anomaly_score=0.0,
        duration_s=0.4, n_iocs=0, liveness_ok=True,
    ) == "quiet_benign"


def test_normal_benign_is_silent():
    # A benign that actually ran for a while with observation = trustworthy.
    assert low_observability_alert(
        verdict="benign", anomaly_score=0.0,
        duration_s=12.0, n_iocs=0, liveness_ok=True,
    ) is None


def test_malicious_is_silent():
    assert low_observability_alert(
        verdict="malicious", anomaly_score=0.42,
        duration_s=3.0, n_iocs=5, liveness_ok=True,
    ) is None


def test_error_is_silent():
    # The error path is already surfaced loudly via log.exception.
    assert low_observability_alert(
        verdict="error", anomaly_score=0.0,
        duration_s=0.1, n_iocs=0, liveness_ok=False,
    ) is None


def test_benign_with_iocs_is_not_quiet():
    # Some signal was observed → not the silent-miss shape.
    assert low_observability_alert(
        verdict="benign", anomaly_score=0.0,
        duration_s=0.4, n_iocs=2, liveness_ok=True,
    ) is None
