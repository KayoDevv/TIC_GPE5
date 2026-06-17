"""PDF analysis agent — runs inside the ubuntu-pdf-sandbox:v1 K8s pod.

Receives --job-id and --s3-url as CLI arguments.
Environment variables: KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_OUT,
                       MINIO_ENDPOINT, EMAIL_CONTEXT_JSON.

Multi-layer pipeline (defense-in-depth):

    1. Download the sample from MinIO (presigned URL)

    2. STATIC LAYER — orthogonal probes over the raw bytes:
         a) pdfid (Didier Stevens) — combinatorial rules on PDF structure
         b) stream_entropy v2 — localized entropy peak (hidden payload)
         c) embedded_magic — ELF/PE/ZIP/etc. embedded at offset > 0
       MAX aggregation → pdf_static_indicators (weight 0.30)

    3. Snapshot BEFORE

    4. DYNAMIC LAYER A — `strace -f mutool draw /sample.pdf`
         Renders the pages, triggers parser bugs, exercises zlib/JPEG/JBIG2.
         Catches mupdf CVEs, malicious files that exploit rendering.

    4-bis. DYNAMIC LAYER B — `strace -f node /opt/agent/pdf_runner.js`
         Extracts the PDF's JS via PDF.js, runs it in a Node vm with a stubbed
         Adobe context. The app.launchURL / this.submitForm calls trigger REAL
         network syscalls visible to strace.
         Catches JS-based polymorphs invisible to the static and mutool layers.

    5. Snapshot AFTER

    6. Parse strace — UNION of the two traces (A ∪ B) so the 7 behavioural
       hypotheses see any signal, regardless of the originating layer. No layer
       removed, broadened perception.

    7. 7 behavioural hypotheses (persistence, c2, injection, encryption,
       evasion, propagation, lolbins) + pdf_static_indicators → anomaly_score

    8. Build SandboxLayerResultEvent + IOCs

    9. Publish to sandbox_layer.result
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))

from agent_runtime import EMAIL_CONTEXT, TIMEOUT_S, get_logger, now_iso, publish, run_cli

from models import MemoryObservables, NetworkObservables, RuntimeSignals
from snapshot import compute_diff, take_snapshot
from strace_collector import extract_evasion_tells, extract_sleep_cumulated, parse_strace_log
from memory import collect_memory_observables
from core.messages import PDF_ERROR_SUMMARY, PDF_GUARD_NEEDS_CONTEXT
from core.report import build_pdf_narrative, build_iocs, build_result_event
from core.scoring import (
    compute_anomaly_score,
    execution_liveness,
    guarded_verdict,
    low_observability_alert,
)
import hypotheses.persistence as h_persistence
import hypotheses.c2 as h_c2
import hypotheses.injection as h_injection
import hypotheses.encryption as h_encryption
import hypotheses.evasion as h_evasion
import hypotheses.propagation as h_propagation
import hypotheses.lolbins as h_lolbins
from hypotheses.pdf_static import evaluate_static as pdf_static_evaluate
from hypotheses.stream_entropy import evaluate_static as entropy_evaluate
from hypotheses.embedded_magic import evaluate_static as embedded_evaluate
from hypotheses.pdf_uri import evaluate_static as uri_evaluate
from hypotheses.pdf_anomaly import evaluate_static as anomaly_evaluate
from hypotheses._types import HypothesisResult

log = get_logger("pdf-agent")

# ---------------------------------------------------------------------------
# Config (PDF-specific; the shared Kafka/MinIO/EMAIL/TIMEOUT config is in
# agent_runtime, imported above)
# ---------------------------------------------------------------------------

# SSRF protection — restrict sample download to known MinIO endpoints.
# Override via env var ALLOWED_DOWNLOAD_HOSTS="host1,host2,...".
# Post-Option-B (Kafka/MinIO in-cluster): only the K8s service endpoint is legit.
# The host IP 172.16.249.133 has been removed — no more docker-compose host bridge.
_DEFAULT_ALLOWED_HOSTS = "minio.minio.svc.cluster.local"
ALLOWED_DOWNLOAD_HOSTS = frozenset(
    h.strip() for h in os.getenv("ALLOWED_DOWNLOAD_HOSTS", _DEFAULT_ALLOWED_HOSTS).split(",")
    if h.strip()
)

# ---------------------------------------------------------------------------
# PDF weights — rebalanced to include pdf_static_indicators (weight 0.30)
# The runtime behaviours stay present but the static signal is strong for
# evasive PDFs that trigger no suspicious syscalls.
# ---------------------------------------------------------------------------

PDF_WEIGHTS: dict[str, float] = {
    # Behavioural — 7 hypotheses = 0.70 total
    # Identical regardless of the file's source (embedded ELF, JS, etc.)
    "persistence_detected":  0.12,
    "c2_communication":      0.12,
    "code_injection":        0.10,
    "lolbins_abuse":         0.10,
    "file_encryption":       0.08,
    "evasion_attempted":     0.08,
    "propagation":           0.10,
    # Format-specific static — complementary signal, never dominant
    # Swap for docx_static, lnk_static, etc. depending on the incoming format
    "pdf_static_indicators": 0.30,
}

_BEHAVIORAL_PIPELINE: list[tuple[str, object]] = [
    ("evasion_attempted",    h_evasion),
    ("file_encryption",      h_encryption),
    ("c2_communication",     h_c2),
    ("lolbins_abuse",        h_lolbins),
    ("propagation",          h_propagation),
    ("persistence_detected", h_persistence),
    ("code_injection",       h_injection),
]


# MITRE ATT&CK tactic per hypothesis (config — consumed by build_iocs).
_HYP_TO_MITRE: dict[str, str] = {
    "persistence_detected":  "TA0003",
    "c2_communication":      "TA0011",
    "code_injection":        "TA0005",
    "file_encryption":       "TA0040",
    "evasion_attempted":     "TA0005",
    "propagation":           "TA0008",
    "lolbins_abuse":         "T1059",
    "pdf_static_indicators": "T1027",
}


def _ioc_type(hyp_name: str, ev) -> str:
    """PDF IOC typing: pdf_indicator for the static probe, syscall otherwise."""
    return "pdf_indicator" if hyp_name == "pdf_static_indicators" else "syscall"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download_sample(s3_url: str, dest: Path) -> None:
    log.info("Downloading PDF sample from %s", s3_url[:80])

    # SSRF guard — reject file://, gopher://, internal metadata IPs, etc.
    # An attacker who can inject on the Kafka topic must not be able to
    # exfiltrate host secrets or pivot to internal services via this agent.
    parsed = urlparse(s3_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Refusing scheme {parsed.scheme!r} (only http/https allowed)")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    if parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(
            f"Host {parsed.hostname!r} not in ALLOWED_DOWNLOAD_HOSTS "
            f"({sorted(ALLOWED_DOWNLOAD_HOSTS)})"
        )

    with urllib.request.urlopen(s3_url, timeout=60) as resp:  # noqa: S310 (validated above)
        dest.write_bytes(resp.read())
    log.info("Sample downloaded: %d bytes", dest.stat().st_size)


def _compute_anomaly_score(hyp_results: dict) -> float:
    """PDF weighted sum → anomaly_score. Delegates to the pure core (core/scoring)."""
    return compute_anomaly_score(hyp_results, PDF_WEIGHTS)


# PDF verdict thresholds — config. The 3-band logic lives in core/scoring.
_VERDICT_MALICIOUS = 0.15
_VERDICT_SUSPICIOUS = 0.04


def _build_narrative(hyp_results: dict, anomaly_score: float, duration_s: float) -> tuple[str, str]:
    """(verdict, narrative) PDF. Delegates to the pure core (core/report)."""
    return build_pdf_narrative(
        hyp_results, anomaly_score, duration_s, _VERDICT_MALICIOUS, _VERDICT_SUSPICIOUS
    )


# ---------------------------------------------------------------------------
# Pipeline steps (each owns one numbered stage of run_pdf_analysis)
# ---------------------------------------------------------------------------

def _static_layer(sample_path: Path) -> tuple[HypothesisResult, float]:
    """5 static probes over the raw bytes, aggregated by MAX (one positive is enough).

    Returns (pdf_static_indicators result, timing_ms). Evidence is merged.
    """
    log.info("Running multi-probe static analysis")
    t_static = time.monotonic()
    pdfid_result    = pdf_static_evaluate(sample_path)
    entropy_result  = entropy_evaluate(sample_path)
    embedded_result = embedded_evaluate(sample_path)
    uri_result      = uri_evaluate(sample_path)
    anomaly_result  = anomaly_evaluate(sample_path)

    all_evidence = (
        list(pdfid_result.evidence)
        + list(entropy_result.evidence)
        + list(embedded_result.evidence)
        + list(uri_result.evidence)
        + list(anomaly_result.evidence)
    )
    static_score = max(
        pdfid_result.score, entropy_result.score, embedded_result.score,
        uri_result.score, anomaly_result.score,
    )
    result = HypothesisResult(
        value=static_score >= 0.1,
        score=round(static_score, 3),
        evidence=all_evidence,
    )
    timing_ms = round((time.monotonic() - t_static) * 1000, 1)
    log.info(
        "Static probes: pdfid=%.3f entropy=%.3f embedded=%.3f uri=%.3f anomaly=%.3f → combined=%.3f (%d evidence)",
        pdfid_result.score, entropy_result.score, embedded_result.score,
        uri_result.score, anomaly_result.score, result.score, len(all_evidence),
    )
    return result, timing_ms


def _detonate(
    sample_path: Path, work_dir: Path,
) -> tuple[MemoryObservables, int | None, float, bool, Path, Path]:
    """Two straced detonations (mutool draw, then node+PDF.js) + parallel /proc forensics.

    Returns (memory, exit_code, execution_duration_s, timeout_triggered,
    trace_mutool_path, trace_pdfjs_path). exit_code is mutool's (layer A reference);
    pdfjs exit != 0 is common on malformed PDFs (itself a signal).
    """
    trace_mutool_path = work_dir / "trace_mutool.log"
    trace_pdfjs_path  = work_dir / "trace_pdfjs.log"
    per_step_timeout = max(TIMEOUT_S // 2, 30)
    timeout_triggered = False

    # Layer A — mutool draw straced (renders pages, exercises zlib/JPEG/JBIG2 → mupdf CVEs).
    mutool_cmd = [
        "strace", "-f", "-tt", "-e", "trace=all", "-o", str(trace_mutool_path),
        "mutool", "draw", "-o", "/dev/null", str(sample_path),
    ]
    log.info("[layer A] strace + mutool draw (timeout=%ds)", per_step_timeout)

    # Memory forensics in parallel (mutool process)
    memory_result: list[MemoryObservables] = [MemoryObservables()]
    def _collect_memory():
        memory_result[0] = collect_memory_observables("mutool", max_snapshots=5, interval_s=0.5)
    mem_thread = threading.Thread(target=_collect_memory, daemon=True)
    mem_thread.start()

    exec_start = time.time()
    exit_code_mutool: int | None = None
    try:
        with open(work_dir / "stdout_mutool.log", "wb") as out_f, \
             open(work_dir / "stderr_mutool.log", "wb") as err_f:
            r = subprocess.run(mutool_cmd, stdout=out_f, stderr=err_f,
                               timeout=per_step_timeout, check=False)
        exit_code_mutool = r.returncode
    except subprocess.TimeoutExpired:
        log.warning("[layer A] mutool timed out after %ds", per_step_timeout)
        timeout_triggered = True

    mem_thread.join(timeout=10)
    memory = memory_result[0]

    # Layer B — node + PDF.js straced (runs the PDF's embedded JS via PDF.js).
    pdfjs_cmd = [
        "strace", "-f", "-tt", "-e", "trace=all", "-o", str(trace_pdfjs_path),
        "node", "/opt/agent/pdf_runner.js", str(sample_path),
    ]
    log.info("[layer B] strace + node pdf_runner.js (timeout=%ds)", per_step_timeout)
    exit_code_pdfjs: int | None = None
    try:
        with open(work_dir / "stdout_pdfjs.log", "wb") as out_f, \
             open(work_dir / "stderr_pdfjs.log", "wb") as err_f:
            r = subprocess.run(pdfjs_cmd, stdout=out_f, stderr=err_f,
                               timeout=per_step_timeout, check=False)
        exit_code_pdfjs = r.returncode
    except subprocess.TimeoutExpired:
        log.warning("[layer B] pdf_runner.js timed out after %ds", per_step_timeout)
        timeout_triggered = True

    execution_duration_s = time.time() - exec_start

    exit_code = exit_code_mutool
    if exit_code is not None:
        (work_dir / "exit_code").write_text(str(exit_code))
    log.info("Exec done: mutool exit=%s pdfjs exit=%s duration=%.1fs",
             exit_code_mutool, exit_code_pdfjs, execution_duration_s)
    return (memory, exit_code, execution_duration_s, timeout_triggered,
            trace_mutool_path, trace_pdfjs_path)


def _parse_traces(trace_mutool_path: Path, trace_pdfjs_path: Path):
    """Parse the UNION of both straces so a signal from any layer fires the hypotheses.

    Returns (syscalls, sleep_cumulated_s, evasion_tells).
    """
    trace_mutool = trace_mutool_path.read_text(errors="replace") if trace_mutool_path.exists() else ""
    trace_pdfjs  = trace_pdfjs_path.read_text(errors="replace")  if trace_pdfjs_path.exists()  else ""
    trace_combined = trace_mutool + "\n" + trace_pdfjs
    syscalls = parse_strace_log(trace_combined)
    sleep_cumulated = extract_sleep_cumulated(trace_combined)
    evasion_tells = extract_evasion_tells(trace_combined)
    log.info("Trace sizes: mutool=%d bytes pdfjs=%d bytes → %d syscalls in union",
             len(trace_mutool), len(trace_pdfjs), len(syscalls))
    return syscalls, sleep_cumulated, evasion_tells


def _run_behavioural(diff, signals, memory) -> tuple[dict, dict[str, float]]:
    """Run the 7 behavioural hypotheses on the (union) signals. Returns (results, timings_ms)."""
    results: dict = {}
    timings_ms: dict[str, float] = {}
    for name, module in _BEHAVIORAL_PIPELINE:
        t_hyp = time.monotonic()
        results[name] = module.evaluate(diff, signals, memory)
        timings_ms[name] = round((time.monotonic() - t_hyp) * 1000, 1)
        log.debug("[pipeline] %s -> value=%s score=%.3f (%.0fms)",
                  name, results[name].value, results[name].score, timings_ms[name])
    return results, timings_ms


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pdf_analysis(job_id: str, s3_url: str) -> None:
    started_at = now_iso()
    t0 = time.time()

    work_dir = Path("/out") / job_id[:8]
    work_dir.mkdir(parents=True, exist_ok=True)
    sample_path = work_dir / "sample.pdf"

    timeout_triggered = False
    error_msg: str | None = None
    hyp_results: dict = {}
    hypothesis_timings_ms: dict[str, float] = {}

    try:
        # 1. Download
        _download_sample(s3_url, sample_path)

        # 2. Static layer (5 probes over the raw bytes, before execution)
        static_result, static_ms = _static_layer(sample_path)
        hyp_results["pdf_static_indicators"] = static_result
        hypothesis_timings_ms["pdf_static_indicators"] = static_ms

        # 3. Snapshot BEFORE
        log.info("Taking snapshot BEFORE")
        snapshot_before = take_snapshot(relative_ts_s=0.0)

        # 4. Dynamic detonation (mutool + node/PDF.js, straced)
        (memory, exit_code, execution_duration_s, detonation_timeout,
         trace_mutool_path, trace_pdfjs_path) = _detonate(sample_path, work_dir)
        timeout_triggered = timeout_triggered or detonation_timeout

        # 5. Snapshot AFTER
        log.info("Taking snapshot AFTER")
        snapshot_after = take_snapshot(relative_ts_s=execution_duration_s)

        # 6. Parse strace — union of both layers
        syscalls, sleep_cumulated, evasion_tells = _parse_traces(
            trace_mutool_path, trace_pdfjs_path
        )

        # 7. Diff
        diff = compute_diff(
            snapshot_before, snapshot_after,
            execution_duration_s=execution_duration_s,
            exit_code=exit_code,
        )
        signals = RuntimeSignals(
            syscalls_summary=syscalls,
            inotify_events=[],
            network=NetworkObservables(),
            execution_duration_s=execution_duration_s,
            sleep_cumulated_s=sleep_cumulated,
            exit_code=exit_code,
            evasion_tells=evasion_tells,
        )

        log.info(
            "Layer 1 done: files_created=%d processes=%d syscalls=%d rwx=%d",
            diff.files_created_count,
            len(diff.processes_spawned),
            len(syscalls),
            len(memory.suspicious_regions),
        )

        # 8. Behavioural hypotheses (union signals — a mutool exploit surfaces
        #    the same C2/injection signals as a malicious ELF)
        beh_results, beh_timings = _run_behavioural(diff, signals, memory)
        hyp_results.update(beh_results)
        hypothesis_timings_ms.update(beh_timings)

        anomaly_score = _compute_anomaly_score(hyp_results)
        verdict, behavior_summary = _build_narrative(hyp_results, anomaly_score, execution_duration_s)

        # D1 guard — "benign" is only allowed when the render actually
        # happened (M4 liveness); an unobserved/crashed render escalates.
        total_syscalls = sum(s.call_count for s in syscalls)
        liveness_ok, liveness_note = execution_liveness(total_syscalls, exit_code)
        guarded, guard_reason = guarded_verdict(
            anomaly_score, _VERDICT_MALICIOUS, _VERDICT_SUSPICIOUS,
            liveness_ok=liveness_ok,
        )
        if guarded != verdict:
            verdict = guarded
            behavior_summary = PDF_GUARD_NEEDS_CONTEXT.format(
                score=anomaly_score, liveness=liveness_note,
            )

        log.info(
            "Analysis done: verdict=%s guard=%s anomaly=%.3f positive=%s",
            verdict, guard_reason, anomaly_score,
            [k for k, r in hyp_results.items() if r.value],
        )

    except Exception as exc:
        log.exception("PDF analysis failed: %s", exc)
        error_msg = str(exc)
        anomaly_score = 0.0
        verdict = "error"
        behavior_summary = PDF_ERROR_SUMMARY.format(exc=exc)
        timeout_triggered = False
        hypothesis_timings_ms = {}
        hyp_results = {}
        liveness_ok, liveness_note, guard_reason = False, "analysis failed", "analysis_error"

    ended_at = now_iso()
    duration_s = time.time() - t0

    iocs = build_iocs(hyp_results, _HYP_TO_MITRE, _ioc_type)

    # D-obs — greppable verdict line + beacon on the probable-miss signature.
    low_obs = low_observability_alert(
        verdict=verdict, anomaly_score=anomaly_score,
        duration_s=duration_s, n_iocs=len(iocs), liveness_ok=liveness_ok,
    )
    log.info(
        "SANDBOX_VERDICT path=pdf verdict=%s score=%.3f guard=%s liveness=%s "
        "dur=%.2fs iocs=%d low_obs=%s",
        verdict, anomaly_score, guard_reason, liveness_ok, duration_s, len(iocs), low_obs,
    )
    if low_obs:
        log.warning(
            "SANDBOX_LOW_OBSERVABILITY path=pdf reason=%s verdict=%s score=%.3f "
            "iocs=%d — probable miss, do not trust silently",
            low_obs, verdict, anomaly_score, len(iocs),
        )

    event = build_result_event(
        job_id=job_id,
        iocs=iocs,
        behavior_summary=behavior_summary,
        email_context=EMAIL_CONTEXT,
        timeout_triggered=timeout_triggered,
        timestamp=ended_at,
        anomaly_score=anomaly_score,
        duration_s=duration_s,
        error=error_msg,
        pipeline_version="v2-pdf",
        hypothesis_timings_ms=hypothesis_timings_ms,
        hyp_results=hyp_results,
        verdict=verdict,
        meta_extra={
            "file_type": "pdf",
            "liveness_ok": liveness_ok,
            "liveness": liveness_note,
            "verdict_guard": guard_reason,
            "low_observability": low_obs,
        },
    )

    publish(job_id, event, log)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    run_cli("PDF sandbox analysis agent", "PDF Agent", log, run_pdf_analysis)


if __name__ == "__main__":
    main()
