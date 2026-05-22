"""sandbox-consumer — dispatcher Kafka → K8s Job.

Consomme file.requested, valide le payload, crée 1 batch/v1 Job par sample.
L'analyse réelle (strace + snapshots + hypothèses + publish) se fait dans
le pod Job (ubuntu-sandbox:v1 / agent/run_analysis.py).

Variables d'environnement (injectées par consumer-deployment.yaml) :
    KAFKA_BOOTSTRAP_SERVERS   default: kafka.kafka.svc.cluster.local:9092
    KAFKA_TOPIC_IN            default: file.requested
    KAFKA_GROUP_ID            default: charon-sandbox-v1
    K8S_NAMESPACE             default: sandbox
    SANDBOX_JOB_IMAGE         default: ghcr.io/kayodevv/ubuntu-sandbox:v1
    SANDBOX_TIMEOUT_S         default: 180
    MINIO_ENDPOINT            default: minio.minio.svc.cluster.local:9000
    KAFKA_TOPIC_OUT           default: sandbox_layer.result
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if sys.stderr.isatty()
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.kafka.svc.cluster.local:9092")
TOPIC_IN        = os.getenv("KAFKA_TOPIC_IN", "file.requested")
TOPIC_OUT       = os.getenv("KAFKA_TOPIC_OUT", "sandbox_layer.result")
GROUP_ID        = os.getenv("KAFKA_GROUP_ID", "charon-sandbox-v1")
K8S_NAMESPACE   = os.getenv("K8S_NAMESPACE", "sandbox")
JOB_IMAGE       = os.getenv("SANDBOX_JOB_IMAGE", "ghcr.io/kayodevv/ubuntu-sandbox:v1")
PDF_JOB_IMAGE   = os.getenv("SANDBOX_PDF_JOB_IMAGE", "ghcr.io/kayodevv/ubuntu-pdf-sandbox:v1")
TIMEOUT_S       = int(os.getenv("SANDBOX_TIMEOUT_S", "180"))
MINIO_ENDPOINT  = os.getenv("MINIO_ENDPOINT", "minio.minio.svc.cluster.local:9000")

# Hardening Tranche B (audit 2026-04-30) — all configurable so dev can opt-out.
#
# B.1 (V3) — RuntimeClass: empty string disables (default = runc).
#            Set to "gvisor" in prod overlay to enable userspace kernel sandboxing.
RUNTIME_CLASS   = os.getenv("SANDBOX_RUNTIME_CLASS", "").strip() or None
#
# B.2 (V5) — Non-root user: 0 = run as root (legacy), 10001 = run as `agent`.
#            The Dockerfile creates `agent` UID=10001. Setting RUN_AS_USER=10001
#            requires the image to be rebuilt with the hardened Dockerfile.
RUN_AS_USER     = int(os.getenv("SANDBOX_RUN_AS_USER", "10001"))
#
# B.3 (V7) — Sinkhole DNS: ClusterIP of sinkhole-dns service in this namespace.
#            Empty string disables and falls back to default cluster DNS.
SINKHOLE_DNS_IP = os.getenv("SANDBOX_DNS_IP", "").strip() or None
#
# B.4 (V2 strict) — Seccomp profile: "Localhost" + custom JSON, or "RuntimeDefault".
#            Tranche A applies RuntimeDefault by default; set to "Localhost" once
#            charon-seccomp.json is distributed to all nodes (seccomp-distributor).
SECCOMP_TYPE    = os.getenv("SANDBOX_SECCOMP_TYPE", "RuntimeDefault").strip()
SECCOMP_PROFILE = os.getenv("SANDBOX_SECCOMP_PROFILE", "charon-seccomp.json").strip()

# Endpoints injectés dans les pods d'analyse (peuvent différer du consumer
# quand le consumer tourne en dehors du cluster, ex. dev local hors K3s).
# Par défaut = mêmes valeurs que le consumer lui-même.
AGENT_KAFKA_BOOTSTRAP = os.getenv("AGENT_KAFKA_BOOTSTRAP_SERVERS", KAFKA_BOOTSTRAP)
AGENT_MINIO_ENDPOINT  = os.getenv("AGENT_MINIO_ENDPOINT", MINIO_ENDPOINT)

# ---------------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------------

def _detect_file_type(s3_url: str) -> str:
    """Détecte le type de fichier via magic bytes (HTTP Range request bytes=0-7).

    Retourne "elf", "pdf", ou "unknown".
    Timeout 10 s — ne bloque pas le dispatch si MinIO est lent.
    """
    try:
        req = urllib.request.Request(s3_url, headers={"Range": "bytes=0-7"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            header = resp.read(8)
        if header[:4] == b"\x7fELF":
            return "elf"
        if header[:4] == b"%PDF":
            return "pdf"
        log.warning("Unknown magic bytes — routing to PDF static analyzer (disguise detection)", magic=header[:4].hex())
        return "unknown"
    except Exception as exc:
        log.warning("File type detection failed — routing to PDF static analyzer", error=str(exc))
        return "unknown"


# ---------------------------------------------------------------------------
# K8s Job factory
# ---------------------------------------------------------------------------

def _load_k8s() -> k8s_client.BatchV1Api:
    """Charge la config K8s.

    Ordre de résolution :
    1. K8S_API_SERVER défini → token + CA standard, host overridé (override
       via overlay : ex. https://kubernetes.default.svc:443).
    2. Variables d'environnement standard in-cluster (cluster K8s "normal").
    3. Kubeconfig local (dev hors cluster, ex. make run-consumer).
    """
    api_server = os.getenv("K8S_API_SERVER")
    if api_server:
        # Chemin in-cluster avec host custom (override depuis overlay).
        from kubernetes.config.incluster_config import (
            SERVICE_CERT_FILENAME,
            SERVICE_TOKEN_FILENAME,
        )
        configuration = k8s_client.Configuration()
        configuration.host = api_server
        configuration.ssl_ca_cert = SERVICE_CERT_FILENAME
        configuration.verify_ssl = True
        try:
            with open(SERVICE_TOKEN_FILENAME) as f:
                token = f.read().strip()
            configuration.api_key = {"authorization": "Bearer " + token}
            configuration.api_key_prefix = {"authorization": ""}
        except FileNotFoundError:
            # Pas de token in-cluster → kubeconfig
            k8s_config.load_kube_config()
            log.info("k8s config: kubeconfig (K8S_API_SERVER set but no token)")
            return k8s_client.BatchV1Api()
        k8s_client.Configuration.set_default(configuration)
        log.info("k8s config: in-cluster (K8S_API_SERVER=%s)", api_server)
        return k8s_client.BatchV1Api()

    try:
        k8s_config.load_incluster_config()
        log.info("k8s config: in-cluster")
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()
        log.info("k8s config: kubeconfig")
    return k8s_client.BatchV1Api()


def _create_analysis_job(
    batch_api: k8s_client.BatchV1Api,
    job_id: str,
    s3_url: str,
    email_context: dict,
    file_type: str = "unknown",
) -> str:
    """Crée un batch/v1 Job K8s pour analyser un sample.

    Sélectionne automatiquement l'image et l'agent selon le type de fichier :
      "elf"      → ubuntu-sandbox:v1      + run_analysis.py
      "pdf" / *  → ubuntu-pdf-sandbox:v1  + run_pdf_analysis.py

    Le pipeline PDF est le DÉFAUT — y compris pour les magic "unknown". Sa
    couche statique (missing_pdf_magic, embedded_magic, entropy) est un
    analyseur d'octets format-agnostique qui flague les fichiers déguisés
    (ex. HTML/script maquillé en .pdf = évasion). L'agent ELF reste réservé
    aux vrais binaires ELF (\\x7fELF), qu'il est seul à savoir exécuter.

    Retourne le nom du Job créé.
    """
    short_id = job_id.replace("-", "")[:12]
    job_name = f"charon-{short_id}"

    # ELF → agent ELF ; PDF ET unknown/déguisé → agent PDF (couche statique
    # généraliste qui détecte les fichiers mentant sur leur format).
    if file_type == "elf":
        job_image   = JOB_IMAGE
        agent_cmd   = ["python3", "/opt/agent/run_analysis.py"]
        file_type_label = "elf"
    else:
        job_image   = PDF_JOB_IMAGE
        agent_cmd   = ["python3", "/opt/agent/run_pdf_analysis.py"]
        file_type_label = "pdf"

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name,
            namespace=K8S_NAMESPACE,
            labels={
                "app.kubernetes.io/part-of": "charon",
                "charon.io/role": "analysis",
                "charon.io/job-id": job_id,
                "charon.io/file-type": file_type_label,
            },
        ),
        spec=k8s_client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=120,
            active_deadline_seconds=TIMEOUT_S,
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(
                    labels={
                        "charon.io/role": "analysis",
                        "charon.io/job-id": job_id,
                    }
                ),
                spec=k8s_client.V1PodSpec(
                    restart_policy="Never",
                    automount_service_account_token=False,
                    # fsGroup=10001 makes K8s chgrp the volume mounts (/tmp,
                    # /var/tmp, /out emptyDirs) so UID 10001 (agent) can write
                    # to them. Without this, the volumes default to root:root
                    # and the sample cannot create files in WATCHED_PATHS.
                    security_context=k8s_client.V1PodSecurityContext(
                        fs_group=10001,
                    ),
                    # Hardening Tranche B — V3 (audit 2026-04-30):
                    # RuntimeClass = gvisor en prod (userspace kernel sandbox).
                    # None = falls back to runc (default actuel).
                    runtime_class_name=RUNTIME_CLASS,
                    # Hardening Tranche B — V7: sinkhole DNS. dnsPolicy=None
                    # detaches the pod from the cluster's default DNS, dnsConfig
                    # explicitly points to the in-namespace sinkhole-dns service.
                    # External names return NXDOMAIN; *.svc.cluster.local still
                    # resolves through the sinkhole's upstream forward.
                    dns_policy="None" if SINKHOLE_DNS_IP else None,
                    dns_config=(
                        k8s_client.V1PodDNSConfig(
                            nameservers=[SINKHOLE_DNS_IP],
                            searches=[
                                f"{K8S_NAMESPACE}.svc.cluster.local",
                                "svc.cluster.local",
                                "cluster.local",
                            ],
                            options=[
                                k8s_client.V1PodDNSConfigOption(
                                    name="ndots", value="2"),
                                k8s_client.V1PodDNSConfigOption(
                                    name="single-request-reopen"),
                            ],
                        ) if SINKHOLE_DNS_IP else None
                    ),
                    containers=[
                        k8s_client.V1Container(
                            name="analysis",
                            image=job_image,
                            image_pull_policy="IfNotPresent",
                            command=agent_cmd,
                            args=[
                                "--job-id", job_id,
                                "--s3-url", s3_url,
                            ],
                            env=[
                                k8s_client.V1EnvVar(
                                    name="KAFKA_BOOTSTRAP_SERVERS",
                                    value=AGENT_KAFKA_BOOTSTRAP,
                                ),
                                k8s_client.V1EnvVar(
                                    name="KAFKA_TOPIC_OUT",
                                    value=TOPIC_OUT,
                                ),
                                k8s_client.V1EnvVar(
                                    name="MINIO_ENDPOINT",
                                    value=AGENT_MINIO_ENDPOINT,
                                ),
                                k8s_client.V1EnvVar(
                                    name="EMAIL_CONTEXT_JSON",
                                    value=json.dumps(email_context),
                                ),
                            ],
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"cpu": "500m", "memory": "512Mi"},
                                limits={
                                    "cpu": "2000m",
                                    "memory": "2Gi",
                                    "ephemeral-storage": "2Gi",
                                },
                            ),
                            # Hardening (audit 2026-04-30) — combined Tranches A + B:
                            #   Tranche A:
                            #     seccomp           → RuntimeDefault (Tranche A) or
                            #                         Localhost charon-seccomp.json (Tranche B)
                            #     readOnlyRootFs    → agent /opt/agent/* immutable at runtime
                            #     allowPrivEsc      → no_new_privs, blocks setuid escalation
                            #     caps drop=ALL     → no CAP_SYS_ADMIN/MODULE/etc.
                            #     caps add=SYS_PTRACE → strace requirement only
                            #   Tranche B:
                            #     runAsUser=10001   → agent runs as non-root `agent`
                            #                         (Dockerfile.agent creates the user)
                            #     SYS_PTRACE on file (setcap) + ambient cap propagation
                            #                         allow strace to work as non-root
                            security_context=k8s_client.V1SecurityContext(
                                run_as_user=RUN_AS_USER,
                                run_as_group=RUN_AS_USER,
                                run_as_non_root=(RUN_AS_USER != 0),
                                allow_privilege_escalation=False,
                                read_only_root_filesystem=True,
                                capabilities=k8s_client.V1Capabilities(
                                    drop=["ALL"],
                                    add=["SYS_PTRACE"],
                                ),
                                seccomp_profile=(
                                    k8s_client.V1SeccompProfile(
                                        type="Localhost",
                                        localhost_profile=SECCOMP_PROFILE,
                                    )
                                    if SECCOMP_TYPE == "Localhost"
                                    else k8s_client.V1SeccompProfile(
                                        type="RuntimeDefault",
                                    )
                                ),
                            ),
                            volume_mounts=[
                                k8s_client.V1VolumeMount(
                                    name="scratch",
                                    mount_path="/out",
                                ),
                                # Hardening Tranche A — V6 :
                                # rootfs read-only → /tmp doit rester writable pour
                                # Python tempfile, gcc temp, pip cache, etc. tmpfs en
                                # mémoire (256Mi) compté dans le memory limit du pod.
                                k8s_client.V1VolumeMount(
                                    name="tmp",
                                    mount_path="/tmp",
                                ),
                                k8s_client.V1VolumeMount(
                                    name="var-tmp",
                                    mount_path="/var/tmp",
                                ),
                            ],
                        )
                    ],
                    volumes=[
                        k8s_client.V1Volume(
                            name="scratch",
                            empty_dir=k8s_client.V1EmptyDirVolumeSource(
                                size_limit="1Gi"
                            ),
                        ),
                        k8s_client.V1Volume(
                            name="tmp",
                            empty_dir=k8s_client.V1EmptyDirVolumeSource(
                                medium="Memory",
                                size_limit="256Mi",
                            ),
                        ),
                        k8s_client.V1Volume(
                            name="var-tmp",
                            empty_dir=k8s_client.V1EmptyDirVolumeSource(
                                medium="Memory",
                                size_limit="64Mi",
                            ),
                        ),
                    ],
                ),
            ),
        ),
    )

    batch_api.create_namespaced_job(namespace=K8S_NAMESPACE, body=job)
    return job_name


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

_QUOTA_RETRY_DELAYS = [10, 20, 40]  # secondes entre chaque tentative (3 essais)


def _is_quota_exceeded(exc: Exception) -> bool:
    """Retourne True si l'exception K8s est un 403 quota exceeded."""
    from kubernetes.client.exceptions import ApiException
    return (
        isinstance(exc, ApiException)
        and exc.status == 403
        and "exceeded quota" in str(exc.body)
    )


async def _handle(
    payload: dict,
    batch_api: k8s_client.BatchV1Api,
    producer: AIOKafkaProducer,
) -> None:
    job_id = payload.get("job_id", str(uuid.uuid4()))
    s3_url = payload.get("s3_url", "")
    email_context = payload.get("email_context", {})

    log.info("Dispatching job", job_id=job_id, s3_url=s3_url[:60])

    if not s3_url:
        log.error("Missing s3_url — skipping", job_id=job_id)
        return

    # Détection du type de fichier avant de créer le Job
    file_type = _detect_file_type(s3_url)
    log.info("File type detected", job_id=job_id, file_type=file_type)

    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _QUOTA_RETRY_DELAYS, start=1):
        if delay:
            log.warning(
                "Quota exceeded — retry after delay",
                job_id=job_id,
                attempt=attempt,
                delay_s=delay,
            )
            await asyncio.sleep(delay)
        try:
            job_name = _create_analysis_job(batch_api, job_id, s3_url, email_context, file_type)
            log.info("K8s Job created", job_id=job_id, job_name=job_name)
            return
        except Exception as exc:
            last_exc = exc
            if _is_quota_exceeded(exc):
                continue  # réessayer
            # Erreur non-quota → pas la peine de réessayer
            log.exception("Failed to create K8s Job", job_id=job_id, error=str(exc))
            break

    # Toutes les tentatives épuisées → publier un résultat d'erreur pour ne pas
    # perdre le job silencieusement (le validator le comptera dans les erreurs).
    log.error(
        "K8s Job creation failed after retries — publishing error result",
        job_id=job_id,
        attempts=attempt,
        error=str(last_exc),
    )
    error_result = {
        "job_id": job_id,
        "behavior_summary": "",
        "iocs": [],
        "timeout_triggered": False,
        "error": f"quota_exceeded_after_{attempt}_attempts",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await producer.send_and_wait(
        TOPIC_OUT,
        value=json.dumps(error_result).encode("utf-8"),
        key=job_id.encode("utf-8"),
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run() -> None:
    batch_api = _load_k8s()

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)

    await consumer.start()
    await producer.start()
    log.info("Consumer started", topic=TOPIC_IN, bootstrap=KAFKA_BOOTSTRAP)

    try:
        async for msg in consumer:
            payload = msg.value
            if not isinstance(payload, dict) or "job_id" not in payload:
                log.warning("Invalid message skipped")
                continue
            try:
                await _handle(payload, batch_api, producer)
            except Exception:
                log.exception("Unexpected error", job_id=payload.get("job_id"))
    finally:
        await consumer.stop()
        await producer.stop()
        log.info("Consumer stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Shutdown requested")


if __name__ == "__main__":
    main()
