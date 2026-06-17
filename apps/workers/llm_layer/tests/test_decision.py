from __future__ import annotations

from conftest import NOW, make_report

from llm_layer.decision import build_result, degraded_result
from llm_layer.models import ModelDecision


def test_malicious_passes_through():
    d = ModelDecision(is_malicious=True, explanation_text="beacons out", confidence_score=90)
    r = build_result(make_report(), d, now=NOW)
    assert r.is_malicious is True and r.confidence_score == 90
    assert r.timestamp == NOW


def test_clean_passes_through():
    d = ModelDecision(is_malicious=False, explanation_text="legit invoice", confidence_score=85)
    r = build_result(make_report(), d, now=NOW)
    assert r.is_malicious is False and r.confidence_score == 85


def test_missing_confidence_defaults():
    d = ModelDecision(is_malicious=False, explanation_text="ok")
    r = build_result(make_report(), d, now=NOW)
    assert r.confidence_score == 50


def test_timeout_caps_clean_confidence_and_adds_caveat():
    d = ModelDecision(is_malicious=False, explanation_text="nothing seen", confidence_score=95)
    r = build_result(make_report(timeout=True), d, now=NOW)
    assert r.confidence_score == 40
    assert "partial evidence" in r.explanation_text.lower()


def test_timeout_does_not_touch_malicious():
    d = ModelDecision(is_malicious=True, explanation_text="ransomware", confidence_score=70)
    r = build_result(make_report(timeout=True), d, now=NOW)
    assert r.is_malicious is True and r.confidence_score == 70


def test_injection_hint_appended_when_filtered():
    d = ModelDecision(is_malicious=False, explanation_text="ok", confidence_score=60)
    r = build_result(make_report(prompt_injection_filtered=2), d, now=NOW)
    assert "neutralised before analysis" in r.explanation_text


def test_no_injection_hint_when_zero():
    d = ModelDecision(is_malicious=False, explanation_text="ok", confidence_score=60)
    r = build_result(make_report(prompt_injection_filtered=0), d, now=NOW)
    assert "neutralised before analysis" not in r.explanation_text


def test_build_result_uses_now_when_omitted():
    d = ModelDecision(is_malicious=False, explanation_text="ok")
    r = build_result(make_report(), d)
    assert r.timestamp is not None


def test_degraded_is_cautious():
    r = degraded_result(make_report(), reason="all endpoints failed", now=NOW)
    assert r.is_malicious is True and r.confidence_score == 0
    assert "could not be completed" in r.explanation_text


def test_degraded_appends_injection_hint_and_default_now():
    r = degraded_result(make_report(prompt_injection_filtered=1), reason="x")
    assert "neutralised before analysis" in r.explanation_text
    assert r.timestamp is not None
