"""Pure core — anomaly scoring + verdict band.

Pure functions (no I/O) shared by the ELF and PDF paths. The weight sets and
thresholds remain the orchestrators' config (run_*.py); here lives only the
aggregation and classification mechanics.
"""

from __future__ import annotations


def compute_anomaly_score(hyp_results: dict, weights: dict[str, float]) -> float:
    """Weighted sum of hypothesis scores, capped at 1.0, rounded to 3 decimals.

    hyp_results : {name: object with a `.score` attribute in [0, 1]}.
    weights     : {name: weight}. A key missing from the weights contributes 0.
    """
    score = sum(weights.get(k, 0.0) * r.score for k, r in hyp_results.items())
    return round(min(score, 1.0), 3)


def verdict_band(
    anomaly_score: float,
    malicious_threshold: float,
    suspicious_threshold: float,
) -> str:
    """Classify the score into 3 bands.

    malicious            if score >= malicious_threshold
    needs_more_context   if score >= suspicious_threshold
    benign               otherwise

    The sandbox is a tie-breaker: it only rules "malicious" on a strong signal,
    "benign" only in the total absence of signal, and sends the whole ambiguous
    middle to the LLM (which does have the sending context) via "needs_more_context".
    """
    if anomaly_score >= malicious_threshold:
        return "malicious"
    if anomaly_score >= suspicious_threshold:
        return "needs_more_context"
    return "benign"
