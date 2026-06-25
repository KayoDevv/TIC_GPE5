"""Static PDF hypothesis — structure analysis via pdfid (Didier Stevens).

Combinatorial rules, not per-keyword weights: a lone keyword is ambiguous
(`/OpenAction`, `/JS`, `/AcroForm` are common in benign PDFs), but combinations
discriminate — `/JS`+`/OpenAction` = auto-exec malware, `/EmbeddedFile`+`/Launch`
= dropper, `/JBIG2Decode`+`/Colors` = CVE-2009-0658. Weight 0.30 (MAX upstream).
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

log = logging.getLogger(__name__)

# Keywords tracked by pdfid — used in the combinatorial rules below.
_TRACKED_KEYWORDS = (
    "/JS", "/JavaScript",
    "/Launch", "/AA", "/OpenAction",
    "/EmbeddedFile", "/RichMedia",
    "/AcroForm", "/XFA",
    "/JBIG2Decode", "/Colors",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PDFID_TIMEOUT_S = 30

# Sentinel: the probe TIMED OUT (the sample defeated the tool) — distinct from
# "" (tool absent). A timeout is the sample's doing and must surface as an
# indicator, never be silently converted into "no signal" (cf. the fb87d8a7
# miss: pdfid + qpdf all choked on a pathological PDF -> score 0.0 -> benign).
_PROBE_TIMEOUT = None


def _run_pdfid(pdf_path: Path) -> str | None:
    """Run pdfid. Returns its output, '' if the tool is absent, or
    _PROBE_TIMEOUT (None) if the sample made it hang past the timeout."""
    try:
        result = subprocess.run(
            ["pdfid", str(pdf_path)],
            capture_output=True, text=True, timeout=_PDFID_TIMEOUT_S,
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        log.warning("pdfid not found — static PDF analysis unavailable")
        return ""
    except subprocess.TimeoutExpired:
        log.warning("pdfid timed out on %s", pdf_path.name)
        return _PROBE_TIMEOUT


def _parse_pdfid_output(output: str) -> dict[str, int]:
    """Extract the keyword→count counters from pdfid's output."""
    counts: dict[str, int] = {}
    for keyword in _TRACKED_KEYWORDS:
        pattern = re.compile(
            rf"^\s*{re.escape(keyword)}\s+([0-9]+)", re.MULTILINE
        )
        match = pattern.search(output)
        if match:
            counts[keyword] = int(match.group(1))
    return counts


# ---------------------------------------------------------------------------
# Combinatorial rules
# ---------------------------------------------------------------------------

def _apply_rules(counts: dict[str, int]) -> tuple[float, list[tuple[str, float, str]]]:
    """Apply the combinatorial rules, return (max_score, [rules_fired]).

    Each rule = (name, score, mitre_technique). We keep the MAX of the scores
    (not the sum) — a single strong pattern is enough to classify as malicious.
    """
    js          = counts.get("/JS", 0) > 0 or counts.get("/JavaScript", 0) > 0
    auto_action = counts.get("/OpenAction", 0) > 0 or counts.get("/AA", 0) > 0
    launch      = counts.get("/Launch", 0) > 0
    embedded    = counts.get("/EmbeddedFile", 0) > 0
    jbig2       = counts.get("/JBIG2Decode", 0) > 0
    colors      = counts.get("/Colors", 0) > 0
    xfa         = counts.get("/XFA", 0) > 0
    rich        = counts.get("/RichMedia", 0) > 0

    rules: list[tuple[str, float, str]] = []

    # --- Strong solos (rare in legit) ---
    if launch:
        rules.append(("launch_action", 0.70, "T1204.002"))

    if jbig2 and colors:
        rules.append(("jbig2_colors_overflow", 0.70, "T1027"))   # CVE-2009-0658

    # --- Combinaisons JS ---
    if js and auto_action:
        rules.append(("js_auto_triggered", 0.80, "T1059.007"))   # execution without interaction — discriminating (0 benign)
    elif js:
        # Calibrated: PASSIVE JS (no /OpenAction) exists in legitimate docs
        # (navigation, forms) → moderate signal, not a verdict.
        rules.append(("js_embedded", 0.25, "T1059.007"))

    # --- Dropper patterns ---
    # CALIBRATED: /EmbeddedFile + PASSIVE /JS is NOT a dropper (an RFC embeds its
    # XML source and has navigation JS → false positive at 0.9, seen on rfc9110).
    # A real dropper requires /Launch (almost always malicious) OR AUTO-EXECUTED
    # JS (/OpenAction|/AA) that launches the payload without interaction.
    if embedded and launch:
        rules.append(("dropper_with_payload", 0.90, "T1027"))
    elif embedded and js and auto_action:
        rules.append(("dropper_auto_exec", 0.90, "T1027"))
    elif embedded:
        # /EmbeddedFile alone: 4/7 benigns trigger it → suspicious band.
        rules.append(("embedded_file_alone", 0.15, "T1027"))

    # --- XFA & RichMedia (Flash / XML form vectors) ---
    if xfa:
        rules.append(("xfa_form", 0.30, "T1059.007"))
    if rich:
        rules.append(("rich_media", 0.40, "T1027"))

    # NOTE: /OpenAction ALONE and /AcroForm ALONE do NOT trigger a rule.
    # These two indicators are too common in legitimate PDFs (auto-open page 1,
    # interactive forms). Without correlation with /JS, /Launch or /EmbeddedFile,
    # they are noise, not signal.

    max_score = max((s for _, s, _ in rules), default=0.0)
    return max_score, rules


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_static(pdf_path: Path) -> HypothesisResult:
    """Static PDF structure analysis via combinatorial rules.

    Signature: (Path) → HypothesisResult.
    """
    output = _run_pdfid(pdf_path)
    if output is _PROBE_TIMEOUT:
        # The sample defeated the probe — a legitimate PDF never makes a
        # regex counter grind for 30s. Inconclusive => escalate (0.2 through
        # the 0.30 hypothesis weight = 0.06, needs_more_context band), never
        # claim benign on an observation we failed to make (D1).
        return HypothesisResult(
            value=False,
            score=0.2,
            evidence=[Evidence(
                source="runtime_signals",
                field_path="pdf_static.probe_timeout",
                value=f"pdfid hung past {_PDFID_TIMEOUT_S}s — pathological PDF structure, static probe defeated",
            )],
        )
    if not output:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    counts = _parse_pdfid_output(output)
    score, rules = _apply_rules(counts)

    if not rules:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # Present indicators (for traceability in the evidence)
    indicators_str = ",".join(f"{k}={v}" for k, v in counts.items() if v > 0) or "—"

    evidence: list[Evidence] = []
    for rule_name, rule_score, mitre in rules:
        evidence.append(Evidence(
            source="runtime_signals",
            field_path=f"pdf_static.rule[{rule_name}]",
            value=f"score={rule_score:.2f} mitre={mitre} indicators={indicators_str}",
        ))

    return HypothesisResult(
        value=score >= 0.3,
        score=round(score, 3),
        evidence=evidence,
    )
