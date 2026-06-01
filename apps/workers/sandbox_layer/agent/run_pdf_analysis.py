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

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from aiokafka import AIOKafkaProducer

sys.path.insert(0, str(Path(__file__).parent))

from models import MemoryObservables, NetworkObservables, RuntimeSignals
from snapshot import compute_diff, take_snapshot
from strace_collector import extract_sleep_cumulated, parse_strace_log
from memory import collect_memory_observables
from core.report import build_pdf_narrative, build_iocs, build_result_event
from core.scoring import compute_anomaly_score
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("pdf-agent")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.kafka.svc.cluster.local:9092")
TOPIC_OUT       = os.getenv("KAFKA_TOPIC_OUT", "sandbox_layer.result")
MINIO_ENDPOINT  = os.getenv("MINIO_ENDPOINT", "minio.minio.svc.cluster.local:9000")
EMAIL_CONTEXT   = json.loads(os.getenv("EMAIL_CONTEXT_JSON", "{}"))
TIMEOUT_S       = int(os.getenv("SANDBOX_TIMEOUT_S", "120"))

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
    # Remplacer par docx_static, lnk_static, etc. selon le format entrant
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

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


# Seuils de verdict PDF — config. La logique des 3 bandes vit dans core/scoring.
_VERDICT_MALICIOUS = 0.15
_VERDICT_SUSPICIOUS = 0.04


def _build_narrative(hyp_results: dict, anomaly_score: float, duration_s: float) -> tuple[str, str]:
    """(verdict, narrative) PDF. Delegates to the pure core (core/report)."""
    return build_pdf_narrative(
        hyp_results, anomaly_score, duration_s, _VERDICT_MALICIOUS, _VERDICT_SUSPICIOUS
    )


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

