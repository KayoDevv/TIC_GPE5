"""Export a trained LightGBM model to ONNX format.

The exported model accepts a float32 matrix of shape ``[N, len(FEATURE_ORDER)]``
and outputs class labels (``int64``) and class probabilities (``float32``).
A round-trip verification with ONNX Runtime is performed before writing the file.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import onnxruntime as ort
from lightgbm import LGBMClassifier
from onnxmltools import convert_lightgbm
from onnxmltools.convert.common.data_types import FloatTensorType

from ml_layer.features.pdf import FEATURE_ORDER

logger = logging.getLogger(__name__)


def export_to_onnx(model: LGBMClassifier, output_path: str) -> None:
    """Serialize *model* to ONNX and verify the round-trip with ONNX Runtime.

    Parameters
    ----------
    model:
        A fitted ``LGBMClassifier``.
    output_path:
        Destination path for the ``.onnx`` file.

    Raises
    ------
    RuntimeError
        If the ONNX Runtime round-trip verification fails.
    """
    n_features = len(FEATURE_ORDER)
    initial_type = [("float_input", FloatTensorType([None, n_features]))]

    logger.info("Converting LightGBM model to ONNX (%d features)…", n_features)
    onnx_model = convert_lightgbm(model, initial_types=initial_type)

    # Round-trip verification: run inference on a zero vector.
    session = ort.InferenceSession(onnx_model.SerializeToString())
    dummy = np.zeros((1, n_features), dtype=np.float32)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: dummy})

    if len(outputs) < 2:
        raise RuntimeError(
            f"ONNX model verification failed: expected ≥ 2 outputs, got {len(outputs)}"
        )

    proba = outputs[1][0]
    if len(proba) != 2:
        raise RuntimeError(
            f"ONNX model verification failed: expected 2 class probabilities, got {len(proba)}"
        )

    logger.info("Round-trip OK — dummy input proba: benign=%.4f malicious=%.4f", *proba.values())

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(onnx_model.SerializeToString())

    logger.info("Model saved to %s", output_path)
