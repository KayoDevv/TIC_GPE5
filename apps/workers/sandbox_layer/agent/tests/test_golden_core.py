"""Golden (characterization) tests — pin the PURE scoring / verdict / narrative core.

Goal: anti-regression net for the refactor. These tests freeze the CURRENT output
of the pure aggregation layer (anomaly_score, verdict band, narrative /
behavior_summary) for representative hypothesis results. When this logic moves
from run_*.py into core/ (phases 2-3), these golden values MUST stay identical —
that is the proof the behaviour is preserved.

100% pure: no subprocess, no I/O, no real sample. Runs in CI.

Regenerate the golden baseline (run ONCE on a machine with the agent deps — the
VM — AFTER confirming the current behaviour is correct):

    GOLDEN_UPDATE=1 python -m pytest tests/test_golden_core.py
    git add tests/golden/*.json && git commit -m "test(agent): golden baseline"

Then every run compares against these reference files.

NB: in phase 2, only the imports below changed (run_pdf_analysis/run_analysis
→ core.scoring/core.report). The golden values do not move.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from hypotheses._types import Evidence, HypothesisResult
from core.report import build_iocs, build_result_event
from models import MemoryRegion
import run_analysis as elf
import run_pdf_analysis as pdf

GOLDEN_DIR = Path(__file__).parent / "golden"
_UPDATE = bool(os.getenv("GOLDEN_UPDATE"))
_FIXED_DURATION = 12.3  # narratives embed the duration → fixed for determinism


def _hr(score: float, *evidence: tuple[str, str, str]) -> HypothesisResult:
    """HypothesisResult helper. evidence = tuples (source, field_path, value)."""
    return HypothesisResult(
        value=score >= 0.3,
        score=score,
        evidence=[Evidence(source=s, field_path=fp, value=v) for s, fp, v in evidence],
    )


# --- Representative PDF hypothesis sets, covering the 3 verdict bands ---

def _pdf_benign() -> dict:
    return {k: _hr(0.0) for k in pdf.PDF_WEIGHTS}


def _pdf_ambiguous() -> dict:
    # pdf_static_indicators 0.15 × weight 0.30 = 0.045 → needs_more_context
    r = {k: _hr(0.0) for k in pdf.PDF_WEIGHTS}
    r["pdf_static_indicators"] = _hr(
        0.15, ("snapshot_diff", "pdf_uri.external_url", "http://acme-portal.example/login")
    )
    return r


def _pdf_malicious() -> dict:
    r = {k: _hr(0.0) for k in pdf.PDF_WEIGHTS}
    r["pdf_static_indicators"] = _hr(
        0.8,
        ("snapshot_diff", "pdf_static.js_auto_triggered", "OpenAction"),
        ("snapshot_diff", "pdf_static.launch_action", "/Launch cmd.exe"),
        ("snapshot_diff", "pdf_uri.exec_extension", "http://evil.test/p.exe"),
    )
    r["c2_communication"] = _hr(
        0.7, ("runtime_signals", "network.dns_queries[0].query", "c2.evil.test")
    )
    return r


def _pdf_output(hyp: dict) -> dict:
    score = pdf._compute_anomaly_score(hyp)
    verdict, narrative = pdf._build_narrative(hyp, score, _FIXED_DURATION)
    return {"anomaly_score": score, "verdict": verdict, "narrative": narrative}


# --- Representative ELF hypothesis sets ---

def _elf_benign() -> dict:
    return {k: _hr(0.0) for k in elf.DEFAULT_WEIGHTS}


def _elf_malicious() -> dict:
    return {k: _hr(1.0) for k in elf.DEFAULT_WEIGHTS}


def _elf_output(hyp: dict) -> dict:
    score = elf._compute_anomaly_score(hyp)
    return {
        "anomaly_score": score,
        "behavior_summary": elf._behavior_summary(hyp, score, _FIXED_DURATION),
    }


# --- IOC + event assembly (core/report.build_iocs / build_result_event) ---

_SAMPLE_MITRE = {
    "c2_communication":      "TA0011",
    "lolbins_abuse":         "T1059",
    "pdf_static_indicators": "T1027",
}


def _elf_ioc_type(name: str, ev) -> str:
    return "syscall" if ev.source == "runtime_signals" else "file_hash"


def _pdf_ioc_type(name: str, ev) -> str:
    return "pdf_indicator" if name == "pdf_static_indicators" else "syscall"


def _iocs_elf() -> list:
    hyp = {
        "c2_communication": _hr(0.7, ("runtime_signals", "network.dns_queries[0].query", "c2.evil.test")),
        "lolbins_abuse":    _hr(0.0),  # value False → ignored
    }
    region = MemoryRegion(
        pid=42, comm="mutool", start_addr="0x7f00", end_addr="0x7f10",
        permissions="rwx", size_bytes=4096,
    )
    return build_iocs(hyp, _SAMPLE_MITRE, _elf_ioc_type, memory_regions=[region])


def _iocs_pdf() -> list:
    hyp = {
        "pdf_static_indicators": _hr(0.8, ("snapshot_diff", "pdf_static.launch_action", "/Launch cmd.exe")),
        "c2_communication":      _hr(0.7, ("runtime_signals", "network.dns_queries[0].query", "c2.evil.test")),
    }
    return build_iocs(hyp, _SAMPLE_MITRE, _pdf_ioc_type)


def _event(verdict, meta_extra, pipeline_version) -> dict:
    hyp = {"c2_communication": _hr(0.7, ("runtime_signals", "x.query", "c2.evil.test"))}
    return build_result_event(
        job_id="JOB-1",
        iocs=[{"type": "syscall", "value": "v", "mitre_tactic": "TA0011", "description": "d"}],
        behavior_summary="summary",
        email_context={"sender": "x@y"},
        timeout_triggered=False,
        timestamp="2026-01-01T00:00:00+00:00",
        anomaly_score=0.42,
        duration_s=12.3,
        error=None,
        pipeline_version=pipeline_version,
        hypothesis_timings_ms={"c2_communication": 1.0},
        hyp_results=hyp,
        verdict=verdict,
        meta_extra=meta_extra,
    )


CASES = {
    "pdf_benign":    lambda: _pdf_output(_pdf_benign()),
    "pdf_ambiguous": lambda: _pdf_output(_pdf_ambiguous()),
    "pdf_malicious": lambda: _pdf_output(_pdf_malicious()),
    "elf_benign":    lambda: _elf_output(_elf_benign()),
    "elf_malicious": lambda: _elf_output(_elf_malicious()),
    "iocs_elf":      _iocs_elf,
    "iocs_pdf":      _iocs_pdf,
    "event_elf":     lambda: _event(None, {"early_exit": False}, "v2"),
    "event_pdf":     lambda: _event("malicious", {"file_type": "pdf"}, "v2-pdf"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden_core(name: str) -> None:
    actual = CASES[name]()
    path = GOLDEN_DIR / f"{name}.json"

    if _UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        pytest.skip(f"golden updated: {path.name}")

    assert path.exists(), (
        f"missing golden: {path}. Run first: "
        f"GOLDEN_UPDATE=1 python -m pytest tests/test_golden_core.py"
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, f"regression on {name}: {actual} != {expected}"
