"""Sonde générique — détection de magic bytes embarqués.

Format-agnostique. Scanne les octets bruts du fichier à la recherche de
signatures de formats exécutables ou de conteneurs, à des offsets > 0
(les magic bytes en tête du fichier sont normaux, c'est ceux *au milieu*
qui trahissent un payload caché).

Signatures détectées :
    \\x7fELF       → Linux ELF (exécutable)        — score 1.0 (très suspect)
    MZ           → Windows PE/DOS                  — score 1.0 (très suspect)
    PK\\x03\\x04   → ZIP/JAR/DOCX/XLSX             — score 0.3 (souvent légitime)
    \\x1f\\x8b     → gzip                            — score 0.3
    Rar!\\x1a\\x07 → RAR                            — score 0.3
    %PDF-       → PDF imbriqué dans un PDF        — score 0.7 (rare et suspect)

Signature: (Path) → HypothesisResult — identique à pdf_static.evaluate_static
"""

from __future__ import annotations

from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

# (signature, score, label)
_SIGNATURES: tuple[tuple[bytes, float, str], ...] = (
    (b"\x7fELF",        1.0, "ELF"),
    (b"MZ\x90\x00",     1.0, "PE_DOS"),   # MZ + padding typique
    (b"PK\x03\x04",     0.3, "ZIP"),
    (b"\x1f\x8b\x08",   0.3, "gzip"),
    (b"Rar!\x1a\x07",   0.3, "RAR"),
    (b"%PDF-",          0.7, "nested_PDF"),
)

_MIN_OFFSET = 8   # ignore le header du fichier lui-même
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB cap pour le scan


def evaluate_static(file_path: Path) -> HypothesisResult:
    """Cherche des magic bytes embarqués à offset > 0.

    Retourne le score le plus élevé trouvé (un ELF embarqué est plus
    discriminant que 5 ZIPs).
    """
    try:
        size = file_path.stat().st_size
        if size > _MAX_FILE_SIZE:
            # On scanne juste les 50 premiers MB pour éviter d'exploser
            with file_path.open("rb") as f:
                data = f.read(_MAX_FILE_SIZE)
        else:
            data = file_path.read_bytes()
    except OSError:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    if len(data) < 16:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    score = 0.0
    evidence: list[Evidence] = []

    for sig, sig_score, label in _SIGNATURES:
        # On cherche la signature à partir de _MIN_OFFSET pour ignorer
        # le magic du fichier lui-même (ex: %PDF- en tête d'un PDF légitime)
        offset = data.find(sig, _MIN_OFFSET)
        if offset == -1:
            continue
        # Garde le score le plus élevé
        score = max(score, sig_score)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path=f"embedded_magic.{label}",
            value=f"{label} signature at offset={offset}",
        ))

    return HypothesisResult(
        value=score >= 0.5,
        score=round(score, 3),
        evidence=evidence,
    )
