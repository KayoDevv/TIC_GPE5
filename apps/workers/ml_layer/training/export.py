"""Export a trained LightGBM model to ONNX, with a threshold metadata sidecar.

The exported model takes a ``float32`` ``[N, len(FEATURE_ORDER)]`` matrix and
outputs labels plus class probabilities; a round-trip through ONNX Runtime
verifies it before writing. The sidecar carries the feature order and the tuned
threshold so inference calibrates scores instead of using hardcoded cut-offs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import onnxruntime as ort
from lightgbm import LGBMClassifier
from onnxmltools import convert_lightgbm
from onnxmltools.convert.common.data_types import FloatTensorType

from ml_layer.features.pdf import FEATURE_ORDER

logger = logging.getLogger(__name__)

_MIN_ONNX_OUTPUTS = 2
_BINARY_CLASS_COUNT = 2


def _write_metadata(output_path: str, threshold: float | None) -> None:
    metadata = {"feature_order": FEATURE_ORDER, "threshold": threshold}
    meta_path = Path(output_path).with_suffix(".metadata.json")
    meta_path.write_text(json.dumps(metadata, indent=2))
    logger.info("Metadata saved to %s (threshold=%s)", meta_path, threshold)


def _verify_roundtrip(onnx_bytes: bytes, n_features: int) -> None:
    session = ort.InferenceSession(onnx_bytes)
    dummy = np.zeros((1, n_features), dtype=np.float32)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: dummy})

    if len(outputs) < _MIN_ONNX_OUTPUTS:
        raise RuntimeError(
            f"ONNX model verification failed: expected >= 2 outputs, got {len(outputs)}"
        )

    proba = outputs[1][0]
    if len(proba) != _BINARY_CLASS_COUNT:
        raise RuntimeError(
            f"ONNX model verification failed: expected 2 class probabilities, got {len(proba)}"
        )

    logger.info("Round-trip OK - dummy input proba: benign=%.4f malicious=%.4f", *proba.values())


def export_to_onnx(model: LGBMClassifier, output_path: str, threshold: float | None = None) -> None:
    n_features = len(FEATURE_ORDER)
    initial_type = [("float_input", FloatTensorType([None, n_features]))]

    logger.info("Converting LightGBM model to ONNX (%d features)", n_features)
    onnx_model = convert_lightgbm(model, initial_types=initial_type)
    onnx_bytes = onnx_model.SerializeToString()

    _verify_roundtrip(onnx_bytes, n_features)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(onnx_bytes)

    logger.info("Model saved to %s", output_path)
    _write_metadata(output_path, threshold)
