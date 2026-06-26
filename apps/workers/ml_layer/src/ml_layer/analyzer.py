import asyncio
from typing import Any

import numpy as np
import onnxruntime as ort

from ml_layer.features.pdf import FEATURE_ORDER, PDFFeatureExtractor


class StaticAnalyzer:
    def __init__(self, model_path: str) -> None:
        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.extractor = PDFFeatureExtractor()

    def _score(self, result: Any) -> int:
        """Map the ONNX output to a 0-100 risk score.

        The LightGBM→ONNX export returns ``result[1]`` as the per-class
        probabilities (``result[1][0][1]`` is the malicious probability).
        Any deviation in the output shape falls back to a neutral score of 0.
        """
        try:
            proba = float(result[1][0][1])
        except (IndexError, KeyError, TypeError, ValueError):
            return 0
        return int(proba * 100)

    async def analyze(self, data: bytes) -> tuple[int, list[str]]:
        """Extract features and run ONNX inference. Returns (risk_score, tags)."""
        # 1. Feature extraction (CPU intensive, run in thread).
        features = await asyncio.to_thread(self.extractor.extract, data)

        # 2. Prepare input in the canonical FEATURE_ORDER the model was trained on.
        X = np.array([[features[k] for k in FEATURE_ORDER]], dtype=np.float32)

        # 3. Inference (run in thread to not block the event loop).
        result = await asyncio.to_thread(self.session.run, None, {self.input_name: X})
        risk_score = self._score(result)

        tags: list[str] = []
        if features.get("entropy", 0) > 7.0:
            tags.append("high_entropy")
        if features.get("pdf_has_javascript", 0) > 0:
            tags.append("has_javascript")
        if features.get("pdf_suspicious_js_count", 0) > 5:
            tags.append("suspicious_js")
        if features.get("pdf_has_launch", 0) > 0:
            tags.append("has_launch_action")

        if risk_score > 90:
            tags.append("known_malware")
        elif risk_score > 70:
            tags.append("high_risk")

        return risk_score, tags
