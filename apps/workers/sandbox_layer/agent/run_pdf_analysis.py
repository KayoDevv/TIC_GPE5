"""Agent d'analyse PDF — tourne dans le pod K8s ubuntu-pdf-sandbox:v1.

Reçoit --job-id et --s3-url en arguments CLI.
Variables d'environnement : KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_OUT,
                            MINIO_ENDPOINT, EMAIL_CONTEXT_JSON.

Pipeline multi-couches (defense-in-depth) :

    1. Télécharge le sample depuis MinIO (URL presigned)

    2. COUCHE STATIQUE — sondes orthogonales sur les octets bruts :
         a) pdfid (Didier Stevens) — règles combinatoires sur structure PDF
         b) stream_entropy v2 — pic d'entropie localisé (payload caché)
         c) embedded_magic — ELF/PE/ZIP/etc. embarqués à offset > 0
       Agrégation MAX → pdf_static_indicators (poids 0.30)

    3. Snapshot AVANT

    4. COUCHE DYNAMIQUE A — `strace -f mutool draw /sample.pdf`
         Rend les pages, déclenche bugs de parseur, exerce zlib/JPEG/JBIG2.
         Catch les CVEs mupdf, malicious qui exploitent le rendu.

    4-bis. COUCHE DYNAMIQUE B — `strace -f node /opt/agent/pdf_runner.js`
         Extrait le JS du PDF via PDF.js, l'exécute dans Node vm avec
         contexte Adobe stubbé. Les appels app.launchURL / this.submitForm
         déclenchent de VRAIS syscalls réseau visibles par strace.
         Catch les polymorphes JS-based invisibles aux couches statique
         et mutool.

    5. Snapshot APRÈS

    6. Parse strace — UNION des deux traces (A ∪ B) pour que les 7 hypothèses
       comportementales voient n'importe quel signal, peu importe la couche
       d'origine. Aucune couche supprimée, perception élargie.

    7. 7 hypothèses comportementales (persistence, c2, injection, encryption,
       evasion, propagation, lolbins) + pdf_static_indicators → anomaly_score

    8. Construit SandboxLayerResultEvent + IOCs

    9. Publie sur sandbox_layer.result
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
# Post-Option-B (Kafka/MinIO in-cluster) : seul l'endpoint K8s service est légitime.
# L'IP host 172.16.249.133 a été retirée — plus de bridge docker-compose host.
_DEFAULT_ALLOWED_HOSTS = "minio.minio.svc.cluster.local"
ALLOWED_DOWNLOAD_HOSTS = frozenset(
    h.strip() for h in os.getenv("ALLOWED_DOWNLOAD_HOSTS", _DEFAULT_ALLOWED_HOSTS).split(",")
    if h.strip()
)

# ---------------------------------------------------------------------------
# Poids PDF — rééquilibrés pour intégrer pdf_static (poids 0.15)
# Les comportements runtime restent présents mais le signal statique est fort
# pour les PDFs évasifs qui ne déclenchent pas de syscalls suspects.
# ---------------------------------------------------------------------------

PDF_WEIGHTS: dict[str, float] = {
    # Comportemental — 7 hypothèses = 0.70 total
    # Identiques quelle que soit la source du fichier (ELF embarqué, JS, etc.)
    "persistence_detected":  0.12,
    "c2_communication":      0.12,
    "code_injection":        0.10,
    "lolbins_abuse":         0.10,
    "file_encryption":       0.08,
    "evasion_attempted":     0.08,
    "propagation":           0.10,
    # Statique format-spécifique — signal complémentaire, jamais dominant
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
    score = sum(
        PDF_WEIGHTS.get(k, 0.0) * r.score
        for k, r in hyp_results.items()
    )
    return round(min(score, 1.0), 3)


# Bandes de verdict. Le sandbox est un tie-breaker : il ne tranche "malicious"
# qu'avec un signal fort, "benign" qu'en l'absence totale de signal, et renvoie
# tout l'entre-deux ambigu au LLM (qui, lui, a l'email_context) via
# "needs_more_context".
_VERDICT_MALICIOUS = 0.15
_VERDICT_SUSPICIOUS = 0.04


def _verdict_band(anomaly_score: float) -> str:
    if anomaly_score >= _VERDICT_MALICIOUS:
        return "malicious"
    if anomaly_score >= _VERDICT_SUSPICIOUS:
        return "needs_more_context"
    return "benign"


# Traduction clé-de-règle → explication en langage clair (pour le LLM et l'UI).
# La clé est le dernier segment du field_path d'evidence.
_SIGNAL_EXPLAIN: dict[str, str] = {
    # Déguisement / structure
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
    # Exécution / contenu actif
    "js_auto_triggered":        "JavaScript exécuté automatiquement à l'ouverture (/OpenAction) — sans interaction utilisateur",
    "js_embedded":              "JavaScript embarqué (passif)",
    "dropper_with_payload":     "Fichier embarqué couplé à un déclencheur d'exécution (pattern dropper)",
    "dropper_auto_exec":        "Fichier embarqué exécuté automatiquement à l'ouverture (pattern dropper)",
    "embedded_file_alone":      "Fichier embarqué dans le PDF",
    "launch_action":            "Action /Launch (exécution d'un programme externe) — quasi toujours malveillant",
    "jbig2_colors_overflow":    "Pattern d'exploit JBIG2 (CVE-2009-0658)",
    "rich_media":               "Contenu RichMedia/Flash embarqué",
    "xfa_form":                 "Formulaire XFA (vecteur d'exécution)",
    # URI / réseau
    "exec_extension":           "Lien pointant vers un exécutable (.exe/.scr/.ps1/...)",
    "bare_ip":                  "Lien vers une adresse IP nue (contournement DNS/réputation)",
    "fileshare":                "Lien vers un service de partage de fichiers fréquemment abusé",
    "free_hosting":             "Lien vers de l'hébergement gratuit/jetable (pattern phishing)",
    "obfuscated_b64_param":     "URL avec paramètres base64 obfusqués",
    "shortener":                "Lien raccourci masquant la destination réelle",
    "suspicious_tld":           "Domaine sur un TLD fréquemment abusé pour le phishing",
    "raw_hoster":               "Lien vers un hébergeur de contenu brut",
    "external_url":             "Lien externe vers un domaine non catégorisé",
    # Génériques
    "local_peak":               "Pic d'entropie localisé (contenu compressé/chiffré)",
}


def _explain_signal(field_path: str) -> str | None:
    """field_path → explication en clair, ou None si non mappé."""
    key = field_path.split("[")[-1].rstrip("]").split(".")[-1]
    return _SIGNAL_EXPLAIN.get(key)


def _build_narrative(hyp_results: dict, anomaly_score: float, duration_s: float) -> tuple[str, str]:
    """Construit (verdict, narrative) lisible par le LLM et l'UI.

    Le narratif mène par la bande de verdict, traduit les signaux en langage
    clair (avec la valeur concrète : URL, déguisement), et donne au LLM une
    consigne de corrélation pour la bande ambiguë.
    """
    verdict = _verdict_band(anomaly_score)

    # Signaux uniques en clair (dédupliqués par explication), avec leur valeur.
    signals: list[str] = []
    seen: set[str] = set()
    for r in hyp_results.values():
        for ev in r.evidence:
            expl = _explain_signal(ev.field_path)
            if not expl or expl in seen:
                continue
            seen.add(expl)
            # Pour les URI, on joint la valeur observée (utile au LLM).
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

        # 2. Layer statique multi-sondes (avant exécution — aucune déclenche rien)
        #    Cinq sondes indépendantes regardent des aspects différents du fichier :
        #      a) pdfid          → règles combinatoires sur structure PDF
        #      b) stream_entropy → payload chiffré/obfusqué local (générique)
        #      c) embedded_magic → executables embarqués (générique)
        #      d) pdf_uri        → actions URI vers fileshare/exe/IP nue (phishing)
        #      e) pdf_anomaly    → anomalies structurelles (xref cassée, ratio obj/pages)
        #    Le score retenu est le MAX — un seul signal positif suffit à alerter.
        log.info("Running multi-probe static analysis")
        t_static = time.monotonic()
        pdfid_result    = pdf_static_evaluate(sample_path)
        entropy_result  = entropy_evaluate(sample_path)
        embedded_result = embedded_evaluate(sample_path)
        uri_result      = uri_evaluate(sample_path)
        anomaly_result  = anomaly_evaluate(sample_path)

        # Agrégation : on prend le score max + on fusionne les evidences
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

        # 3. Snapshot AVANT
        log.info("Taking snapshot BEFORE")
        snapshot_before = take_snapshot(relative_ts_s=0.0)

        # 4. COUCHE DYNAMIQUE A — mutool draw straced
        # Rend les pages du PDF, déclenche les bugs de parseur, exerce
        # le code de décompression (zlib, JPEG, JBIG2) → catch les CVEs mupdf.
        # Pas d'exécution de JS PDF (mutool draw ne le fait pas).
        trace_mutool_path = work_dir / "trace_mutool.log"
        trace_pdfjs_path  = work_dir / "trace_pdfjs.log"

        per_step_timeout = max(TIMEOUT_S // 2, 30)

        mutool_cmd = [
            "strace", "-f", "-tt", "-e", "trace=all", "-o", str(trace_mutool_path),
            "mutool", "draw", "-o", "/dev/null", str(sample_path),
        ]
        log.info("[layer A] strace + mutool draw (timeout=%ds)", per_step_timeout)

        # Memory forensics en parallèle (mutool process)
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

        # 4-bis. COUCHE DYNAMIQUE B — Node + PDF.js straced
        # Exécute le JavaScript embarqué dans le PDF (extraction par PDF.js,
        # exécution dans vm Node avec contexte Adobe stubbé).
        # Catch les polymorphes JS-based qui sont invisibles au statique
        # ET à mutool (qui ne lance pas le JS).
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

        # Exit code retenu pour le rapport : on prend mutool (couche A) en référence,
        # le pdfjs.js exit étant souvent != 0 sur PDFs malformés (signal lui-même).
        exit_code = exit_code_mutool
        if exit_code is not None:
            (work_dir / "exit_code").write_text(str(exit_code))
        log.info(
            "Exec done: mutool exit=%s pdfjs exit=%s duration=%.1fs",
            exit_code_mutool, exit_code_pdfjs, execution_duration_s,
        )

        # 5. Snapshot APRÈS
        log.info("Taking snapshot AFTER")
        snapshot_after = take_snapshot(relative_ts_s=execution_duration_s)

        # 6. Parse strace — UNION des deux traces (couche A + couche B)
        # Les 7 hypothèses comportementales voient l'union des syscalls,
        # donc un signal capté par n'importe quelle couche fait fire l'hypothèse.
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

        # 8. Hypothèses comportementales (réutilisées telles quelles sur les
        #    syscalls de mutool — si mutool est exploité, les signaux C2/injection
        #    apparaissent exactement comme pour un ELF malicieux)
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

    # IOCs depuis les hypothèses positives
    iocs = []
    hyp_to_mitre = {
        "persistence_detected":  "TA0003",
        "c2_communication":      "TA0011",
        "code_injection":        "TA0005",
        "file_encryption":       "TA0040",
        "evasion_attempted":     "TA0005",
        "propagation":           "TA0008",
        "lolbins_abuse":         "T1059",
        "pdf_static_indicators": "T1027",
    }
    for hyp_name, result in hyp_results.items():
        if not result.value:
            continue
        mitre = hyp_to_mitre.get(hyp_name, "TA0000")
        for ev in result.evidence:
            iocs.append({
                "type": "pdf_indicator" if hyp_name == "pdf_static_indicators" else "syscall",
                "value": ev.value[:256],
                "mitre_tactic": mitre,
                "description": f"{hyp_name}: {ev.field_path}",
            })

    event = {
        "job_id": job_id,
        "verdict": verdict,
        "iocs": iocs,
        "behavior_summary": behavior_summary,
        "email_context": EMAIL_CONTEXT,
        "timeout_triggered": timeout_triggered,
        "timestamp": ended_at,
        "_meta": {
            "anomaly_score": anomaly_score,
            "duration_s": round(duration_s, 2),
            "error": error_msg,
            "file_type": "pdf",
            "pipeline_version": "v2-pdf",
            "hypothesis_timings_ms": hypothesis_timings_ms,
            "hypothesis_scores": {
                k: round(r.score, 3) for k, r in hyp_results.items()
            },
        },
    }

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
