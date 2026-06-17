"""D1 follow-up — a defeated static probe is a signal, not an absence of signal.

Root cause of the fb87d8a7 miss (run_OpusV1.4 + run_after_D1): the sample made
pdfid hang past its timeout; the failure was silently converted into score 0.0
=> benign. These tests pin the new behaviour: probe timeout => score 0.2
(0.06 through the 0.30 hypothesis weight => needs_more_context band), with an
explicit evidence trail. Tool ABSENT stays score 0.0 (environment problem,
not the sample's doing).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import hypotheses.pdf_static as pdf_static
from core.report import explain_signal
from core.scoring import compute_anomaly_score


def test_probe_timeout_scores_inconclusive(monkeypatch):
    def _hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pdfid", timeout=30)
    monkeypatch.setattr(pdf_static.subprocess, "run", _hang)

    res = pdf_static.evaluate_static(Path("/sample.pdf"))

    assert res.score == 0.2
    assert any("probe_timeout" in ev.field_path for ev in res.evidence)
    # Through the PDF weight (0.30): 0.06 >= suspicious 0.04 -> escalates.
    score = compute_anomaly_score({"pdf_static_indicators": res},
                                  {"pdf_static_indicators": 0.30})
    assert 0.04 <= score < 0.15


def test_tool_absent_stays_silent(monkeypatch):
    def _missing(*args, **kwargs):
        raise FileNotFoundError("pdfid")
    monkeypatch.setattr(pdf_static.subprocess, "run", _missing)

    res = pdf_static.evaluate_static(Path("/sample.pdf"))
    assert res.score == 0.0
    assert res.evidence == []


def test_probe_timeout_is_explained_in_narrative():
    assert explain_signal("pdf_static.probe_timeout") is not None
