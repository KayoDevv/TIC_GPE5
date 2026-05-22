"""Sonde générique — détection de payload caché via analyse d'entropie locale.

Format-agnostique. Marche sur n'importe quel fichier (PDF, ELF, DOCX, LNK...).

Principe v2 : un PDF normal compressé a une entropie *uniformément* élevée
(zlib/Flate sur tous les streams → ~7.9 partout). Un fichier avec un payload
chiffré/obfusqué caché montre une *anomalie locale* — un pic d'entropie au-dessus
d'un contenu plus bas.

La v1 ne regardait que `max_chunk_entropy` → fire sur PDFs compressés légitimes
(98% FP sur le corpus benign RFC/arXiv). La v2 regarde l'écart entre le max
et la médiane des chunks pour distinguer "uniformément compressé" (normal)
de "pic localisé" (suspect).

Heuristique v2 :
  - high_ratio > 0.7  (>70% des chunks à entropie élevée) → compression uniforme légit, score 0
  - peak_gap > 1.5    (pic dépassant la médiane de >1.5 bits) ET max > 7.8 → payload caché, score 0.8
  - peak_gap > 1.0    → suspect modéré, score 0.5
  - peak_gap > 0.5 ET max > 7.5 → faible signal, score 0.2
  - sinon → 0

Signature: (Path) → HypothesisResult — identique à pdf_static.evaluate_static
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

_CHUNK_SIZE = 4096      # fenêtre glissante
_MIN_FILE_SIZE = 1024   # ignore fichiers triviaux
_HIGH_ENTROPY_THRESHOLD = 7.5  # bits/byte au-dessus duquel un chunk est "haut"


def _shannon_entropy(data: bytes) -> float:
    """Entropie de Shannon sur des octets bruts, en bits/byte (0..8)."""
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum(
        (c / total) * math.log2(c / total)
        for c in counts.values()
    )


def evaluate_static(file_path: Path) -> HypothesisResult:
    """Analyse l'entropie par fenêtres et retourne un score discriminant.

    Distingue compression uniforme (légit) de pic localisé (suspect).
    """
    try:
        data = file_path.read_bytes()
    except OSError:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    if len(data) < _MIN_FILE_SIZE:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # Entropie par fenêtre
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
        # Trop peu de chunks pour calculer une médiane fiable.
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # Stats discriminantes
    median_entropy = statistics.median(chunk_entropies)
    high_chunks = sum(1 for e in chunk_entropies if e > _HIGH_ENTROPY_THRESHOLD)
    high_ratio = high_chunks / len(chunk_entropies)
    peak_gap = max_entropy - median_entropy

    # Heuristique v2 : la signature d'un payload caché c'est un PIC localisé,
    # pas une entropie uniformément élevée.
    # CALIBRÉ (corpus mixte) : même la v2 (pic localisé) fire sur 5/7 benigns —
    # un RFC/papier a un objet compressé (image, source embarquée) qui forme un
    # pic au-dessus du texte, identique à un payload caché. high_ratio bas + gap
    # élevé ne distingue PAS benign de malicious sur PDF (tally : 5 benign / 5
    # malic). On garde l'entropie comme signal FAIBLE (bande suspicious) : utile
    # comme evidence pour le LLM, mais ne classe jamais seul en malicious.
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
