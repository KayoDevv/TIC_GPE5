"""Pure core — narrative / behavioural-summary assembly (Layer 4). No I/O.

Turns hypothesis results into human-readable text for the LLM + UI (PDF: 3-band
verdict + indicators; ELF: behavioural summary). The French user-facing CONTENT
lives in core.messages; this module holds only the assembly logic.
"""

from __future__ import annotations

from .messages import (
    PDF_INDICATORS_PREFIX,
    PDF_NARRATIVE_BENIGN,
    PDF_NARRATIVE_MALICIOUS,
    PDF_NARRATIVE_NEEDS_CONTEXT,
    PDF_NEEDS_CONTEXT_GUIDE,
    SIGNAL_EXPLAIN,
)
from .sanitize import (
    count_control_tokens,
    neutralize_untrusted,
    sanitize_email_context,
    sanitize_iocs,
)
from .scoring import verdict_band


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
        head = PDF_NARRATIVE_MALICIOUS.format(score=anomaly_score, duration=duration_s)
        body = PDF_INDICATORS_PREFIX + " ; ".join(signals) + "." if signals else ""
        return verdict, head + body

    if verdict == "needs_more_context":
        head = PDF_NARRATIVE_NEEDS_CONTEXT.format(score=anomaly_score)
        body = PDF_INDICATORS_PREFIX + " ; ".join(signals) + "." if signals else ""
        return verdict, head + body + PDF_NEEDS_CONTEXT_GUIDE

    return verdict, PDF_NARRATIVE_BENIGN.format(score=anomaly_score, duration=duration_s)


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


def _build_signals(hyp_results: dict, weights: dict[str, float]) -> list[dict]:
    # A hypothesis absent from hyp_results was early-exit skipped: score=null,
    # evaluated=false — kept distinct from a real 0 score.
    signals: list[dict] = []
    for name in weights:
        result = hyp_results.get(name)
        if result is None:
            signals.append({"name": name, "score": None,
                            "fired": False, "evaluated": False})
        else:
            signals.append({"name": name, "score": round(result.score, 3),
                            "fired": result.value, "evaluated": True})
    return signals


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
    weights: dict[str, float] | None = None,
    verdict: str | None = None,
    meta_extra: dict | None = None,
) -> dict:
    """Assemble the SandboxLayerResult event published to Kafka.

    Decision-facing fields are top-level (verdict, anomaly_score, analysis_trust,
    signals); operational fields live in _meta. `meta_extra` carries path-specific
    keys (early_exit for ELF, file_type for PDF); liveness_ok/low_observability are
    promoted into analysis_trust.
    """
    extra = dict(meta_extra or {})
    trust = {
        "liveness_ok": extra.pop("liveness_ok", None),
        "low_observability": extra.pop("low_observability", None),
        "timeout_triggered": timeout_triggered,
        "error": error,
    }
    weights = weights if weights is not None else {k: 0.0 for k in hyp_results}

    meta = {
        # D4 — factual count of neutralized chat-template control tokens (weak
        # signal for the LLM, never a detection claim).
        "prompt_injection_filtered": (
            count_control_tokens(behavior_summary)
            + count_control_tokens(email_context)
            + count_control_tokens(iocs)
        ),
    }
    meta.update(extra)

    # D4 — neutralize control tokens at this single output boundary; the LLM Layer
    # must still treat these fields as untrusted data at prompt-assembly time.
    return {
        "job_id": job_id,
        "verdict": verdict,
        "anomaly_score": anomaly_score,
        "analysis_trust": trust,
        "signals": _build_signals(hyp_results, weights),
        "iocs": sanitize_iocs(iocs),
        "behavior_summary": neutralize_untrusted(behavior_summary),
        "email_context": sanitize_email_context(email_context),
        "timestamp": timestamp,
        "_meta": meta,
    }
