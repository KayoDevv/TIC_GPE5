"""Shared utilities: Shannon entropy and magic-byte file-type detection."""

from typing import Literal

import numpy as np


def shannon_entropy(data: bytes) -> float:
    """Return the Shannon entropy (bits) of *data*.

    Returns 0.0 for empty input.

    Vectorised with numpy: a per-byte histogram (``bincount``) instead of a
    pure-Python byte loop. The value is mathematically identical to the naive
    definition, but this is ~10x faster and keeps the ML Layer inside its
    500 ms SLA on large PDFs — the byte-frequency loop was the dominant cost
    (profiled: ~8 s of a 14 s extraction, spent scanning stream bodies).
    """
    if not data:
        return 0.0

    arr = np.frombuffer(data, dtype=np.uint8)
    counts = np.bincount(arr, minlength=256)
    probs = counts[counts > 0] / arr.size
    entropy = float(-np.sum(probs * np.log2(probs)))
    # Normalise a possible -0.0 (single-symbol input) to 0.0.
    return entropy + 0.0


def detect_file_type(data: bytes) -> Literal["pdf", "pe", "unknown"]:
    """Identify *data* by its magic bytes.

    Returns ``"pdf"``, ``"pe"``, or ``"unknown"``.
    """
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"MZ":
        return "pe"
    return "unknown"
