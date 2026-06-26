"""Tests for ml_layer.analyzer.StaticAnalyzer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ml_layer.analyzer import StaticAnalyzer
from ml_layer.features.pdf import FEATURE_ORDER


@pytest.fixture()
def analyzer() -> StaticAnalyzer:
    """StaticAnalyzer with a mocked ONNX session (no real model loaded)."""
    with patch("ml_layer.analyzer.ort.InferenceSession") as mock_session_cls:
        session = mock_session_cls.return_value
        input_meta = MagicMock()
        input_meta.name = "input"
        session.get_inputs.return_value = [input_meta]
        instance = StaticAnalyzer("dummy.onnx")
    return instance


def _set_session(analyzer: StaticAnalyzer, run_return: object) -> None:
    analyzer.session = MagicMock()
    analyzer.session.run.return_value = run_return


def _set_features(analyzer: StaticAnalyzer, overrides: dict[str, float]) -> None:
    features = {k: 0.0 for k in FEATURE_ORDER}
    features.update(overrides)
    analyzer.extractor = MagicMock()
    analyzer.extractor.extract.return_value = features


async def test_analyze_malicious_all_tags(analyzer: StaticAnalyzer) -> None:
    _set_session(analyzer, ["label", [[0.05, 0.95]]])
    _set_features(
        analyzer,
        {
            "entropy": 7.5,
            "pdf_has_javascript": 1.0,
            "pdf_suspicious_js_count": 6.0,
            "pdf_has_launch": 1.0,
        },
    )

    score, tags = await analyzer.analyze(b"%PDF-1.7")

    assert score == 95
    assert tags == [
        "high_entropy",
        "has_javascript",
        "suspicious_js",
        "has_launch_action",
        "known_malware",
    ]


async def test_analyze_high_risk_band(analyzer: StaticAnalyzer) -> None:
    _set_session(analyzer, ["label", [[0.2, 0.8]]])
    _set_features(analyzer, {"entropy": 3.0})

    score, tags = await analyzer.analyze(b"%PDF-1.7")

    assert score == 80
    assert tags == ["high_risk"]


async def test_analyze_malformed_output_falls_back_to_zero(analyzer: StaticAnalyzer) -> None:
    _set_session(analyzer, [123])  # result[1] -> IndexError
    _set_features(analyzer, {"entropy": 1.0})

    score, tags = await analyzer.analyze(b"%PDF-1.7")

    assert score == 0
    assert tags == []


def test_score_value_error_falls_back_to_zero(analyzer: StaticAnalyzer) -> None:
    # result[1][0][1] is not coercible to float -> ValueError branch.
    assert analyzer._score(["label", [["not-a-number", "nope"]]]) == 0
