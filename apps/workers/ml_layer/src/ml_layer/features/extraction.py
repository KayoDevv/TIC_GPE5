"""Feature extraction under a hard per-file time budget.

pikepdf can spin for an unbounded time on a malformed or hostile PDF, so both
training ingestion and production inference extract through this one guard. The
alarm is armed in the calling process, which must therefore be the main thread
of that process -- production satisfies this by extracting inside a process-pool
worker rather than a thread.
"""

from __future__ import annotations

import signal
from types import FrameType

from ml_layer.features.pdf import PDFFeatureExtractor


class FeatureExtractionTimeout(TimeoutError):
    pass


def _raise_extraction_timeout(signum: int, frame: FrameType | None) -> None:  # noqa: ARG001
    raise FeatureExtractionTimeout("PDF feature extraction exceeded its time budget")


def extract_within_timeout(data: bytes, timeout_s: int) -> dict[str, float]:
    signal.signal(signal.SIGALRM, _raise_extraction_timeout)
    signal.alarm(timeout_s)
    try:
        return PDFFeatureExtractor().extract(data)
    finally:
        signal.alarm(0)
