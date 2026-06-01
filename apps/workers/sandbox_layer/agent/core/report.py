"""Pure core — narrative / behavioural-summary assembly (Layer 4).

Turns hypothesis results into human-readable text (LLM + UI). No I/O. Two
variants: PDF (3-band verdict + indicators explained in plain language) and ELF
(behavioural summary). Tested via tests/test_golden_core.py.

NB: the user-facing strings below (SIGNAL_EXPLAIN values, narrative text) are in
French on purpose — that is the product's output language, pinned by the golden
tests. Only comments/docstrings are in English.
"""

from __future__ import annotations

from .scoring import verdict_band

# Rule-key → plain-language explanation (the key is the last segment of the
# evidence field_path). Values are French (product output language).
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
}


def explain_signal(field_path: str) -> str | None:
    """field_path → plain-language explanation, or None if unmapped."""
    key = field_path.split("[")[-1].rstrip("]").split(".")[-1]
    return SIGNAL_EXPLAIN.get(key)


def build_pdf_narrative(
    hyp_results: dict,
    anomaly_score: float,
    duration_s: float,
    malicious_threshold: float,
    suspicious_threshold: float,
) -> tuple[str, str]:
    """Build the (verdict, narrative) PDF tuple, readable by the LLM and the UI.

    The narrative leads with the verdict band, translates signals into plain
    language (with the concrete value: URL, disguise), and gives the LLM a
    correlation instruction for the ambiguous band.
    """
    verdict = verdict_band(anomaly_score, malicious_threshold, suspicious_threshold)

    # Unique signals in plain language (deduped by explanation), with their value.
    signals: list[str] = []
    seen: set[str] = set()
    for r in hyp_results.values():
        for ev in r.evidence:
            expl = explain_signal(ev.field_path)
            if not expl or expl in seen:
                continue
            seen.add(expl)
            # For URIs, append the observed value (useful to the LLM).
            if ev.field_path.startswith("pdf_uri."):
                signals.append(f"{expl} : {ev.value[:160]}")
            else:
                signals.append(expl)

    if verdict == "malicious":
        head = f"Verdict sandbox : MALICIOUS (score {anomaly_score:.2f}). PDF analysé via mutool + PDF.js en {duration_s:.1f}s."
        body = " Indicateurs : " + " ; ".join(signals) + "." if signals else ""
        return verdict, head + body

    if verdict == "needs_more_context":
        head = f"Verdict sandbox : NEEDS_MORE_CONTEXT (score {anomaly_score:.2f}). Signaux faibles/ambigus, insuffisants pour trancher seuls."
        body = " Indicateurs : " + " ; ".join(signals) + "." if signals else ""
        guide = (
            " À corréler avec le contexte de l'email (expéditeur, objet, corps) : "
            "un lien vers un domaine d'apparence légitime ou une structure atypique "
            "peut être du phishing par usurpation. Le sandbox ne dispose pas du contexte d'envoi."
        )
        return verdict, head + body + guide

    return verdict, (
        f"Verdict sandbox : BENIGN (score {anomaly_score:.2f}). "
        f"Aucun indicateur structurel, comportemental ou d'URI suspect détecté ({duration_s:.1f}s)."
    )


def build_elf_summary(hyp_results: dict, anomaly_score: float, duration_s: float) -> str:
    """One-sentence ELF behavioural summary (for the LLM and the UI)."""
    positives = [k for k, r in hyp_results.items() if r.value]
    if not positives:
        return (
            f"Sample ran for {duration_s:.1f}s and exited cleanly. "
            "No filesystem mutations, no outbound connections, no RWX memory regions, "
            f"no persistence mechanism. anomaly_score={anomaly_score:.2f}"
        )
    return (
        f"Sample ran for {duration_s:.1f}s. "
        f"Detected signals: {', '.join(positives)}. "
        f"anomaly_score={anomaly_score:.2f}"
    )


# ---------------------------------------------------------------------------
# Result-event assembly (Layer 4 — Kafka output)
# ---------------------------------------------------------------------------

def build_iocs(
    hyp_results: dict,
    mitre_map: dict[str, str],
    type_for,
    *,
    memory_regions=None,
) -> list[dict]:
    """IOCs from the positive hypotheses (+ RWX memory regions if provided).

    type_for(hyp_name, evidence) -> str: decides the IOC type. The typing differs
    between ELF (syscall/file_hash by source) and PDF (pdf_indicator/syscall),
    hence the callable rather than a hardcoded condition.
    memory_regions: RWX regions to add as IOCs (ELF only; None otherwise).
    """
    iocs: list[dict] = []
    for hyp_name, result in hyp_results.items():
        if not result.value:
            continue
        mitre = mitre_map.get(hyp_name, "TA0000")
        for ev in result.evidence:
            iocs.append({
                "type": type_for(hyp_name, ev),
                "value": ev.value[:256],
                "mitre_tactic": mitre,
                "description": f"{hyp_name}: {ev.field_path}",
            })
    for region in (memory_regions or []):
        iocs.append({
            "type": "syscall",
            "value": f"mmap(RWX) pid={region.pid} {region.start_addr}-{region.end_addr}",
            "mitre_tactic": "TA0005",
            "description": f"RWX memory region: {region.permissions} {region.size_bytes}B",
        })
    return iocs


def build_result_event(
    *,
    job_id: str,
    iocs: list[dict],
    behavior_summary: str,
    email_context: dict,
    timeout_triggered: bool,
    timestamp: str,
    anomaly_score: float,
    duration_s: float,
    error: str | None,
    pipeline_version: str,
    hypothesis_timings_ms: dict,
    hyp_results: dict,
    verdict: str | None = None,
    meta_extra: dict | None = None,
) -> dict:
    """Assemble the SandboxLayerResult event published to Kafka.

    Common ELF/PDF skeleton. `verdict` (top-level key) is present for PDF only.
    `meta_extra` carries the path-specific _meta keys (early_exit for ELF,
    file_type for PDF).
    """
    meta = {
        "anomaly_score": anomaly_score,
        "duration_s": round(duration_s, 2),
        "error": error,
        "pipeline_version": pipeline_version,
        "hypothesis_timings_ms": hypothesis_timings_ms,
        "hypothesis_scores": {k: round(r.score, 3) for k, r in hyp_results.items()},
    }
    if meta_extra:
        meta.update(meta_extra)
    event: dict = {
        "job_id": job_id,
        "iocs": iocs,
        "behavior_summary": behavior_summary,
        "email_context": email_context,
        "timeout_triggered": timeout_triggered,
        "timestamp": timestamp,
        "_meta": meta,
    }
    if verdict is not None:
        event["verdict"] = verdict
    return event
