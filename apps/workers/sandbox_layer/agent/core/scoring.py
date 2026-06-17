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


# Below this many captured syscalls, the sample is considered to have done
# (almost) nothing: dynamic linking alone produces dozens of syscalls, so a
# lower count means the process bailed out instantly or never really ran.
MIN_MEANINGFUL_SYSCALLS = 30


def execution_liveness(total_syscalls: int, exit_code: int | None) -> tuple[bool, str]:
    """Did the sample demonstrably RUN (M4 liveness observable)?

    Returns (liveness_ok, note). liveness_ok is True only when a normal
    execution was actually observed: the process completed (exit 0) AND
    produced a meaningful amount of syscall activity. A crash, a timeout
    (exit_code None) or a near-silent run all yield False — "no signal"
    then means "nothing was observed", not "nothing is wrong".
    """
    note = f"{total_syscalls} syscalls, exit_code={exit_code}"
    ok = exit_code == 0 and total_syscalls >= MIN_MEANINGFUL_SYSCALLS
    return ok, note


def guarded_verdict(
    anomaly_score: float,
    malicious_threshold: float,
    suspicious_threshold: float,
    *,
    liveness_ok: bool,
    analysis_error: bool = False,
) -> tuple[str, str | None]:
    """verdict_band + the D1 guard: absence of signal is NOT proof of benignity.

    A "benign" band is only allowed when a normal execution was actually
    observed (liveness) and the analysis completed without error. Otherwise
    the verdict escalates to "needs_more_context" — NEVER "benign" — because
    a zero score may simply mean the sample detected the sandbox and bailed
    before doing anything observable (the 0.000 contentless miss).

    Threshold-independent on purpose: recalibrating the bands (D-calib) must
    not silently re-open the silence==benign hole.

    Returns (verdict, guard_reason); guard_reason is None when the band was
    not overridden.
    """
    band = verdict_band(anomaly_score, malicious_threshold, suspicious_threshold)
    if band != "benign":
        return band, None
    if analysis_error:
        return "needs_more_context", "analysis_error"
    if not liveness_ok:
        return "needs_more_context", "no_liveness"
    return band, None


def low_observability_alert(
    *,
    verdict: str,
    anomaly_score: float,
    duration_s: float,
    n_iocs: int,
    liveness_ok: bool,
) -> str | None:
    """D-obs — beacon for a verdict that must not pass silently.

    Returns a short reason when the run carries the signature of a probable
    miss (the contentless pattern that let the run_OpusV1.4 0.000 slip through),
    so operators can grep/alert on it EVEN when the D1 guard already escalated
    the verdict. We can only fix what we can see; the original miss went by
    unnoticed. None when a normal, trustworthy execution was observed.

      - no_liveness : nothing meaningful ran (timeout / crash / instant bailout);
      - quiet_benign: a benign verdict with zero score, zero IOC and a sub-5s
                      run — the shape of a sample that detected the sandbox.
    """
    if verdict == "error":
        return None  # already surfaced loudly via the exception path
    if not liveness_ok:
        return "no_liveness"
    if verdict == "benign" and anomaly_score == 0.0 and n_iocs == 0 and duration_s < 5.0:
        return "quiet_benign"
    return None
