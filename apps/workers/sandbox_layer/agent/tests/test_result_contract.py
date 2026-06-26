"""Gate: a real build_result_event output must validate against the published
Kafka schema, so the contract and the code cannot drift silently."""

import json
from pathlib import Path

import pytest

from core.report import build_result_event
from hypotheses._types import HypothesisResult

jsonschema = pytest.importorskip("jsonschema")

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[5]
     / "packages" / "kafka-schemas" / "sandbox_layer.result.json").read_text()
)


def _event(verdict, weights, hyp_results, iocs):
    return build_result_event(
        job_id="00000000-0000-0000-0000-000000000000",
        iocs=iocs,
        behavior_summary="x",
        email_context={},
        timeout_triggered=False,
        timestamp="2026-06-24T00:00:00Z",
        anomaly_score=0.54,
        duration_s=1.0,
        error=None,
        pipeline_version="test",
        hypothesis_timings_ms={},
        hyp_results=hyp_results,
        weights=weights,
        verdict=verdict,
        meta_extra={"liveness_ok": True, "low_observability": None},
    )


def test_elf_event_matches_contract():
    weights = {"c2_communication": 0.20, "code_injection": 0.20}
    hyp = {"c2_communication": HypothesisResult(value=True, score=0.8)}
    iocs = [{"type": "syscall", "value": "connect -> 1.2.3.4", "mitre_tactic": "TA0011"}]
    jsonschema.validate(_event("malicious", weights, hyp, iocs), SCHEMA)


def test_pdf_indicator_ioc_is_valid():
    weights = {"pdf_static_indicators": 0.30}
    hyp = {"pdf_static_indicators": HypothesisResult(value=True, score=0.5)}
    iocs = [{"type": "pdf_indicator", "value": "JS+OpenAction", "mitre_tactic": "T1027"}]
    jsonschema.validate(_event("needs_more_context", weights, hyp, iocs), SCHEMA)


def test_skipped_hypothesis_is_null_not_zero():
    weights = {"c2_communication": 0.20, "code_injection": 0.20}
    hyp = {"c2_communication": HypothesisResult(value=True, score=0.8)}
    signals = {s["name"]: s for s in _event("malicious", weights, hyp, [])["signals"]}
    assert signals["code_injection"]["evaluated"] is False
    assert signals["code_injection"]["score"] is None
    assert signals["c2_communication"]["evaluated"] is True
    assert signals["c2_communication"]["score"] == 0.8
