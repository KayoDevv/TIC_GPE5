"""Static PDF analysis: ONNX inference plus threshold-calibrated risk scoring.

The tuned decision threshold lives in a sidecar next to the model; scores are
calibrated so ``risk_score > 90`` matches the Verdict Layer's block boundary.
``load_threshold`` and ``calibrate_score`` are shared with offline evaluation so
it scores files exactly as production does. A file the model cannot legitimately
score yields an abstention, never a zero score a consumer would read as benign.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from zt_shared.models.events import ML_ANALYSIS_COMPLETED, MlAnalysisStatus

from ml_layer.features.pdf import FEATURE_ORDER, PDFFeatureExtractor

_SCORE_SCALE = 100
_MAX_BENIGN_SCORE = 90.0
_MIN_MALICIOUS_SCORE = 91
_MALICIOUS_SCORE_SPAN = float(_SCORE_SCALE - _MIN_MALICIOUS_SCORE)

_HIGH_ENTROPY_THRESHOLD = 7.0
_SUSPICIOUS_JS_TAG_THRESHOLD = 5
_KNOWN_MALWARE_SCORE = 90
_HIGH_RISK_SCORE = 70

_PDF_MAGIC = b"%PDF"
_ABSTENTION_SCORE = 0


class ModelOutputError(RuntimeError):
    pass


class FeatureOrderMismatch(RuntimeError):
    pass


@dataclass(frozen=True)
class StaticAnalysis:
    risk_score: int
    tags: list[str]
    status: MlAnalysisStatus


def abstention(status: MlAnalysisStatus) -> StaticAnalysis:
    return StaticAnalysis(risk_score=_ABSTENTION_SCORE, tags=[status], status=status)


def _metadata_path(model_path: str) -> Path:
    return Path(model_path).with_suffix(".metadata.json")


def _read_metadata(model_path: str) -> dict[str, Any]:
    meta_path = _metadata_path(model_path)
    if not meta_path.exists():
        return {}
    metadata: dict[str, Any] = json.loads(meta_path.read_text())
    return metadata


def load_threshold(model_path: str) -> float | None:
    threshold = _read_metadata(model_path).get("threshold")
    return float(threshold) if threshold is not None else None


def validate_feature_order(model_path: str, n_features: int) -> None:
    declared = _read_metadata(model_path).get("feature_order")
    if declared is None:
        return
    expected = FEATURE_ORDER[:n_features]
    if list(declared) != expected:
        raise FeatureOrderMismatch(
            f"{model_path}: the sidecar feature_order does not match the code "
            f"FEATURE_ORDER, so the model would receive mis-mapped features"
        )


def calibrate_score(proba: float, threshold: float | None) -> int:
    if threshold is None or not 0.0 < threshold < 1.0:
        return int(proba * _SCORE_SCALE)
    if proba < threshold:
        return int(_MAX_BENIGN_SCORE * proba / threshold)
    malicious_span = _MALICIOUS_SCORE_SPAN * (proba - threshold) / (1.0 - threshold)
    return _MIN_MALICIOUS_SCORE + int(malicious_span)


def _malicious_probability(result: Any) -> float:
    try:
        return float(result[1][0][1])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ModelOutputError(f"unusable ONNX output: {exc}") from exc


def _build_tags(features: dict[str, float], risk_score: int) -> list[str]:
    tags: list[str] = []
    if features.get("entropy", 0) > _HIGH_ENTROPY_THRESHOLD:
        tags.append("high_entropy")
    if features.get("pdf_has_javascript", 0) > 0:
        tags.append("has_javascript")
    if features.get("pdf_suspicious_js_count", 0) > _SUSPICIOUS_JS_TAG_THRESHOLD:
        tags.append("suspicious_js")
    if features.get("pdf_has_launch", 0) > 0:
        tags.append("has_launch_action")

    if risk_score > _KNOWN_MALWARE_SCORE:
        tags.append("known_malware")
    elif risk_score > _HIGH_RISK_SCORE:
        tags.append("high_risk")

    return tags


class StaticAnalyzer:
    def __init__(self, model_path: str) -> None:
        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.n_features = self._resolve_n_features()
        self.threshold = load_threshold(model_path)
        self.extractor = PDFFeatureExtractor()
        validate_feature_order(model_path, self.n_features)

    def _resolve_n_features(self) -> int:
        shape = self.session.get_inputs()[0].shape
        feature_dim = shape[1] if isinstance(shape, (list, tuple)) and len(shape) > 1 else None
        return feature_dim if isinstance(feature_dim, int) else len(FEATURE_ORDER)

    async def _infer(self, features: dict[str, float]) -> int:
        model_features = [features[k] for k in FEATURE_ORDER[: self.n_features]]
        model_input = np.array([model_features], dtype=np.float32)
        result = await asyncio.to_thread(self.session.run, None, {self.input_name: model_input})
        return calibrate_score(_malicious_probability(result), self.threshold)

    async def analyze(self, data: bytes) -> StaticAnalysis:
        if not data.startswith(_PDF_MAGIC):
            return abstention("unsupported_file_type")

        features = await asyncio.to_thread(self.extractor.extract, data)
        risk_score = await self._infer(features)
        return StaticAnalysis(
            risk_score=risk_score,
            tags=_build_tags(features, risk_score),
            status=ML_ANALYSIS_COMPLETED,
        )
