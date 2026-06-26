"""ELF analysis agent — runs inside the ubuntu-sandbox:v1 K8s pod.

Args: --job-id, --s3-url. Env: KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_OUT,
MINIO_ENDPOINT, EMAIL_CONTEXT_JSON.

Pipeline: download → snapshot → strace+sample (with parallel /proc memory
forensics) → snapshot → 7 hypotheses → anomaly_score → build event → publish.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# Add the current directory to the path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from agent_runtime import EMAIL_CONTEXT, TIMEOUT_S, get_logger, now_iso, publish, run_cli
from models import MemoryObservables, RuntimeSignals
from snapshot import compute_diff, take_snapshot
from strace_collector import extract_evasion_tells, extract_network, extract_sleep_cumulated, parse_strace_log
from memory import collect_memory_observables
from core.report import build_elf_summary, build_iocs, build_result_event
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

log = get_logger("agent")

# Weights and orchestration (shared Kafka/MinIO config is in agent_runtime).
# Sum = 1.0; override via SANDBOX_WEIGHTS_JSON.
DEFAULT_WEIGHTS: dict[str, float] = {
    "persistence_detected": 0.25,
    "c2_communication":     0.20,
    "code_injection":       0.20,
    "lolbins_abuse":        0.15,   # H7 — fileless/LOLBin families
    "file_encryption":      0.10,
    "evasion_attempted":    0.05,
    "propagation":          0.05,
}


def _load_weights() -> dict[str, float]:
    """Weights from SANDBOX_WEIGHTS_JSON if set (re-calibrate without a rebuild), else defaults."""
    raw = os.getenv("SANDBOX_WEIGHTS_JSON")
    if not raw:
        return DEFAULT_WEIGHTS.copy()
    try:
        loaded: dict[str, float] = json.loads(raw)
        for k, v in DEFAULT_WEIGHTS.items():
            loaded.setdefault(k, v)
        return loaded
    except (json.JSONDecodeError, TypeError):
        log.warning("SANDBOX_WEIGHTS_JSON malformed — falling back to DEFAULT_WEIGHTS")
        return DEFAULT_WEIGHTS.copy()


WEIGHTS = _load_weights()

THRESHOLD_MAL = float(os.getenv("SANDBOX_THRESHOLD_MAL", "0.40"))
THRESHOLD_SUS = float(os.getenv("SANDBOX_THRESHOLD_SUS", "0.15"))

# Early-exit: if the partial score before H3 (code_injection, the most RAM-hungry
# hypothesis) already exceeds this, skip H3. 0.45 ≈ 80% of the 0.55 reachable by then.
EARLY_EXIT_THRESHOLD = float(os.getenv("SANDBOX_EARLY_EXIT_THRESHOLD", "0.45"))

# Execution order: ascending RAM cost, so the priciest (H3) runs last and can be skipped.
_HYPOTHESIS_PIPELINE: list[tuple[str, object]] = [
    ("evasion_attempted",    h_evasion),      # H5 — near-free
    ("file_encryption",      h_encryption),   # H4 — low
    ("c2_communication",     h_c2),           # H2 — low
    ("lolbins_abuse",        h_lolbins),      # H7 — near-free
    ("propagation",          h_propagation),  # H6 — low (PCAP already parsed)
    ("persistence_detected", h_persistence),  # H1 — medium
    ("code_injection",       h_injection),    # H3 — most expensive -> last
]

_EARLY_EXIT_AFTER = "propagation"  # early-exit is evaluated right after this (just before H3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# SSRF guard — download restricted to these hosts (override: ALLOWED_DOWNLOAD_HOSTS="h1,h2").
ALLOWED_DOWNLOAD_HOSTS = frozenset(
    h.strip() for h in os.getenv("ALLOWED_DOWNLOAD_HOSTS", "minio.minio.svc.cluster.local").split(",")
    if h.strip()
)


def _download_sample(s3_url: str, dest: Path) -> None:
    log.info("Downloading sample from %s", s3_url[:80])

    # SSRF guard: a forged Kafka topic must not let an attacker pivot via this fetch.
    parsed = urlparse(s3_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Refusing scheme {parsed.scheme!r} (only http/https allowed)")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    if parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(
            f"Host {parsed.hostname!r} not in ALLOWED_DOWNLOAD_HOSTS ({sorted(ALLOWED_DOWNLOAD_HOSTS)})"
        )

    with urllib.request.urlopen(s3_url, timeout=60) as resp:  # noqa: S310 (validated above)
        dest.write_bytes(resp.read())
    dest.chmod(0o755)
    log.info("Sample downloaded: %d bytes", dest.stat().st_size)


def _compute_anomaly_score(hyp_results: dict) -> float:
    """ELF weighted sum → anomaly_score. Delegates to the pure core (core/scoring)."""
    return compute_anomaly_score(hyp_results, WEIGHTS)


def _run_hypotheses_ordered(
    diff: object,
    signals: object,
    memory: object,
) -> tuple[dict, bool, dict[str, float]]:
    """Run the 7 hypotheses in optimized order (descending RAM ROI).

    Implements early-exit: if the partial score after H6 (propagation)
    exceeds EARLY_EXIT_THRESHOLD, H3 (injection) is skipped.
    This avoids the H3 RAM peak when the signal is already clear.

    Returns:
        hyp_results  — dict {name: HypothesisResult}
        early_exit   — True if H3 was skipped
        timings_ms   — dict {name: duration_ms}
    """
    hyp_results: dict = {}
    timings_ms: dict[str, float] = {}
    early_exit = False

    # Only H3 (code_injection) is skipped — the most RAM-expensive one.
    # H1 (persistence) stays: moderate cost and complementary signal.
    _costly = {"code_injection"}

    for name, module in _HYPOTHESIS_PIPELINE:
        if early_exit and name in _costly:
            log.info("[pipeline] early-exit: skipping %s (score already >= %.2f)",
                     name, EARLY_EXIT_THRESHOLD)
            timings_ms[name] = 0.0
            continue

        t0 = time.monotonic()
        hyp_results[name] = module.evaluate(diff, signals, memory)
        timings_ms[name] = round((time.monotonic() - t0) * 1000, 1)

        log.debug("[pipeline] %s -> value=%s score=%.3f (%.0fms)",
                  name,
                  hyp_results[name].value,
                  hyp_results[name].score,
                  timings_ms[name])

        # Evaluate early-exit after the last "cheap" hypothesis
        if name == _EARLY_EXIT_AFTER:
            partial_score = _compute_anomaly_score(hyp_results)
            if partial_score >= EARLY_EXIT_THRESHOLD:
                early_exit = True
                log.info(
                    "[pipeline] early-exit triggered after %s: "
                    "partial_score=%.3f >= %.2f",
                    name, partial_score, EARLY_EXIT_THRESHOLD,
                )

    return hyp_results, early_exit, timings_ms


# MITRE ATT&CK tactic per hypothesis (config — consumed by build_iocs).
_HYP_TO_MITRE: dict[str, str] = {
    "persistence_detected": "TA0003",
    "c2_communication":     "TA0011",
    "code_injection":       "TA0005",
    "file_encryption":      "TA0040",
    "evasion_attempted":    "TA0005",
    "propagation":          "TA0008",
    "lolbins_abuse":        "T1059",   # Command and Scripting Interpreter
}


def _ioc_type(hyp_name: str, ev) -> str:
    """ELF IOC typing: syscall if runtime_signals, file_hash otherwise."""
    return "syscall" if ev.source == "runtime_signals" else "file_hash"


def _iocs_from_hypotheses(hyp_results: dict, memory: MemoryObservables) -> list[dict]:
    """Build the IOC list (delegates to the pure core, core/report.build_iocs)."""
    return build_iocs(
        hyp_results, _HYP_TO_MITRE, _ioc_type,
        memory_regions=memory.suspicious_regions,
    )


def _behavior_summary(hyp_results: dict, anomaly_score: float, duration_s: float) -> str:
    """ELF behavioural summary. Delegates to the pure core (core/report)."""
    return build_elf_summary(hyp_results, anomaly_score, duration_s)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def _detonate_elf(
    sample_path: Path, work_dir: Path,
) -> tuple[MemoryObservables, int | None, float, bool, Path]:
    """Strace the sample directly + parallel /proc forensics, RLIMIT_NPROC-capped.

    Returns (memory, exit_code, execution_duration_s, timeout_triggered, trace_log_path).
    """
    trace_log_path = work_dir / "trace.log"
    strace_cmd = (
        f"strace -f -tt -e trace=all -o {trace_log_path} "
        f"{sample_path} > {work_dir}/stdout.log 2>{work_dir}/stderr.log; "
        f"echo $? > {work_dir}/exit_code"
    )
    log.info("Running strace + sample (timeout=%ds)", TIMEOUT_S)

    # Thread for memory forensics during execution
    memory_result: list[MemoryObservables] = [MemoryObservables()]
    def _collect_memory():
        memory_result[0] = collect_memory_observables(
            str(sample_path), max_snapshots=5, interval_s=0.5
        )
    mem_thread = threading.Thread(target=_collect_memory, daemon=True)
    mem_thread.start()

    def _set_rlimits():
        # Cap process count inside the sandbox via RLIMIT_NPROC.
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))

    timeout_triggered = False
    exec_start = time.time()
    try:
        subprocess.run(["sh", "-c", strace_cmd], timeout=TIMEOUT_S, preexec_fn=_set_rlimits)
    except subprocess.TimeoutExpired:
        log.warning("Sample timed out after %ds", TIMEOUT_S)
        timeout_triggered = True
    execution_duration_s = time.time() - exec_start

    mem_thread.join(timeout=10)
    memory = memory_result[0]

    exit_code = None
    ec_path = work_dir / "exit_code"
    if ec_path.exists():
        try:
            exit_code = int(ec_path.read_text().strip())
        except ValueError:
            pass
    return memory, exit_code, execution_duration_s, timeout_triggered, trace_log_path


def _parse_trace(trace_log_path: Path):
    """Parse the strace log → (syscalls, sleep_cumulated_s, evasion_tells, network)."""
    trace_log = trace_log_path.read_text(errors="replace") if trace_log_path.exists() else ""
    syscalls = parse_strace_log(trace_log)
    sleep_cumulated = extract_sleep_cumulated(trace_log)
    evasion_tells = extract_evasion_tells(trace_log)
    network = extract_network(trace_log)
    log.info("network: %d tcp, %d udp flows", len(network.tcp_flows), len(network.udp_flows))
    return syscalls, sleep_cumulated, evasion_tells, network


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_analysis(job_id: str, s3_url: str) -> None:
    started_at = now_iso()
    t0 = time.time()

    # Working directory in /out (emptyDir volume)
    work_dir = Path("/out") / job_id[:8]
    work_dir.mkdir(parents=True, exist_ok=True)
    sample_path = work_dir / "sample.elf"

    timeout_triggered = False
    error_msg: str | None = None
    hyp_results: dict = {}
    early_exit: bool = False
    hypothesis_timings_ms: dict[str, float] = {}

    try:
        # 1. Download
        _download_sample(s3_url, sample_path)

        # 2. Snapshot BEFORE
        log.info("Taking snapshot BEFORE")
        snapshot_before = take_snapshot(relative_ts_s=0.0)

        # 3. Detonate (strace + sample, /proc forensics in parallel)
        (memory, exit_code, execution_duration_s, detonation_timeout,
         trace_log_path) = _detonate_elf(sample_path, work_dir)
        timeout_triggered = timeout_triggered or detonation_timeout

        # 4. Snapshot AFTER
        log.info("Taking snapshot AFTER")
        snapshot_after = take_snapshot(relative_ts_s=execution_duration_s)

        # 5. Parse strace
        syscalls, sleep_cumulated, evasion_tells, network = _parse_trace(trace_log_path)

        # 6. Diff
        diff = compute_diff(
            snapshot_before, snapshot_after,
            execution_duration_s=execution_duration_s,
            exit_code=exit_code,
        )
        signals = RuntimeSignals(
            syscalls_summary=syscalls,
            inotify_events=[],
            network=network,
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

        # 7. Hypotheses — pipeline v2 (ordered + early-exit)
        hyp_results, early_exit, hypothesis_timings_ms = _run_hypotheses_ordered(
            diff, signals, memory
        )

        anomaly_score = _compute_anomaly_score(hyp_results)
        iocs = _iocs_from_hypotheses(hyp_results, memory)
        behavior_summary = _behavior_summary(hyp_results, anomaly_score, execution_duration_s)

        # D1 guard — "benign" is only allowed when a normal execution was
        # actually observed (M4 liveness); silence escalates, never washes.
        total_syscalls = sum(s.call_count for s in syscalls)
        liveness_ok, liveness_note = execution_liveness(total_syscalls, exit_code)
        verdict, guard_reason = guarded_verdict(
            anomaly_score, THRESHOLD_MAL, THRESHOLD_SUS,
            liveness_ok=liveness_ok,
        )

        positives = [k for k, r in hyp_results.items() if r.value]
        log.info(
            "Hypotheses done: anomaly=%.2f verdict=%s guard=%s positive=%s early_exit=%s",
            anomaly_score,
            verdict,
            guard_reason,
            positives,
            early_exit,
        )

        # D-obs — greppable verdict line + beacon on the probable-miss signature.
        low_obs = low_observability_alert(
            verdict=verdict, anomaly_score=anomaly_score,
            duration_s=execution_duration_s, n_iocs=len(iocs), liveness_ok=liveness_ok,
        )
        log.info(
            "SANDBOX_VERDICT path=elf verdict=%s score=%.3f guard=%s liveness=%s "
            "dur=%.2fs syscalls=%d iocs=%d low_obs=%s",
            verdict, anomaly_score, guard_reason, liveness_ok,
            execution_duration_s, total_syscalls, len(iocs), low_obs,
        )
        if low_obs:
            log.warning(
                "SANDBOX_LOW_OBSERVABILITY path=elf reason=%s verdict=%s score=%.3f "
                "dur=%.2fs syscalls=%d iocs=%d — probable miss, do not trust silently",
                low_obs, verdict, anomaly_score, execution_duration_s,
                total_syscalls, len(iocs),
            )

    except Exception as exc:
        log.exception("Analysis failed: %s", exc)
        error_msg = str(exc)
        iocs = []
        behavior_summary = f"Analysis error: {exc}"
        anomaly_score = 0.0
        timeout_triggered = False
        early_exit = False
        hypothesis_timings_ms = {}
        hyp_results = {}
        # A failed analysis observed nothing — it must never read as benign.
        verdict = "error"
        guard_reason = "analysis_error"
        liveness_ok, liveness_note = False, "analysis failed"
        low_obs = None  # the error path is already surfaced via log.exception

    ended_at = now_iso()
    duration_s = time.time() - t0

    # 8. Build SandboxLayerResultEvent (GPE-ETNA contract)
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
        pipeline_version="v2",
        hypothesis_timings_ms=hypothesis_timings_ms,
        hyp_results=hyp_results,
        weights=WEIGHTS,
        verdict=verdict,
        meta_extra={
            "early_exit": early_exit,
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
    run_cli("Sandbox analysis agent", "Agent", log, run_analysis)


if __name__ == "__main__":
    main()
