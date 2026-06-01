"""Static probe — structural anomalies of the PDF file.

Detects exploit / obfuscation patterns that the keyword-based probes
(pdfid keywords, pdf_uri) do not see:

1. **%%EOF missing at the end**: intentionally malformed PDF (parser CVE).
2. **obj/endobj mismatch**: inconsistent structure; Adobe's tolerant parser
   still opens it but strict parsers crash.
3. **Abnormal object/page ratio**: dropper pattern (payload split across N objects).
4. **/Encrypt present**: encrypted PDF (very rare in legit, frequent in evasion).
5. **High /ObjStm**: objects packed into streams = obfuscation.

Uses `pdfid` (Didier Stevens) as a subprocess — already installed in the image.
pdfid parses the counts correctly (handles ObjStm) where a naive raw-byte regex
returns 0 on modern PDFs.

Signature: (Path) → HypothesisResult — same as the other static probes.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

log = logging.getLogger(__name__)

# Parse pdfid stat lines: "  obj    12" or "  /Page    3"
_STAT_RE = re.compile(
    r"^\s*(?P<key>obj|endobj|stream|endstream|/Page|/Encrypt|/ObjStm|trailer|startxref|xref)\s+(?P<count>\d+)",
    re.MULTILINE,
)

# Thresholds
_OBJ_RATIO_MEDIUM = 20
_OBJ_RATIO_HIGH   = 100
_OBJSTM_THRESHOLD = 5
_MIN_FILE_SIZE    = 1024
# Minimum obj/endobj delta to be a signal: a gap of 1-4 is benign noise
# (incremental PDF, arXiv papers) — calibrated on a 50 benign/100 malic corpus.
_OBJ_MISMATCH_MIN = 5


def _parse_pdfid_stats(pdf_path: Path) -> dict[str, int]:
    """Run pdfid and parse the counts (obj, endobj, /Page, /Encrypt, /ObjStm, ...)."""
    try:
        result = subprocess.run(
            ["pdfid", str(pdf_path)],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.warning("pdfid not found or timed out")
        return {}

    out = result.stdout + result.stderr
    stats: dict[str, int] = {}
    for m in _STAT_RE.finditer(out):
        stats[m.group("key")] = int(m.group("count"))
    return stats


def _qpdf_check(pdf_path: Path) -> tuple[int | None, str]:
    """Run `qpdf --check` to validate the PDF structure.

    Returns (returncode, output) where:
        - 0  = PDF OK
        - 2  = warnings (xref reconstruction, repairable structure)
        - 3  = errors (truly broken file)
        - None = qpdf not installed (silent fallback probe)
    """
    try:
        result = subprocess.run(
            ["qpdf", "--check", str(pdf_path)],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode, (result.stdout + result.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, ""


def evaluate_static(pdf_path: Path) -> HypothesisResult:
    """Detect the structural anomalies of a PDF.

    Signature: (Path) → HypothesisResult.
    """
    try:
        data = pdf_path.read_bytes()
    except OSError:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    if len(data) < _MIN_FILE_SIZE:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    stats = _parse_pdfid_stats(pdf_path)

    score = 0.0
    evidence: list[Evidence] = []

    # ─── 0. %PDF- magic missing in the first 1024 bytes ───
    # Catches disguised files (HTML/script renamed to .pdf, fake header).
    # Adobe/qpdf tolerate up to ~1024 bytes of garbage before the magic.
    if b"%PDF-" not in data[:1024]:
        score = max(score, 0.9)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.missing_pdf_magic",
            value=f"no %PDF- in first 1024 bytes (head: {data[:40]!r})",
        ))

    # ─── 1. %%EOF missing or not at the end of the file ───
    tail = data.rstrip()
    if not tail.endswith(b"%%EOF"):
        score = max(score, 0.7)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.no_eof_marker",
            value=f"file does not end with %%EOF (last 30 bytes: {data[-30:]!r})",
        ))

    # ─── 1-bis. qpdf --check: detects xref reconstruction, damaged files ───
    # The PDF may have %%EOF but an xref pointing to an invalid offset.
    # qpdf is tolerant like Adobe and reconstructs the xref — classic parser
    # exploit pattern. Return 2 = warnings, 3 = errors.
    rc, qpdf_out = _qpdf_check(pdf_path)
    if rc is not None and rc != 0:
        qlow = qpdf_out.lower()
        # Distinguish a LINEARIZATION artifact (web-optimized PDF: stale hint
        # table, shared object mismatch) — benign and frequent in legitimate
        # PDFs (qpdf reports it as an error but Adobe ignores it) — from REAL
        # structural damage (reconstructed xref, missing objects = exploit pattern).
        lin_only = (
            any(k in qlow for k in ("hint table", "linearization", "linearized", "shared object"))
            and not any(k in qlow for k in (
                "reconstruct", "cross-reference", "cross reference", "damaged",
                "can't find", "unable to find", "expected", "attempting to recover",
            ))
        )
        if lin_only:
            damage_score = 0.15        # suspicious band — not a malicious verdict
            field = "pdf_anomaly.qpdf_linearization_warn"
        else:
            damage_score = 0.8 if rc == 3 else 0.7
            field = "pdf_anomaly.qpdf_check_failed"
        score = max(score, damage_score)
        # Extract the first warning/error message for traceability
        first_warn = next(
            (line for line in qpdf_out.splitlines()
             if "WARNING" in line or "ERROR" in line or "damaged" in line),
            f"exit code {rc}",
        )
        evidence.append(Evidence(
            source="runtime_signals",
            field_path=field,
            value=f"exit={rc} : {first_warn[:150]}",
        ))

    # ─── 2-bis. stream / endstream mismatch (PDF malformed on the streams side) ───
    stream_count = stats.get("stream", 0)
    endstream_count = stats.get("endstream", 0)
    if stream_count > 0 and stream_count != endstream_count:
        # Calibrated on a mixed corpus: fires as much on benign as on malicious
        # (legitimate linearized/incremental PDFs) → suspicious band, not malicious.
        score = max(score, 0.15)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.stream_endstream_mismatch",
            value=f"stream={stream_count} endstream={endstream_count} (delta={abs(stream_count - endstream_count)})",
        ))

    # ─── 2. obj / endobj mismatch (malformed PDF) ───
    obj_count = stats.get("obj", 0)
    endobj_count = stats.get("endobj", 0)
    if obj_count > 0 and abs(obj_count - endobj_count) >= _OBJ_MISMATCH_MIN:
        score = max(score, 0.6)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.obj_endobj_mismatch",
            value=f"obj={obj_count} endobj={endobj_count} (delta={abs(obj_count - endobj_count)})",
        ))

    # ─── 3. Object / page ratio ───
    pages = stats.get("/Page", 0)
    if pages > 0 and obj_count >= 20:
        ratio = obj_count / pages
        if ratio >= _OBJ_RATIO_HIGH:
            score = max(score, 0.8)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_anomaly.obj_ratio_extreme",
                value=f"{obj_count} obj / {pages} pages = {ratio:.0f}:1 (>100)",
            ))
        elif ratio >= _OBJ_RATIO_MEDIUM:
            # Calibrated: fires on 5/7 benigns (RFCs/papers = many objects per
            # page, normal). Only the EXTREME ratio (>100) stays discriminating.
            score = max(score, 0.15)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_anomaly.obj_ratio_high",
                value=f"{obj_count} obj / {pages} pages = {ratio:.0f}:1 (>30)",
            ))

    # ─── 4. /Encrypt present (very rare in benign legit PDFs) ───
    encrypt = stats.get("/Encrypt", 0)
    if encrypt > 0:
        score = max(score, 0.5)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.encrypted",
            value=f"/Encrypt={encrypt} (encrypted PDF)",
        ))

    # ─── 5. High /ObjStm: packed objects (typical obfuscation) ───
    objstm = stats.get("/ObjStm", 0)
    if objstm >= _OBJSTM_THRESHOLD:
        # Calibrated (50 benign/100 malic): 3 benign / 5 malic → barely
        # discriminating. Modern PDFs (arXiv, LaTeX) use object streams as
        # standard. Suspicious band, not malicious.
        score = max(score, 0.15)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.many_objstm",
            value=f"/ObjStm={objstm} (>= {_OBJSTM_THRESHOLD}, packed objects)",
        ))

    # NOTE: the old cumulative boost "2+ anomalies → 0.85" has been REMOVED after
    # calibration on a mixed corpus. It amplified noise: a legitimate RFC easily
    # accumulates obj_ratio_high + stream_mismatch + qpdf_warning without being
    # malicious → false positive at 0.85. The genuinely strong anomalies
    # (missing_pdf_magic, no_eof, /Encrypt, obj_ratio_extreme) already carry a
    # high score individually via the MAX above — no boost needed.

    return HypothesisResult(
        value=score >= 0.3,
        score=round(score, 3),
        evidence=evidence,
    )
