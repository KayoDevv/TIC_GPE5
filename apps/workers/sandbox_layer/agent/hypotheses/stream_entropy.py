"""Generic probe — hidden-payload detection via local entropy analysis.

Format-agnostic. Works on any file (PDF, ELF, DOCX, LNK...).

v2 principle: a normally-compressed PDF has *uniformly* high entropy
(zlib/Flate on every stream → ~7.9 everywhere). A file with a hidden
encrypted/obfuscated payload shows a *local anomaly* — an entropy peak above
lower-entropy content.

v1 only looked at `max_chunk_entropy` → fired on legitimate compressed PDFs
(98% FP on the benign RFC/arXiv corpus). v2 looks at the gap between the max
and the median of the chunks to distinguish "uniformly compressed" (normal)
from "localized peak" (suspicious).

v2 heuristic (scores kept in the "suspicious" band — see the calibration note below):
  - high_ratio > 0.7  (>70% of chunks at high entropy) → uniform legit compression, score 0
  - peak_gap > 1.5 AND max > 7.8 → score 0.20
  - peak_gap > 1.0 AND max > 7.5 → score 0.15
  - peak_gap > 0.5 AND max > 7.5 → score 0.10
  - otherwise → 0

Signature: (Path) → HypothesisResult — same as pdf_static.evaluate_static
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

_CHUNK_SIZE = 4096      # sliding window
_MIN_FILE_SIZE = 1024   # ignore trivial files
_HIGH_ENTROPY_THRESHOLD = 7.5  # bits/byte above which a chunk is "high"


def _shannon_entropy(data: bytes) -> float:
    """Shannon entropy over raw bytes, in bits/byte (0..8)."""
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum(
        (c / total) * math.log2(c / total)
        for c in counts.values()
    )


def evaluate_static(file_path: Path) -> HypothesisResult:
    """Analyze entropy by windows and return a discriminating score.

    Distinguishes uniform compression (legit) from a localized peak (suspicious).
    """
    try:
        data = file_path.read_bytes()
    except OSError:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    if len(data) < _MIN_FILE_SIZE:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # Entropy per window
    chunk_entropies: list[float] = []
    max_entropy = 0.0
    max_offset = 0
    for offset in range(0, len(data) - _CHUNK_SIZE, _CHUNK_SIZE):
        e = _shannon_entropy(data[offset:offset + _CHUNK_SIZE])
        chunk_entropies.append(e)
        if e > max_entropy:
            max_entropy = e
            max_offset = offset

    if len(chunk_entropies) < 4:
        # Too few chunks to compute a reliable median.
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # Discriminating stats
    median_entropy = statistics.median(chunk_entropies)
    high_chunks = sum(1 for e in chunk_entropies if e > _HIGH_ENTROPY_THRESHOLD)
    high_ratio = high_chunks / len(chunk_entropies)
    peak_gap = max_entropy - median_entropy

    # v2 heuristic: the signature of a hidden payload is a LOCALIZED peak,
    # not uniformly high entropy.
    # CALIBRATED (mixed corpus): even v2 (localized peak) fires on 5/7 benigns —
    # an RFC/paper has a compressed object (image, embedded source) that forms a
    # peak above the text, identical to a hidden payload. Low high_ratio + high
    # gap does NOT distinguish benign from malicious on PDF (tally: 5 benign / 5
    # malic). We keep entropy as a WEAK signal (suspicious band): useful as
    # evidence for the LLM, but never classifies as malicious on its own.
    if high_ratio > 0.7:
        # Compression uniforme (PDF zlib, archive, etc.) — pas d'anomalie locale.
        score = 0.0
    elif peak_gap > 1.5 and max_entropy > 7.8:
        score = 0.20
    elif peak_gap > 1.0 and max_entropy > 7.5:
        score = 0.15
    elif peak_gap > 0.5 and max_entropy > 7.5:
        score = 0.10
    else:
        score = 0.0

    evidence: list[Evidence] = []
    if score > 0.0:
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="stream_entropy.local_peak",
            value=(
                f"max={max_entropy:.2f} @offset={max_offset} "
                f"median={median_entropy:.2f} gap={peak_gap:.2f} "
                f"high_ratio={high_ratio:.2f}"
            ),
        ))

    return HypothesisResult(
        value=score >= 0.4,
        score=round(score, 3),
        evidence=evidence,
    )
