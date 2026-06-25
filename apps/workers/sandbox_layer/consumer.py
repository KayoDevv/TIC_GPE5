"""sandbox-consumer — Kafka file.requested → one K8s Job per sample.

Detonation (strace + snapshots + hypotheses + publish) runs in the Job pod
(agent/run_*.py). Config via the env vars in the constants block below.
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

# Pod hardening knobs (env-overridable so dev can opt out).
RUNTIME_CLASS   = os.getenv("SANDBOX_RUNTIME_CLASS", "").strip() or None  # "gvisor" in prod, else runc
RUN_AS_USER     = int(os.getenv("SANDBOX_RUN_AS_USER", "10001"))          # 0 = root (legacy); image ships UID 10001
SINKHOLE_DNS_IP = os.getenv("SANDBOX_DNS_IP", "").strip() or None         # detach analysis pods to the sinkhole resolver
SECCOMP_TYPE    = os.getenv("SANDBOX_SECCOMP_TYPE", "RuntimeDefault").strip()  # or "Localhost" + charon-seccomp.json
SECCOMP_PROFILE = os.getenv("SANDBOX_SECCOMP_PROFILE", "charon-seccomp.json").strip()

# Egress gate (P0a): initContainer that holds the pod until egress is PROVABLY
# blocked, then detonates — fail-closed against the Calico startup race where a
# sample could exfiltrate before the NetworkPolicy is programmed. "host:port", empty disables.
EGRESS_GATE     = os.getenv("SANDBOX_EGRESS_GATE", "1.1.1.1:443").strip()

_EGRESS_GATE_SCRIPT = """
import os, socket, sys, time
host, _, port = os.environ["GATE_TARGET"].partition(":")
target = (host, int(port)); required = 3; deadline = time.time() + 30; streak = 0
while time.time() < deadline:
    try:
        socket.create_connection(target, timeout=2).close()  # reachable => egress OPEN
        streak = 0
        print("egress-gate: still reachable, waiting for NetworkPolicy...", flush=True)
    except OSError:
        streak += 1
        if streak >= required:
            print("egress-gate: blocked (policy enforced) -> detonate", flush=True)
            sys.exit(0)
    time.sleep(1)
