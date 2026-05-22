"""Sonde statique — anomalies structurelles du fichier PDF.

Détecte les patterns d'exploit / d'obfuscation que les sondes keyword-based
(pdfid keywords, pdf_uri) ne voient pas :

1. **%%EOF absent en fin** : PDF malformé intentionnellement (CVE parser).
2. **obj/endobj mismatch** : structure incohérente, le parser tolérant Adobe
   ouvre quand même mais les parseurs strictes plantent.
3. **Ratio objets/pages anormal** : pattern dropper (payload éclaté en N objets).
4. **/Encrypt présent** : PDF chiffré (très rare en légit, fréquent en évasion).
5. **/ObjStm élevé** : objets packés dans des streams = obfuscation.

Utilise `pdfid` (Didier Stevens) en subprocess — déjà installé dans l'image.
pdfid parse les counts correctement (sait gérer les ObjStm) là où un regex
naïf sur bytes bruts retourne 0 sur les PDFs modernes.

Signature: (Path) → HypothesisResult — identique aux autres sondes statiques.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

log = logging.getLogger(__name__)

# Parser des lignes stats pdfid : "  obj    12" ou "  /Page    3"
_STAT_RE = re.compile(
    r"^\s*(?P<key>obj|endobj|stream|endstream|/Page|/Encrypt|/ObjStm|trailer|startxref|xref)\s+(?P<count>\d+)",
    re.MULTILINE,
)

# Seuils
_OBJ_RATIO_MEDIUM = 20
_OBJ_RATIO_HIGH   = 100
_OBJSTM_THRESHOLD = 5
_MIN_FILE_SIZE    = 1024
# Delta obj/endobj minimal pour être un signal : un écart de 1-4 est du bruit
# bénin (PDF incrémental, papiers arXiv) — calibré sur corpus 50 benign/100 malic.
_OBJ_MISMATCH_MIN = 5


def _parse_pdfid_stats(pdf_path: Path) -> dict[str, int]:
    """Lance pdfid et parse les counts (obj, endobj, /Page, /Encrypt, /ObjStm, ...)."""
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
    """Lance `qpdf --check` pour valider la structure du PDF.

    Returns (returncode, output) où :
        - 0  = PDF OK
        - 2  = warnings (xref reconstruction, structure réparable)
        - 3  = errors (fichier vraiment cassé)
        - None = qpdf non installé (sonde fallback silencieuse)
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
    """Détecte les anomalies structurelles d'un PDF.

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

    # ─── 0. Magic %PDF- absent dans les 1024 premiers octets ───
    # Catch les fichiers déguisés (HTML/script renommé en .pdf, fake header).
    # Adobe/qpdf tolèrent jusqu'à ~1024 bytes de garbage avant le magic.
    if b"%PDF-" not in data[:1024]:
        score = max(score, 0.9)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.missing_pdf_magic",
            value=f"no %PDF- in first 1024 bytes (head: {data[:40]!r})",
        ))

    # ─── 1. %%EOF absent ou non en fin de fichier ───
    tail = data.rstrip()
    if not tail.endswith(b"%%EOF"):
        score = max(score, 0.7)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.no_eof_marker",
            value=f"file does not end with %%EOF (last 30 bytes: {data[-30:]!r})",
        ))

    # ─── 1-bis. qpdf --check : détecte xref reconstruction, fichiers damaged ───
    # Le PDF peut avoir %%EOF mais une xref pointant vers un offset invalide.
    # qpdf est tolérant comme Adobe et reconstruit la xref — pattern exploit
    # parser CVE classique. Retour 2 = warnings, 3 = errors.
    rc, qpdf_out = _qpdf_check(pdf_path)
    if rc is not None and rc != 0:
        qlow = qpdf_out.lower()
        # Distinguer un artefact de LINÉARISATION (PDF web-optimisé : hint table
        # périmée, shared object mismatch) — bénin et fréquent dans les PDFs
        # légitimes (qpdf le remonte en erreur mais Adobe l'ignore) — d'un VRAI
        # dégât structurel (xref reconstruite, objets manquants = pattern exploit).
        lin_only = (
            any(k in qlow for k in ("hint table", "linearization", "linearized", "shared object"))
            and not any(k in qlow for k in (
                "reconstruct", "cross-reference", "cross reference", "damaged",
                "can't find", "unable to find", "expected", "attempting to recover",
            ))
        )
        if lin_only:
            damage_score = 0.15        # bande suspicious — pas un verdict malicious
            field = "pdf_anomaly.qpdf_linearization_warn"
        else:
            damage_score = 0.8 if rc == 3 else 0.7
            field = "pdf_anomaly.qpdf_check_failed"
        score = max(score, damage_score)
        # Extrait le premier message de warning/error pour traçabilité
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

    # ─── 2-bis. stream / endstream mismatch (PDF malformé côté streams) ───
    stream_count = stats.get("stream", 0)
    endstream_count = stats.get("endstream", 0)
    if stream_count > 0 and stream_count != endstream_count:
        # Calibré sur corpus mixte : fire autant sur benign que malicious
        # (PDFs linéarisés/incrémentaux légitimes) → bande suspicious, pas malicious.
        score = max(score, 0.15)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.stream_endstream_mismatch",
            value=f"stream={stream_count} endstream={endstream_count} (delta={abs(stream_count - endstream_count)})",
        ))

    # ─── 2. obj / endobj mismatch (PDF malformé) ───
    obj_count = stats.get("obj", 0)
    endobj_count = stats.get("endobj", 0)
    if obj_count > 0 and abs(obj_count - endobj_count) >= _OBJ_MISMATCH_MIN:
        score = max(score, 0.6)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.obj_endobj_mismatch",
            value=f"obj={obj_count} endobj={endobj_count} (delta={abs(obj_count - endobj_count)})",
        ))

    # ─── 3. Ratio objets / pages ───
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
            # Calibré : fire sur 5/7 benigns (RFCs/papiers = beaucoup d'objets
            # par page, normal). Seul le ratio EXTREME (>100) reste discriminant.
            score = max(score, 0.15)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_anomaly.obj_ratio_high",
                value=f"{obj_count} obj / {pages} pages = {ratio:.0f}:1 (>30)",
            ))

    # ─── 4. /Encrypt présent (très rare en PDF légit benin) ───
    encrypt = stats.get("/Encrypt", 0)
    if encrypt > 0:
        score = max(score, 0.5)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.encrypted",
            value=f"/Encrypt={encrypt} (PDF chiffré)",
        ))

    # ─── 5. /ObjStm élevé : objets packés (obfuscation typique) ───
    objstm = stats.get("/ObjStm", 0)
    if objstm >= _OBJSTM_THRESHOLD:
        # Calibré (50 benign/100 malic) : 3 benign / 5 malic → quasi non
        # discriminant. Les PDFs modernes (arXiv, LaTeX) utilisent les object
        # streams en standard. Bande suspicious, pas malicious.
        score = max(score, 0.15)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_anomaly.many_objstm",
            value=f"/ObjStm={objstm} (>= {_OBJSTM_THRESHOLD}, objets packés)",
        ))

    # NOTE : l'ancien boost cumulatif "2+ anomalies → 0.85" a été RETIRÉ après
    # calibration sur corpus mixte. Il amplifiait le bruit : un RFC légitime
    # cumule facilement obj_ratio_high + stream_mismatch + qpdf_warning sans
    # être malveillant → faux positif à 0.85. Les vraies anomalies fortes
    # (missing_pdf_magic, no_eof, /Encrypt, obj_ratio_extreme) portent déjà un
    # score élevé individuellement via le MAX ci-dessus — pas besoin de boost.

    return HypothesisResult(
        value=score >= 0.3,
        score=round(score, 3),
        evidence=evidence,
    )
