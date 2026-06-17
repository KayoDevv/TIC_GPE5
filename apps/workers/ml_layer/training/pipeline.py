"""End-to-end training pipeline: ingest → train → export.

Usage
-----
::

    # Directory layout (malicious/ + benign/ subdirs):
    python -m training.pipeline --dataset ./data/pdfs --output ./models/ml_model_pdf.onnx

    # CSV (columns: path, label):
    python -m training.pipeline --dataset ./data/labels.csv --output ./models/ml_model_pdf.onnx
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure src/ is on sys.path so ml_layer is importable without installation.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:  # pragma: no branch
    sys.path.insert(0, str(_SRC))  # pragma: no cover

from training.export import export_to_onnx  # noqa: E402
from training.ingest import load_dataset  # noqa: E402
from training.train import train  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run(dataset: str, output: str, max_workers: int = 4) -> None:
    logger.info("=== Step 1/3: Ingesting dataset from %s", dataset)
    df = load_dataset(dataset, max_workers=max_workers)

    if df.empty:
        logger.error("Dataset is empty — aborting.")
        sys.exit(1)

    n_malicious = int((df["label"] == 1).sum())
    n_benign = int((df["label"] == 0).sum())
    logger.info("Dataset: %d malicious, %d benign", n_malicious, n_benign)

    logger.info("=== Step 2/3: Training LightGBM model")
    model, threshold = train(df)
    logger.info("Optimal decision threshold: %.4f", threshold)

    logger.info("=== Step 3/3: Exporting to ONNX → %s", output)
    export_to_onnx(model, output)

    logger.info("Done. Model ready at %s", output)


def main() -> None:
    parser = argparse.ArgumentParser(description="GPE-ETNA ML Layer — PDF model training pipeline")
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to dataset directory (malicious/benign layout) or CSV file",
    )
    parser.add_argument(
        "--output",
        default="models/ml_model_pdf.onnx",
        help="Destination path for the exported ONNX model (default: models/ml_model_pdf.onnx)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel processes for feature extraction (default: 4)",
    )
    args = parser.parse_args()
    run(args.dataset, args.output, max_workers=args.workers)


if __name__ == "__main__":  # pragma: no cover
    main()
