"""Generic probe — embedded magic-byte detection.

Format-agnostic. Scans the file's raw bytes for executable-format or container
signatures, at offsets > 0 (magic bytes at the start of the file are normal;
it's the ones *in the middle* that betray a hidden payload).

Detected signatures:
    \\x7fELF       → Linux ELF (executable)          — score 1.0 (very suspicious)
    MZ           → Windows PE/DOS                    — score 1.0 (very suspicious)
    PK\\x03\\x04   → ZIP/JAR/DOCX/XLSX               — score 0.3 (often legitimate)
    \\x1f\\x8b     → gzip                              — score 0.3
    Rar!\\x1a\\x07 → RAR                              — score 0.3
    %PDF-       → PDF nested inside a PDF            — score 0.7 (rare and suspicious)

Signature: (Path) → HypothesisResult — same as pdf_static.evaluate_static
"""

from __future__ import annotations

from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

# (signature, score, label)
_SIGNATURES: tuple[tuple[bytes, float, str], ...] = (
    (b"\x7fELF",        1.0, "ELF"),
    (b"MZ\x90\x00",     1.0, "PE_DOS"),   # MZ + typical padding
    (b"PK\x03\x04",     0.3, "ZIP"),
    (b"\x1f\x8b\x08",   0.3, "gzip"),
    (b"Rar!\x1a\x07",   0.3, "RAR"),
    (b"%PDF-",          0.7, "nested_PDF"),
)

_MIN_OFFSET = 8   # ignore the file's own header
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB cap for the scan


def evaluate_static(file_path: Path) -> HypothesisResult:
    """Look for embedded magic bytes at offset > 0.

    Returns the highest score found (an embedded ELF is more discriminating
    than 5 ZIPs).
    """
    try:
        size = file_path.stat().st_size
        if size > _MAX_FILE_SIZE:
            # Scan just the first 50 MB to avoid blowing up
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
        # Search for the signature starting at _MIN_OFFSET to ignore
        # the file's own magic (e.g. %PDF- at the head of a legitimate PDF)
        offset = data.find(sig, _MIN_OFFSET)
        if offset == -1:
            continue
        # Keep the highest score
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