sys.exit("egress-gate FAIL-CLOSED: %s still reachable after deadline" % (target,))
"""

# Endpoints injected into analysis pods — default to the consumer's own
# (override when the consumer runs outside the cluster).
AGENT_KAFKA_BOOTSTRAP = os.getenv("AGENT_KAFKA_BOOTSTRAP_SERVERS", KAFKA_BOOTSTRAP)
AGENT_MINIO_ENDPOINT  = os.getenv("AGENT_MINIO_ENDPOINT", MINIO_ENDPOINT)

# ---------------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------------

def _detect_file_type(s3_url: str) -> str:
    """Detect file type via magic bytes (HTTP Range 0-7): "elf", "pdf", or "unknown"."""
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
    """Load K8s config: K8S_API_SERVER override → in-cluster → local kubeconfig."""
    api_server = os.getenv("K8S_API_SERVER")
    if api_server:
        # In-cluster path with custom host (override from overlay).
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
            # No in-cluster token → kubeconfig
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


def _egress_gate_init(job_image: str) -> list | None:
    """P0a egress-gate initContainer (see EGRESS_GATE). None when disabled."""
    if not EGRESS_GATE:
        return None
    return [k8s_client.V1Container(
        name="egress-gate",
        image=job_image,
        image_pull_policy="IfNotPresent",
        command=["python3", "-c", _EGRESS_GATE_SCRIPT],
        env=[k8s_client.V1EnvVar(name="GATE_TARGET", value=EGRESS_GATE)],
        resources=k8s_client.V1ResourceRequirements(
            requests={"cpu": "50m", "memory": "32Mi"},
            limits={"cpu": "200m", "memory": "64Mi"},
        ),
        security_context=k8s_client.V1SecurityContext(
            run_as_user=RUN_AS_USER,
            run_as_group=RUN_AS_USER,
            run_as_non_root=(RUN_AS_USER != 0),
            allow_privilege_escalation=False,
            read_only_root_filesystem=True,
            capabilities=k8s_client.V1Capabilities(drop=["ALL"]),
            seccomp_profile=k8s_client.V1SeccompProfile(type="RuntimeDefault"),
        ),
    )]


def _analysis_container(
    job_image: str, agent_cmd: list[str], job_id: str, s3_url: str, email_context: dict,
) -> "k8s_client.V1Container":
    """Detonation container: non-root, cap-drop ALL + SYS_PTRACE only, RO rootfs, seccomp, tmpfs temp."""
    return k8s_client.V1Container(
        name="analysis",
        image=job_image,
        image_pull_policy="IfNotPresent",
        command=agent_cmd,
        args=["--job-id", job_id, "--s3-url", s3_url],
        env=[
            k8s_client.V1EnvVar(name="KAFKA_BOOTSTRAP_SERVERS", value=AGENT_KAFKA_BOOTSTRAP),
            k8s_client.V1EnvVar(name="KAFKA_TOPIC_OUT", value=TOPIC_OUT),
            k8s_client.V1EnvVar(name="MINIO_ENDPOINT", value=AGENT_MINIO_ENDPOINT),
            k8s_client.V1EnvVar(name="EMAIL_CONTEXT_JSON", value=json.dumps(email_context)),
        ],
        resources=k8s_client.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "512Mi"},
            limits={"cpu": "2000m", "memory": "2Gi", "ephemeral-storage": "2Gi"},
        ),
        security_context=k8s_client.V1SecurityContext(
            run_as_user=RUN_AS_USER,
            run_as_group=RUN_AS_USER,
            run_as_non_root=(RUN_AS_USER != 0),
            allow_privilege_escalation=False,
            read_only_root_filesystem=True,
            capabilities=k8s_client.V1Capabilities(drop=["ALL"], add=["SYS_PTRACE"]),
            seccomp_profile=(
                k8s_client.V1SeccompProfile(type="Localhost", localhost_profile=SECCOMP_PROFILE)
                if SECCOMP_TYPE == "Localhost"
                else k8s_client.V1SeccompProfile(type="RuntimeDefault")
            ),
        ),
        volume_mounts=[
            k8s_client.V1VolumeMount(name="scratch", mount_path="/out"),
            k8s_client.V1VolumeMount(name="tmp", mount_path="/tmp"),
            k8s_client.V1VolumeMount(name="var-tmp", mount_path="/var/tmp"),
        ],
    )


def _pod_volumes() -> list:
    """Scratch /out (1Gi) + tmpfs /tmp (256Mi) and /var/tmp (64Mi) — the RO rootfs needs writable temp."""
    return [
        k8s_client.V1Volume(name="scratch", empty_dir=k8s_client.V1EmptyDirVolumeSource(size_limit="1Gi")),
        k8s_client.V1Volume(name="tmp", empty_dir=k8s_client.V1EmptyDirVolumeSource(medium="Memory", size_limit="256Mi")),
        k8s_client.V1Volume(name="var-tmp", empty_dir=k8s_client.V1EmptyDirVolumeSource(medium="Memory", size_limit="64Mi")),
    ]


def _pod_dns():
    """Point analysis pods at the in-ns sinkhole resolver. (None, None) when unset."""
    if not SINKHOLE_DNS_IP:
        return None, None
    return "None", k8s_client.V1PodDNSConfig(
        nameservers=[SINKHOLE_DNS_IP],
        searches=[
            f"{K8S_NAMESPACE}.svc.cluster.local",
            "svc.cluster.local",
            "cluster.local",
        ],
        options=[
            k8s_client.V1PodDNSConfigOption(name="ndots", value="2"),
            k8s_client.V1PodDNSConfigOption(name="single-request-reopen"),
        ],
    )


def _create_analysis_job(
    batch_api: k8s_client.BatchV1Api,
    job_id: str,
    s3_url: str,
    email_context: dict,
    file_type: str = "unknown",
) -> str:
    """Create the batch/v1 Job. ELF → ELF agent; PDF and unknown → PDF agent
    (its format-agnostic static layer flags files disguised as PDF). Returns the Job name."""
    short_id = job_id.replace("-", "")[:12]
    job_name = f"charon-{short_id}"

    if file_type == "elf":
        job_image   = JOB_IMAGE
        agent_cmd   = ["python3", "/opt/agent/run_analysis.py"]
        file_type_label = "elf"
    else:
        job_image   = PDF_JOB_IMAGE
        agent_cmd   = ["python3", "/opt/agent/run_pdf_analysis.py"]
        file_type_label = "pdf"

    dns_policy, dns_config = _pod_dns()

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
                    # P0a — egress gate must pass BEFORE the analysis container, so
                    # the sample never executes while egress is open.
                    init_containers=_egress_gate_init(job_image),
                    # fsGroup=10001 so UID 10001 (agent) can write the emptyDir mounts.
                    security_context=k8s_client.V1PodSecurityContext(fs_group=10001),
                    runtime_class_name=RUNTIME_CLASS,
                    dns_policy=dns_policy,
                    dns_config=dns_config,
                    containers=[
                        _analysis_container(job_image, agent_cmd, job_id, s3_url, email_context),
                    ],
                    volumes=_pod_volumes(),
                ),
            ),
        ),
    )

    batch_api.create_namespaced_job(namespace=K8S_NAMESPACE, body=job)
    return job_name


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

_QUOTA_RETRY_DELAYS = [10, 20, 40]  # seconds between attempts (3 tries)


def _is_quota_exceeded(exc: Exception) -> bool:
    """Return True if the K8s exception is a 403 quota exceeded."""
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

    # File type detection before creating the Job
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
                continue  # retry
            # Non-quota error → no point retrying
            log.exception("Failed to create K8s Job", job_id=job_id, error=str(exc))
            break

    # All attempts exhausted → publish an error result so the job is not lost
    # silently (the validator will count it in the errors).
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
