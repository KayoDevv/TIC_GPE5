"""Offline evaluation of a trained model, focused on the false-positive rate.

Reports the FPR on benign files and especially on hard-negative benign PDFs
(benign files carrying malicious-looking structure), plus malicious recall. Each
file is scored with the exact production calibration so the numbers match what
the Verdict Layer would see.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:  # pragma: no branch
    sys.path.insert(0, str(_SRC))  # pragma: no cover

from ml_layer.analyzer import calibrate_score, load_threshold  # noqa: E402
from ml_layer.features.pdf import FEATURE_ORDER  # noqa: E402
from training.ingest import load_dataset  # noqa: E402
from training.train import _deduplicate  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_HARD_NEGATIVE_FEATURES = [
    "pdf_has_javascript",
    "pdf_has_openaction",
    "pdf_has_auto_action",
    "pdf_has_launch",
    "pdf_has_embedded_file",
    "pdf_has_acroform",
    "pdf_has_xfa",
]

_BLOCK_SCORE = 90
_PERCENT = 100
_FALSE_POSITIVE_COLUMNS = ["sha256", "risk_score", "label", *_HARD_NEGATIVE_FEATURES]


def _malicious_proba(session: ort.InferenceSession, input_name: str, X: np.ndarray) -> np.ndarray:
    proba_out = session.run(None, {input_name: X})[1]
    probas: list[float] = []
    for row in proba_out:
        try:
            probas.append(float(row[1]))
        except (TypeError, KeyError, IndexError):
            probas.append(float(row[-1]))
    return np.array(probas)


def _hard_negative_mask(df: pd.DataFrame) -> np.ndarray:
    present = [f for f in _HARD_NEGATIVE_FEATURES if f in df.columns]
    return (df[present] > 0).any(axis=1).to_numpy()


def _model_feature_count(session: ort.InferenceSession) -> int:
    shape = session.get_inputs()[0].shape
    dim = shape[1] if isinstance(shape, (list, tuple)) and len(shape) > 1 else None
    return dim if isinstance(dim, int) else len(FEATURE_ORDER)


def _rate(numerator: np.ndarray, denominator: np.ndarray) -> float:
    den = int(denominator.sum())
    return int((numerator & denominator).sum()) / den if den else 0.0


def _build_metrics(df: pd.DataFrame, threshold: float | None) -> dict[str, float | int | None]:
    blocked = df["risk_score"].to_numpy() > _BLOCK_SCORE
    y = df["label"].to_numpy()
    benign = y == 0
    malicious = y == 1
    hard = _hard_negative_mask(df) & benign
    return {
        "n_total": int(len(df)),
        "n_benign": int(benign.sum()),
        "n_malicious": int(malicious.sum()),
        "n_hard_negative_benign": int(hard.sum()),
        "threshold": threshold,
        "fpr": _rate(blocked, benign),
        "fpr_hard_negatives": _rate(blocked, hard),
        "recall": _rate(blocked, malicious),
    }


def _log_metrics(metrics: dict[str, float | int | None]) -> None:
    logger.info(
        "Evaluated %d files (%d benign, %d malicious)",
        metrics["n_total"],
        metrics["n_benign"],
        metrics["n_malicious"],
    )
    logger.info("Overall FPR:            %.3f%% (target < 0.5%%)", metrics["fpr"] * _PERCENT)
    logger.info(
        "FPR on hard-neg benign: %.3f%% (%d hard-negative benign files)",
        metrics["fpr_hard_negatives"] * _PERCENT,
        metrics["n_hard_negative_benign"],
    )
    logger.info("Malicious recall:       %.3f%%", metrics["recall"] * _PERCENT)


def _write_false_positives(df: pd.DataFrame, output_csv: str) -> None:
    blocked = df["risk_score"].to_numpy() > _BLOCK_SCORE
    benign = df["label"].to_numpy() == 0
    false_positives = df[benign & blocked].sort_values("risk_score", ascending=False)
    columns = [c for c in _FALSE_POSITIVE_COLUMNS if c in false_positives.columns]
    false_positives[columns].to_csv(output_csv, index=False)
    logger.info("Wrote %d false-positive rows to %s", len(false_positives), output_csv)


def evaluate(
    dataset: str,
    model_path: str,
    cache_path: str | None = None,
    output_csv: str | None = None,
    *,
    dedup: bool = True,
) -> dict[str, float | int | None]:
    df = load_dataset(dataset, cache_path=cache_path)
    if dedup:
        df = _deduplicate(df)
    if df.empty:
        raise ValueError("dataset produced no rows to evaluate")

    session = ort.InferenceSession(model_path)
    input_name = session.get_inputs()[0].name
    n_features = _model_feature_count(session)
    X = df[FEATURE_ORDER[:n_features]].to_numpy(dtype=np.float32)
    threshold = load_threshold(model_path)

    proba = _malicious_proba(session, input_name, X)
    df = df.copy()
    df["risk_score"] = np.array([calibrate_score(p, threshold) for p in proba])

    metrics = _build_metrics(df, threshold)
    _log_metrics(metrics)
    if output_csv:
        _write_false_positives(df, output_csv)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="GPE-ETNA ML Layer model evaluation")
    parser.add_argument("--dataset", required=True, help="Dataset dir (malicious/benign) or CSV")
    parser.add_argument(
        "--model", default="models/ml_model_pdf.onnx", help="Path to the .onnx model"
    )
    parser.add_argument("--cache", default=None, help="Optional feature-cache CSV (fast re-runs)")
    parser.add_argument("--output", default=None, help="Optional CSV to dump false positives")
    parser.add_argument(
        "--no-dedup", action="store_true", help="Evaluate on raw rows without content dedup"
    )
    args = parser.parse_args()
    evaluate(
        args.dataset,
        args.model,
        cache_path=args.cache,
        output_csv=args.output,
        dedup=not args.no_dedup,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
