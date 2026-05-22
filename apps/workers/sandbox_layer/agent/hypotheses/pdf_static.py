"""Hypothèse PDF statique — analyse de structure via pdfid (Didier Stevens).

Stratégie v3 : règles **combinatoires** au lieu de poids par keyword.
Un keyword isolé est souvent trop ambigu :
  - `/OpenAction` seul  → 99% des PDFs légitimes (auto-open page 1)
  - `/AcroForm`  seul   → tout formulaire interactif
  - `/JS`        seul   → présent dans CV PDF, factures, etc.
  - `/Launch`    seul   → quasi toujours malveillant (rare en légit)

Les combinaisons sont beaucoup plus discriminantes :
  - `/JS` + `/OpenAction` → JS auto-exécuté au load = pattern malware classique
  - `/EmbeddedFile` + `/JS` ou `/Launch` → dropper pattern
  - `/JBIG2Decode` + `/Colors` → pattern CVE-2009-0658 (Acrobat integer overflow)

Signature: (Path) → HypothesisResult — identique aux autres sondes statiques.

Poids dans l'anomaly_score PDF : 0.30 (multi-probe MAX en amont).
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from hypotheses._types import Evidence, HypothesisResult

log = logging.getLogger(__name__)

# Keywords trackés par pdfid — utilisés dans les règles combinatoires ci-dessous.
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

def _run_pdfid(pdf_path: Path) -> str:
    """Lance pdfid et retourne sa sortie. '' si absent/timeout."""
    try:
        result = subprocess.run(
            ["pdfid", str(pdf_path)],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        log.warning("pdfid not found — static PDF analysis unavailable")
        return ""
    except subprocess.TimeoutExpired:
        log.warning("pdfid timed out on %s", pdf_path.name)
        return ""


def _parse_pdfid_output(output: str) -> dict[str, int]:
    """Extrait les compteurs keyword→count depuis la sortie de pdfid."""
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
# Règles combinatoires
# ---------------------------------------------------------------------------

def _apply_rules(counts: dict[str, int]) -> tuple[float, list[tuple[str, float, str]]]:
    """Applique les règles combinatoires, retourne (max_score, [rules_fired]).

    Chaque règle = (nom, score, technique_mitre). On garde le MAX des scores
    (pas la somme) — un seul pattern fort suffit à classer malveillant.
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

    # --- Solos forts (rares en légit) ---
    if launch:
        rules.append(("launch_action", 0.70, "T1204.002"))

    if jbig2 and colors:
        rules.append(("jbig2_colors_overflow", 0.70, "T1027"))   # CVE-2009-0658

    # --- Combinaisons JS ---
    if js and auto_action:
        rules.append(("js_auto_triggered", 0.80, "T1059.007"))   # exécution sans interaction — discriminant (0 benign)
    elif js:
        # Calibré : du JS PASSIF (sans /OpenAction) existe dans des docs légitimes
        # (navigation, formulaires) → signal modéré, pas un verdict.
        rules.append(("js_embedded", 0.25, "T1059.007"))

    # --- Dropper patterns ---
    # CALIBRÉ : /EmbeddedFile + /JS PASSIF n'est PAS un dropper (un RFC embarque sa
    # source XML et a du JS de navigation → faux positif à 0.9, observé sur rfc9110).
    # Le vrai dropper exige /Launch (quasi toujours malveillant) OU du JS
    # AUTO-EXÉCUTÉ (/OpenAction|/AA) qui lance le payload sans interaction.
    if embedded and launch:
        rules.append(("dropper_with_payload", 0.90, "T1027"))
    elif embedded and js and auto_action:
        rules.append(("dropper_auto_exec", 0.90, "T1027"))
    elif embedded:
        # /EmbeddedFile seul : 4/7 benigns le déclenchent → bande suspicious.
        rules.append(("embedded_file_alone", 0.15, "T1027"))

    # --- XFA & RichMedia (vecteurs Flash / XML forms) ---
    if xfa:
        rules.append(("xfa_form", 0.30, "T1059.007"))
    if rich:
        rules.append(("rich_media", 0.40, "T1027"))

    # NOTE: /OpenAction SEUL et /AcroForm SEUL ne déclenchent PAS de règle.
    # Ces deux indicateurs sont trop communs dans les PDFs légitimes
    # (auto-open page 1, formulaires interactifs). Sans corrélation avec
    # /JS, /Launch ou /EmbeddedFile, ce sont du bruit, pas du signal.

    max_score = max((s for _, s, _ in rules), default=0.0)
    return max_score, rules


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_static(pdf_path: Path) -> HypothesisResult:
    """Analyse statique de structure PDF via règles combinatoires.

    Signature: (Path) → HypothesisResult.
    """
    output = _run_pdfid(pdf_path)
    if not output:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    counts = _parse_pdfid_output(output)
    score, rules = _apply_rules(counts)

    if not rules:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # Indicateurs présents (pour traçabilité dans l'evidence)
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
