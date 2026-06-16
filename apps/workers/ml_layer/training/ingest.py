"""Dataset ingestion: load PDF files and extract features into a DataFrame.

Supported input formats
-----------------------
1. Directory layout::

       dataset_dir/
           malicious/   ← PDF files labeled 1
           benign/      ← PDF files labeled 0

2. CSV file with columns ``path`` (absolute or relative) and ``label`` (0 or 1).

The returned DataFrame has columns matching ``FEATURE_ORDER`` plus ``"label"``.
Files that cannot be parsed are logged and skipped.
"""

from __future__ import annotations

import csv
import logging
import signal
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd

from ml_layer.features.pdf import FEATURE_ORDER, PDFFeatureExtractor

logger = logging.getLogger(__name__)

# Per-file extraction timeout (seconds). With size caps in the extractor
# (1 MB entropy sample, 512 KB stream body cap, 3K BFS object limit) any
# legitimate PDF should finish in well under 5 s. 10 s is a generous safety net.
_FILE_TIMEOUT_S = 10

# Log a progress line after processing this many files.
_PROGRESS_EVERY = 500


def _timeout_handler(signum: int, frame: object) -> None:  # noqa: ARG001
    raise TimeoutError("PDF feature extraction timed out")


def _extract_one(path: str, label: int) -> Optional[dict[str, float | int]]:
    """Worker function executed in a subprocess.

    Uses SIGALRM to enforce a hard per-file timeout so that pathological PDFs
    (those that cause libqpdf to spin) cannot block the whole worker forever.
    """
    # Silence pikepdf's internal C-level noise (corrupt page trees, etc.) in
    # worker processes — the pipeline log is already noisy enough.
    logging.getLogger("pikepdf._core").setLevel(logging.CRITICAL)

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(_FILE_TIMEOUT_S)
    try:
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            warnings.warn(f"Cannot read {path}: {exc}", stacklevel=2)
            return None

        extractor = PDFFeatureExtractor()
        features = extractor.extract(data)

        # Drop the parse_error side-channel key — it's not in FEATURE_ORDER.
        features.pop("pdf_parse_error", None)

        # Ensure every FEATURE_ORDER key is present (fills zeros for missing ones).
        row: dict[str, float | int] = {k: features.get(k, 0.0) for k in FEATURE_ORDER}
        row["label"] = label
        return row
    finally:
        signal.alarm(0)  # Always cancel the alarm before returning.


def _collect_paths_from_dir(dataset_dir: Path) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    for label_name, label_value in [("malicious", 1), ("benign", 0)]:
        subdir = dataset_dir / label_name
        if not subdir.is_dir():
            logger.warning("Subdirectory not found, skipping: %s", subdir)
            continue
        # Accept both *.pdf and extension-less files (hash-named samples from
        # malware repositories such as MalwareBazaar / Contagio).
        for candidate in subdir.iterdir():
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() == ".pdf" or candidate.suffix == "":
                pairs.append((str(candidate), label_value))
    return pairs


def _collect_paths_from_csv(csv_path: Path) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pairs.append((row["path"], int(row["label"])))
    return pairs


def load_dataset(source: str, max_workers: int = 4) -> pd.DataFrame:
    """Load a labeled PDF dataset and extract features.

    Parameters
    ----------
    source:
        Path to either a directory (``malicious/`` + ``benign/`` layout)
        or a CSV file (``path``, ``label`` columns).
    max_workers:
        Number of parallel processes for feature extraction.

    Returns
    -------
    pd.DataFrame
        One row per successfully parsed file. Columns: ``FEATURE_ORDER`` + ``["label"]``.
    """
    p = Path(source)

    if p.is_dir():
        pairs = _collect_paths_from_dir(p)
    elif p.is_file() and p.suffix.lower() == ".csv":
        pairs = _collect_paths_from_csv(p)
    else:
        raise ValueError(f"source must be a directory or a .csv file, got: {source!r}")

    if not pairs:
        logger.warning("No files found in dataset source: %s", source)
        return pd.DataFrame(columns=FEATURE_ORDER + ["label"])

    total = len(pairs)
    logger.info(
        "Collected %d files — starting feature extraction with %d workers", total, max_workers
    )

    rows: list[dict[str, float | int]] = []
    skipped = 0
    done = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_extract_one, path, label): path for path, label in pairs}
        for future in as_completed(futures):
            path = futures[future]
            done += 1
            try:
                result = future.result(timeout=_FILE_TIMEOUT_S + 5)
            except TimeoutError:
                logger.warning("Timeout (>%ds) extracting %s — skipping", _FILE_TIMEOUT_S, path)
                skipped += 1
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to extract features from %s: %s", path, exc)
                skipped += 1
                continue

            if result is not None:
                rows.append(result)
            else:
                skipped += 1

            if done % _PROGRESS_EVERY == 0 or done == total:
                logger.info(
                    "Progress: %d / %d files processed (%.1f%%) — %d skipped so far",
                    done,
                    total,
                    100.0 * done / total,
                    skipped,
                )

    df = pd.DataFrame(rows, columns=FEATURE_ORDER + ["label"])
    logger.info(
        "Ingestion complete: %d rows loaded, %d files skipped (total %d)",
        len(df),
        skipped,
        total,
    )
    return df
