"""Tests for ml_layer.analyzer: scoring, calibration, and metadata loading."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ml_layer.analyzer import (
    FeatureOrderMismatch,
    ModelOutputError,
    StaticAnalyzer,
    _malicious_probability,
    abstention,
    calibrate_score,
    validate_feature_order,
)
from ml_layer.features.pdf import FEATURE_ORDER


def _build_analyzer(model_path: str, shape: object) -> StaticAnalyzer:
    with patch("ml_layer.analyzer.ort.InferenceSession") as mock_session_cls:
        session = mock_session_cls.return_value
        input_meta = MagicMock()
        input_meta.name = "input"
        input_meta.shape = shape
        session.get_inputs.return_value = [input_meta]
        return StaticAnalyzer(model_path)


@pytest.fixture()
def analyzer() -> StaticAnalyzer:
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

    analysis = await analyzer.analyze(b"%PDF-1.7")

    assert analysis.status == "completed"
    assert analysis.risk_score == 95
    assert analysis.tags == [
        "high_entropy",
        "has_javascript",
        "suspicious_js",
        "has_launch_action",
        "known_malware",
    ]


async def test_analyze_high_risk_band(analyzer: StaticAnalyzer) -> None:
    _set_session(analyzer, ["label", [[0.2, 0.8]]])
    _set_features(analyzer, {"entropy": 3.0})

    analysis = await analyzer.analyze(b"%PDF-1.7")

    assert analysis.risk_score == 80
    assert analysis.tags == ["high_risk"]


async def test_analyze_low_score_carries_no_risk_band_tag(analyzer: StaticAnalyzer) -> None:
    _set_session(analyzer, ["label", [[0.98, 0.02]]])
    _set_features(analyzer, {"entropy": 1.0})

    analysis = await analyzer.analyze(b"%PDF-1.7")

    assert analysis.risk_score == 2
    assert analysis.tags == []


async def test_analyze_raises_on_malformed_model_output(analyzer: StaticAnalyzer) -> None:
    _set_session(analyzer, [123])
    _set_features(analyzer, {"entropy": 1.0})

    with pytest.raises(ModelOutputError):
        await analyzer.analyze(b"%PDF-1.7")


def test_malicious_probability_raises_on_non_numeric_output() -> None:
    with pytest.raises(ModelOutputError):
        _malicious_probability(["label", [["not-a-number", "nope"]]])


async def test_analyze_abstains_on_non_pdf_bytes(analyzer: StaticAnalyzer) -> None:
    _set_session(analyzer, ["label", [[0.05, 0.95]]])
    _set_features(analyzer, {})

    analysis = await analyzer.analyze(b"MZ\x90\x00 not a pdf")

    assert analysis.status == "unsupported_file_type"
    assert analysis.risk_score == 0
    assert analysis.tags == ["unsupported_file_type"]


def test_abstention_carries_status_as_its_only_tag() -> None:
    analysis = abstention("analysis_failed")

    assert analysis.status == "analysis_failed"
    assert analysis.risk_score == 0
    assert analysis.tags == ["analysis_failed"]


class TestFeatureOrderValidation:
    def _write_metadata(self, tmp_path: Path, feature_order: list[str]) -> str:
        model_path = tmp_path / "model.onnx"
        (tmp_path / "model.metadata.json").write_text(json.dumps({"feature_order": feature_order}))
        return str(model_path)

    def test_matching_prefix_is_accepted(self, tmp_path: Path) -> None:
        model_path = self._write_metadata(tmp_path, FEATURE_ORDER[:12])
        validate_feature_order(model_path, 12)

    def test_reordered_features_are_rejected(self, tmp_path: Path) -> None:
        reordered = [FEATURE_ORDER[1], FEATURE_ORDER[0], *FEATURE_ORDER[2:12]]
        model_path = self._write_metadata(tmp_path, reordered)

        with pytest.raises(FeatureOrderMismatch):
            validate_feature_order(model_path, 12)

    def test_absent_sidecar_is_accepted(self, tmp_path: Path) -> None:
        validate_feature_order(str(tmp_path / "model.onnx"), len(FEATURE_ORDER))

    def test_analyzer_refuses_to_start_on_mismatch(self, tmp_path: Path) -> None:
        model_path = self._write_metadata(tmp_path, list(reversed(FEATURE_ORDER)))

        with pytest.raises(FeatureOrderMismatch):
            _build_analyzer(model_path, [None, len(FEATURE_ORDER)])


class TestResolveNFeatures:
    def test_concrete_feature_dim_from_model(self) -> None:
        analyzer = _build_analyzer("dummy.onnx", [None, 12])
        assert analyzer.n_features == 12

    def test_dynamic_feature_dim_falls_back(self) -> None:
        analyzer = _build_analyzer("dummy.onnx", [None, "dyn"])
        assert analyzer.n_features == len(FEATURE_ORDER)

    def test_short_shape_falls_back(self) -> None:
        analyzer = _build_analyzer("dummy.onnx", [16])
        assert analyzer.n_features == len(FEATURE_ORDER)

    def test_non_sequence_shape_falls_back(self) -> None:
        analyzer = _build_analyzer("dummy.onnx", MagicMock())
        assert analyzer.n_features == len(FEATURE_ORDER)


class TestThresholdMetadata:
    def _analyzer_with_metadata(self, tmp_path: Path, metadata: dict | None) -> StaticAnalyzer:
        model_path = tmp_path / "model.onnx"
        if metadata is not None:
            (tmp_path / "model.metadata.json").write_text(json.dumps(metadata))
        return _build_analyzer(str(model_path), [None, len(FEATURE_ORDER)])

    def test_no_sidecar_threshold_is_none(self, tmp_path: Path) -> None:
        analyzer = self._analyzer_with_metadata(tmp_path, None)
        assert analyzer.threshold is None

    def test_threshold_loaded_from_sidecar(self, tmp_path: Path) -> None:
        analyzer = self._analyzer_with_metadata(tmp_path, {"threshold": 0.83})
        assert analyzer.threshold == 0.83

    def test_null_threshold_is_none(self, tmp_path: Path) -> None:
        analyzer = self._analyzer_with_metadata(tmp_path, {"threshold": None})
        assert analyzer.threshold is None


class TestCalibration:
    def test_legacy_scaling_when_no_threshold(self) -> None:
        assert calibrate_score(0.5, None) == 50

    def test_legacy_scaling_when_threshold_degenerate(self) -> None:
        assert calibrate_score(0.5, 1.0) == 50

    def test_benign_side_maps_below_block_boundary(self) -> None:
        assert calibrate_score(0.4, 0.8) == 45

    def test_threshold_boundary_triggers_block(self) -> None:
        score = calibrate_score(0.8, 0.8)
        assert score == 91
        assert score > 90

    def test_max_proba_maps_to_100(self) -> None:
        assert calibrate_score(1.0, 0.8) == 100