async def _publish(job_id: str, event: dict) -> None:
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    try:
        await producer.send_and_wait(TOPIC_OUT, value=event)
        log.info("Published to %s job_id=%s", TOPIC_OUT, job_id)
    finally:
        await producer.stop()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pdf_analysis(job_id: str, s3_url: str) -> None:
    started_at = _now_iso()
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

        # 2. Multi-probe static layer (before execution — none triggers anything)
        #    Five independent probes look at different aspects of the file:
        #      a) pdfid          → combinatorial rules on PDF structure
        #      b) stream_entropy → local encrypted/obfuscated payload (generic)
        #      c) embedded_magic → embedded executables (generic)
        #      d) pdf_uri        → URI actions to fileshare/exe/bare IP (phishing)
        #      e) pdf_anomaly    → structural anomalies (broken xref, obj/page ratio)
        #    The retained score is the MAX — a single positive signal is enough to alert.
        log.info("Running multi-probe static analysis")
        t_static = time.monotonic()
        pdfid_result    = pdf_static_evaluate(sample_path)
        entropy_result  = entropy_evaluate(sample_path)
        embedded_result = embedded_evaluate(sample_path)
        uri_result      = uri_evaluate(sample_path)
        anomaly_result  = anomaly_evaluate(sample_path)

        # Aggregation: take the max score + merge the evidence
        all_evidence = (
            list(pdfid_result.evidence)
            + list(entropy_result.evidence)
            + list(embedded_result.evidence)
            + list(uri_result.evidence)
            + list(anomaly_result.evidence)
        )
        static_score = max(
            pdfid_result.score,
            entropy_result.score,
            embedded_result.score,
            uri_result.score,
            anomaly_result.score,
        )
        from hypotheses._types import HypothesisResult as _HR
        pdf_static_result = _HR(
            value=static_score >= 0.1,
            score=round(static_score, 3),
            evidence=all_evidence,
        )

        hypothesis_timings_ms["pdf_static_indicators"] = round(
            (time.monotonic() - t_static) * 1000, 1
        )
        hyp_results["pdf_static_indicators"] = pdf_static_result
        log.info(
            "Static probes: pdfid=%.3f entropy=%.3f embedded=%.3f uri=%.3f anomaly=%.3f → combined=%.3f (%d evidence)",
            pdfid_result.score, entropy_result.score, embedded_result.score,
            uri_result.score, anomaly_result.score, pdf_static_result.score, len(all_evidence),
        )

        # 3. Snapshot BEFORE
        log.info("Taking snapshot BEFORE")
        snapshot_before = take_snapshot(relative_ts_s=0.0)

        # 4. DYNAMIC LAYER A — mutool draw straced
        # Renders the PDF pages, triggers parser bugs, exercises the
        # decompression code (zlib, JPEG, JBIG2) → catches mupdf CVEs.
        # No PDF JS execution (mutool draw does not do it).
        trace_mutool_path = work_dir / "trace_mutool.log"
        trace_pdfjs_path  = work_dir / "trace_pdfjs.log"

        per_step_timeout = max(TIMEOUT_S // 2, 30)

        mutool_cmd = [
            "strace", "-f", "-tt", "-e", "trace=all", "-o", str(trace_mutool_path),
            "mutool", "draw", "-o", "/dev/null", str(sample_path),
        ]
        log.info("[layer A] strace + mutool draw (timeout=%ds)", per_step_timeout)

        # Memory forensics in parallel (mutool process)
        memory_result: list[MemoryObservables] = [MemoryObservables()]
        def _collect_memory():
            memory_result[0] = collect_memory_observables(
                "mutool", max_snapshots=5, interval_s=0.5
            )

        mem_thread = threading.Thread(target=_collect_memory, daemon=True)
        mem_thread.start()

        exec_start = time.time()
        exit_code_mutool: int | None = None
        try:
            with open(work_dir / "stdout_mutool.log", "wb") as out_f, \
                 open(work_dir / "stderr_mutool.log", "wb") as err_f:
                r = subprocess.run(
                    mutool_cmd, stdout=out_f, stderr=err_f,
                    timeout=per_step_timeout, check=False,
                )
            exit_code_mutool = r.returncode
        except subprocess.TimeoutExpired:
            log.warning("[layer A] mutool timed out after %ds", per_step_timeout)
            timeout_triggered = True

        mem_thread.join(timeout=10)
        memory = memory_result[0]

        # 4-bis. DYNAMIC LAYER B — Node + PDF.js straced
        # Executes the PDF's embedded JavaScript (extraction via PDF.js,
        # execution in a Node vm with a stubbed Adobe context).
        # Catches JS-based polymorphs invisible to the static layer
        # AND to mutool (which does not run the JS).
        pdfjs_cmd = [
            "strace", "-f", "-tt", "-e", "trace=all", "-o", str(trace_pdfjs_path),
            "node", "/opt/agent/pdf_runner.js", str(sample_path),
        ]
        log.info("[layer B] strace + node pdf_runner.js (timeout=%ds)", per_step_timeout)

        exit_code_pdfjs: int | None = None
        try:
            with open(work_dir / "stdout_pdfjs.log", "wb") as out_f, \
                 open(work_dir / "stderr_pdfjs.log", "wb") as err_f:
                r = subprocess.run(
                    pdfjs_cmd, stdout=out_f, stderr=err_f,
                    timeout=per_step_timeout, check=False,
                )
            exit_code_pdfjs = r.returncode
        except subprocess.TimeoutExpired:
            log.warning("[layer B] pdf_runner.js timed out after %ds", per_step_timeout)
            timeout_triggered = True

        execution_duration_s = time.time() - exec_start

        # Exit code retained for the report: we take mutool (layer A) as the
        # reference; the pdfjs exit is often != 0 on malformed PDFs (a signal itself).
        exit_code = exit_code_mutool
        if exit_code is not None:
            (work_dir / "exit_code").write_text(str(exit_code))
        log.info(
            "Exec done: mutool exit=%s pdfjs exit=%s duration=%.1fs",
            exit_code_mutool, exit_code_pdfjs, execution_duration_s,
        )

        # 5. Snapshot AFTER
        log.info("Taking snapshot AFTER")
        snapshot_after = take_snapshot(relative_ts_s=execution_duration_s)

        # 6. Parse strace — UNION of the two traces (layer A + layer B)
        # The 7 behavioural hypotheses see the union of syscalls, so a signal
        # caught by any layer makes the hypothesis fire.
        trace_mutool = trace_mutool_path.read_text(errors="replace") if trace_mutool_path.exists() else ""
        trace_pdfjs  = trace_pdfjs_path.read_text(errors="replace")  if trace_pdfjs_path.exists()  else ""
        trace_combined = trace_mutool + "\n" + trace_pdfjs
        syscalls = parse_strace_log(trace_combined)
        sleep_cumulated = extract_sleep_cumulated(trace_combined)
        log.info(
            "Trace sizes: mutool=%d bytes pdfjs=%d bytes → %d syscalls in union",
            len(trace_mutool), len(trace_pdfjs), len(syscalls),
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
        )

        log.info(
            "Layer 1 done: files_created=%d processes=%d syscalls=%d rwx=%d",
            diff.files_created_count,
            len(diff.processes_spawned),
            len(syscalls),
            len(memory.suspicious_regions),
        )

        # 8. Behavioural hypotheses (reused as-is on mutool's syscalls — if
        #    mutool is exploited, the C2/injection signals appear exactly like
        #    for a malicious ELF)
        for name, module in _BEHAVIORAL_PIPELINE:
            t_hyp = time.monotonic()
            hyp_results[name] = module.evaluate(diff, signals, memory)
            hypothesis_timings_ms[name] = round(
                (time.monotonic() - t_hyp) * 1000, 1
            )
            log.debug(
                "[pipeline] %s -> value=%s score=%.3f (%.0fms)",
                name,
                hyp_results[name].value,
                hyp_results[name].score,
                hypothesis_timings_ms[name],
            )

        anomaly_score = _compute_anomaly_score(hyp_results)
        verdict, behavior_summary = _build_narrative(hyp_results, anomaly_score, execution_duration_s)

        log.info(
            "Analysis done: verdict=%s anomaly=%.3f positive=%s",
            verdict, anomaly_score, [k for k, r in hyp_results.items() if r.value],
        )

    except Exception as exc:
        log.exception("PDF analysis failed: %s", exc)
        error_msg = str(exc)
        anomaly_score = 0.0
        verdict = "error"
        behavior_summary = f"Verdict sandbox : ERROR — l'analyse a échoué ({exc})."
        timeout_triggered = False
        hypothesis_timings_ms = {}
        hyp_results = {}

    ended_at = _now_iso()
    duration_s = time.time() - t0

    iocs = build_iocs(hyp_results, _HYP_TO_MITRE, _ioc_type)

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
        meta_extra={"file_type": "pdf"},
    )

    asyncio.run(_publish(job_id, event))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="PDF sandbox analysis agent")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--s3-url", required=True)
    args = parser.parse_args()

    log.info("PDF Agent started: job_id=%s", args.job_id)
    run_pdf_analysis(args.job_id, args.s3_url)
    log.info("PDF Agent done: job_id=%s", args.job_id)


if __name__ == "__main__":
    main()
