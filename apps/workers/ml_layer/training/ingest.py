"""Dataset ingestion: load labelled PDFs and extract features into a DataFrame.

Accepts a ``malicious/`` + ``benign/`` directory layout or a CSV of
``path,label`` rows. Output columns are ``FEATURE_ORDER`` plus ``label`` and
``sha256``; unreadable/pathological files are logged and skipped. An optional
SHA-256-keyed CSV cache lets repeat runs skip pikepdf re-parsing.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import signal
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd

from ml_layer.features.pdf import FEATURE_ORDER, PDFFeatureExtractor

logger = logging.getLogger(__name__)

# A per-file hard timeout guards against PDFs that make libqpdf spin; the result
# wait adds a margin over it. Progress is logged every N files.
_FILE_TIMEOUT_S = 10
_RESULT_TIMEOUT_MARGIN_S = 5
_PROGRESS_EVERY = 500
_HASH_CHUNK_BYTES = 1 << 16


def _timeout_handler(signum: int, frame: object) -> None:  # noqa: ARG001
    raise TimeoutError("PDF feature extraction timed out")


def _extract_one(path: str, label: int) -> Optional[dict[str, float | int | str]]:
    logging.getLogger("pikepdf._core").setLevel(logging.CRITICAL)

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(_FILE_TIMEOUT_S)
    try:
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            warnings.warn(f"Cannot read {path}: {exc}", stacklevel=2)
            return None

        features = PDFFeatureExtractor().extract(data)
        row: dict[str, float | int | str] = {k: features.get(k, 0.0) for k in FEATURE_ORDER}
        row["label"] = label
        row["sha256"] = hashlib.sha256(data).hexdigest()
        return row
    finally:
        signal.alarm(0)


def _collect_paths_from_dir(dataset_dir: Path) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    for label_name, label_value in [("malicious", 1), ("benign", 0)]:
        subdir = dataset_dir / label_name
        if not subdir.is_dir():
            logger.warning("Subdirectory not found, skipping: %s", subdir)
            continue
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


def _file_sha256(path: str) -> Optional[str]:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _load_cache(cache_path: str) -> dict[str, dict[str, float]]:
    p = Path(cache_path)
    if not p.exists():
        return {}
    cached = pd.read_csv(p, dtype={"sha256": str})
    if any(col not in cached.columns for col in FEATURE_ORDER):
        logger.info("Feature cache schema is stale (feature set changed) — rebuilding it")
        return {}
    cache: dict[str, dict[str, float]] = {}
    for record in cached.to_dict(orient="records"):
        cache[str(record["sha256"])] = {k: float(record[k]) for k in FEATURE_ORDER}
    return cache


def _save_cache(cache_path: str, cache: dict[str, dict[str, float]]) -> None:
    records = [{"sha256": sha, **feats} for sha, feats in cache.items()]
    df = pd.DataFrame(records, columns=["sha256", *FEATURE_ORDER])
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)


def _log_progress(done: int, total: int, skipped: int) -> None:
    if done % _PROGRESS_EVERY == 0 or done == total:
        logger.info(
            "Progress: %d / %d files processed (%.1f%%) — %d skipped so far",
            done,
            total,
            100.0 * done / total,
            skipped,
        )


def _extract_pairs(
    pairs: list[tuple[str, int]], max_workers: int
) -> tuple[list[tuple[str, dict[str, float | int | str]]], int]:
    total = len(pairs)
    path_rows: list[tuple[str, dict[str, float | int | str]]] = []
    skipped = 0
    done = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_extract_one, path, label): path for path, label in pairs}
        for future in as_completed(futures):
            path = futures[future]
            done += 1
            try:
                result = future.result(timeout=_FILE_TIMEOUT_S + _RESULT_TIMEOUT_MARGIN_S)
            except TimeoutError:
                logger.warning("Timeout (>%ds) extracting %s — skipping", _FILE_TIMEOUT_S, path)
                skipped += 1
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to extract features from %s: %s", path, exc)
                skipped += 1
                continue

            if result is not None:
                path_rows.append((path, result))
            else:
                skipped += 1

            _log_progress(done, total, skipped)
    return path_rows, skipped


def _extract_with_cache(
    pairs: list[tuple[str, int]], max_workers: int, cache_path: str
) -> tuple[list[dict[str, float | int | str]], int]:
    cache = _load_cache(cache_path)
    rows: list[dict[str, float | int | str]] = []
    misses: list[tuple[str, int]] = []
    path_to_sha: dict[str, str] = {}

    for path, label in pairs:
        sha = _file_sha256(path)
        if sha is not None and sha in cache:
            rows.append({**cache[sha], "label": label, "sha256": sha})
        else:
            misses.append((path, label))
            if sha is not None:
                path_to_sha[path] = sha

    logger.info("Feature cache: %d hits, %d misses", len(rows), len(misses))

    skipped = 0
    if misses:
        path_rows, skipped = _extract_pairs(misses, max_workers)
        for path, row in path_rows:
            rows.append(row)
            sha = path_to_sha.get(path)
            if sha is not None:
                cache[sha] = {k: float(row[k]) for k in FEATURE_ORDER}
        _save_cache(cache_path, cache)

    return rows, skipped


def load_dataset(
    source: str, max_workers: int = 4, cache_path: Optional[str] = None
) -> pd.DataFrame:
    p = Path(source)

    if p.is_dir():
        pairs = _collect_paths_from_dir(p)
    elif p.is_file() and p.suffix.lower() == ".csv":
        pairs = _collect_paths_from_csv(p)
    else:
        raise ValueError(f"source must be a directory or a .csv file, got: {source!r}")

    if not pairs:
        logger.warning("No files found in dataset source: %s", source)
        return pd.DataFrame(columns=FEATURE_ORDER + ["label", "sha256"])

    total = len(pairs)
    logger.info(
        "Collected %d files — starting feature extraction with %d workers", total, max_workers
    )

    if cache_path is None:
        path_rows, skipped = _extract_pairs(pairs, max_workers)
        rows = [row for _path, row in path_rows]
    else:
        rows, skipped = _extract_with_cache(pairs, max_workers, cache_path)

    df = pd.DataFrame(rows, columns=FEATURE_ORDER + ["label", "sha256"])
    logger.info(
        "Ingestion complete: %d rows loaded, %d files skipped (total %d)",
        len(df),
        skipped,
        total,
    )
    return df
