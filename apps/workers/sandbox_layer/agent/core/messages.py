"""Product-facing message content — the single designated home for French.

CHARON's output language is French: the per-signal explanations and the
behaviour-summary text are shown to French end-users (the extension's UI panel)
and fed to the LLM Layer, and their exact wording is pinned by the golden tests
(tests/test_golden_core.py).

This module is an i18n content table, NOT logic. Code and comments everywhere
else in the codebase — including in this file — are English (CONTRIBUTING.md
§1). Product-facing strings live here and only here; never inline them in a
logic module. To translate the product later, swap this table.
"""

from __future__ import annotations

# Rule-key -> plain-language explanation. The key is the last segment of an
# evidence field_path (see core.report.explain_signal). Values are the French
# product output (see module docstring).
SIGNAL_EXPLAIN: dict[str, str] = {
    # Disguise / structure
    "missing_pdf_magic":        "Le fichier prétend être un PDF mais son entête est d'un autre type (HTML/script) — déguisement caractéristique d'évasion",
    "no_eof_marker":            "Structure PDF malformée (marqueur de fin %%EOF absent)",
    "qpdf_check_failed":        "Échec de la validation structurelle stricte (xref/streams réparés à la volée)",
    "qpdf_linearization_warn":  "Avertissement de linéarisation (PDF web-optimisé) — bénin, fréquent en légitime",
    "stream_endstream_mismatch":"Incohérence stream/endstream dans la structure PDF",
    "obj_endobj_mismatch":      "Incohérence obj/endobj dans la structure PDF",
    "obj_ratio_extreme":        "Ratio objets/pages extrême (>100:1) — pattern d'empaquetage de payload",
    "obj_ratio_high":           "Ratio objets/pages élevé",
    "encrypted":                "PDF chiffré (rare en document légitime)",
    "many_objstm":              "Nombreux object streams (obfuscation possible)",
    # Execution / active content
    "js_auto_triggered":        "JavaScript exécuté automatiquement à l'ouverture (/OpenAction) — sans interaction utilisateur",
    "js_embedded":              "JavaScript embarqué (passif)",
    "dropper_with_payload":     "Fichier embarqué couplé à un déclencheur d'exécution (pattern dropper)",
    "dropper_auto_exec":        "Fichier embarqué exécuté automatiquement à l'ouverture (pattern dropper)",
    "embedded_file_alone":      "Fichier embarqué dans le PDF",
    "launch_action":            "Action /Launch (exécution d'un programme externe) — quasi toujours malveillant",
    "jbig2_colors_overflow":    "Pattern d'exploit JBIG2 (CVE-2009-0658)",
    "rich_media":               "Contenu RichMedia/Flash embarqué",
    "xfa_form":                 "Formulaire XFA (vecteur d'exécution)",
    # URI / network
    "exec_extension":           "Lien pointant vers un exécutable (.exe/.scr/.ps1/...)",
    "bare_ip":                  "Lien vers une adresse IP nue (contournement DNS/réputation)",
    "fileshare":                "Lien vers un service de partage de fichiers fréquemment abusé",
    "free_hosting":             "Lien vers de l'hébergement gratuit/jetable (pattern phishing)",
    "obfuscated_b64_param":     "URL avec paramètres base64 obfusqués",
    "shortener":                "Lien raccourci masquant la destination réelle",
    "suspicious_tld":           "Domaine sur un TLD fréquemment abusé pour le phishing",
    "raw_hoster":               "Lien vers un hébergeur de contenu brut",
    "external_url":             "Lien externe vers un domaine non catégorisé",
    # Generic
    "local_peak":               "Pic d'entropie localisé (contenu compressé/chiffré)",
    # Probe health (D1 — a defeated probe is a signal, not an absence of signal)
    "probe_timeout":            "L'analyse statique a été mise en échec par le fichier (outil bloqué jusqu'au timeout) — structure pathologique, résultat non concluant",
}

# --- PDF behaviour-summary templates (product output, golden-pinned) ---------
# `.format()` templates used by core.report.build_pdf_narrative and the PDF
# agent. The exact wording is frozen by tests/test_golden_core.py.
PDF_INDICATORS_PREFIX = " Indicateurs : "  # joined with " ; ", terminated by "."

PDF_NARRATIVE_MALICIOUS = (
    "Verdict sandbox : MALICIOUS (score {score:.2f}). "
    "PDF analysé via mutool + PDF.js en {duration:.1f}s."
)
PDF_NARRATIVE_NEEDS_CONTEXT = (
    "Verdict sandbox : NEEDS_MORE_CONTEXT (score {score:.2f}). "
    "Signaux faibles/ambigus, insuffisants pour trancher seuls."
)
PDF_NEEDS_CONTEXT_GUIDE = (
    " À corréler avec le contexte de l'email (expéditeur, objet, corps) : "
    "un lien vers un domaine d'apparence légitime ou une structure atypique "
    "peut être du phishing par usurpation. Le sandbox ne dispose pas du contexte d'envoi."
)
PDF_NARRATIVE_BENIGN = (
    "Verdict sandbox : BENIGN (score {score:.2f}). "
    "Aucun indicateur structurel, comportemental ou d'URI suspect détecté ({duration:.1f}s)."
)
# Emitted by the PDF agent (run_pdf_analysis) on the D1 guard override / error.
PDF_GUARD_NEEDS_CONTEXT = (
    "Verdict sandbox : NEEDS_MORE_CONTEXT (score {score:.2f}). "
    "Aucun signal, mais aucune exécution normale observée non plus "
    "({liveness}) — l'absence de signal ne prouve pas la bénignité. "
    "À corréler avec le contexte de l'email."
)
PDF_ERROR_SUMMARY = "Verdict sandbox : ERROR — l'analyse a échoué ({exc})."
