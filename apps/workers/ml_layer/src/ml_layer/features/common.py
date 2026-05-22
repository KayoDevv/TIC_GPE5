"""Shared utilities: Shannon entropy and magic-byte file-type detection."""

import math
from typing import Literal


def shannon_entropy(data: bytes) -> float:
    """Return the Shannon entropy (bits) of *data*.

    Returns 0.0 for empty input.
    """
    if not data:
        return 0.0

    counts: dict[int, int] = {}
    for byte in data:
        counts[byte] = counts.get(byte, 0) + 1

    length = len(data)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def detect_file_type(data: bytes) -> Literal["pdf", "pe", "unknown"]:
    """Identify *data* by its magic bytes.

    Returns ``"pdf"``, ``"pe"``, or ``"unknown"``.
    """
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"MZ":
        return "pe"
    return "unknown"
