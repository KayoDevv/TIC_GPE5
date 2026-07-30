# Sandbox Layer: Behavioural Analysis (slow path)

**Tech:** Python · K8s `batch/v1 Job` · strace · state-diff · `/proc` forensics

**Business context:** Runs alongside the ML Layer whenever a file is submitted. Captures
malicious behaviour that is not statically visible (obfuscation, payloads downloaded at
runtime, persistence, C2). Its `sandbox_layer.result` output is consumed by the LLM Layer to
enrich its semantic reasoning.

> For how the code is **built** (functional core / imperative shell, the ELF vs PDF paths,
> how to extend), read [`ARCHITECTURE.md`](./ARCHITECTURE.md). This README covers how to
> **deploy and run** it.

**Kafka events:**
- **Consumes:** `file.requested`
- **Produces:** `sandbox_layer.result` — `SandboxLayerResultEvent` (MITRE ATT&CK-tagged IOCs,
  `behavior_summary`, `email_context` pass-through, `timeout_triggered`, `verdict` for PDF)

---

## Architecture: Job-per-analysis

```
file.requested
      │
      ▼
sandbox-consumer (Deployment, 1-3 replicas via KEDA)
      │  creates 1 batch/v1 Job per sample (routes by magic bytes)
      ▼
ubuntu-sandbox (ELF)  /  ubuntu-pdf-sandbox (PDF)  pod (K8s Job, release-tagged)
      │  run_analysis.py  /  run_pdf_analysis.py
      ├── download sample (MinIO presigned URL)
      ├── snapshot BEFORE  (FS SHA-256, processes, sockets, crontab)
      ├── strace -f + sample  ──┐
      ├── /proc forensics       │  in parallel (thread)
      ├── snapshot AFTER    ────┘
      ├── 7 scored hypotheses → anomaly_score → verdict band
      └── publishes SandboxLayerResultEvent → sandbox_layer.result
```

---

## Analysis process (state-diff)

1. **Snapshot BEFORE** — SHA-256 hashing over the FS (`/etc /home /tmp /var /opt`), `ps`, `ss`, crontab, systemd units
2. **Instrumented execution** — `strace -f -tt -e trace=all` with the `SYS_PTRACE` cap, timeout `SANDBOX_TIMEOUT_S` (default: 120s)
3. **Memory forensics** — read `/proc/[pid]/maps` + `/proc/[pid]/mem`, extract RWX regions, decoded strings
4. **Snapshot AFTER** — same scope
5. **Diff** — files created/modified/deleted, new processes, opened sockets, crontab/systemd/persistence changes
6. **7 hypotheses** — pure functions `evaluate(diff, signals, memory) -> HypothesisResult`, ELF weights (`DEFAULT_WEIGHTS`):
   - `persistence_detected` (0.25) · `c2_communication` (0.20) · `code_injection` (0.20)
   - `lolbins_abuse` (0.15) · `file_encryption` (0.10) · `evasion_attempted` (0.05) · `propagation` (0.05)
   - PDF adds 5 static probes aggregated into `pdf_static_indicators` (see `ARCHITECTURE.md`)
7. **anomaly_score** — weighted sum of the scores → 3-band verdict: `malicious` ≥ 0.15, `needs_more_context` ≥ 0.04, otherwise `benign`

**Linux capture (v1):** strace syscalls + state-diff + `/proc` forensics
**Windows capture (v2):** ETW via Sysmon — out of scope for v1

---

## Code structure

```
sandbox_layer/
├── consumer.py              # Kafka dispatcher → batch/v1 Job (routes ELF/PDF by magic bytes)
├── Dockerfile.consumer      # Image ghcr.io/kayodevv/charon-sandbox-consumer
├── Dockerfile.agent         # Image ghcr.io/kayodevv/ubuntu-sandbox (ELF)
├── Dockerfile.pdf-agent     # Image ghcr.io/kayodevv/ubuntu-pdf-sandbox (PDF)
├── ARCHITECTURE.md          # The maintainer's map (how it's built)
├── contract/
│   ├── CONTRACT_VERSION
│   └── golden/              # Reference fixtures
└── agent/
    ├── run_analysis.py      # ELF Job entrypoint
    ├── run_pdf_analysis.py  # PDF Job entrypoint
    ├── snapshot.py          # take_snapshot() / compute_diff()
    ├── strace_collector.py  # parse_strace_log() / extract_sleep_cumulated()
    ├── memory.py            # collect_memory_observables() via /proc
    ├── pdf_runner.js        # runs the PDF's embedded JS (Node + PDF.js)
    ├── core/                # PURE core (golden-tested): scoring.py, report.py
    ├── models/              # Data contract (frozen Pydantic): snapshot/signals/memory/constants
    └── hypotheses/          # 7 behavioural + 5 PDF static probes + _types.py (contract)
```

---

## Local dev

### Prerequisites

The only thing required by hand is **`make`** (`sudo apt install build-essential`) —
it bootstraps everything else. `make configuration` then installs K3s, kubectl,
Helm, Docker, k9s and the Python deps automatically.

### First install (fresh machine) — 3 steps

```bash
# 1. Install everything: apt deps + K3s + kubectl + Helm + Docker + k9s
#    + Python deps + kubeconfig + DNS fix. Idempotent.
make configuration

# >>> If Docker was just installed: LOG OUT / LOG BACK IN (or `newgrp docker`)
# >>> before the next steps, so the docker group becomes active.

# 2. Deploy the in-cluster infra in the right order: KEDA -> Kafka -> MinIO
make deploy

# 3. Launch the stack: build/import images + deploy the dev overlay (workers)
make launch
```

> `make configuration` runs `fix-dns-fai` automatically. Behind an SFR/Numericable
> box you can also re-run it standalone at any time: `make fix-dns-fai`.

> `make deploy` and `make launch` re-run `setup-kubeconfig` / `setup-keda` every time.
> If everything is fine: ~1s overhead. Otherwise: auto-fix without intervention.

> Legacy aliases still work: `make bootstrap-k3s` (≈ kubeconfig + KEDA),
> `make bootstrap-in-cluster` (≈ Kafka + MinIO), `make deploy-dev` (workers only).

### Daily use

```bash
# Re-deploy after a change (rebuild images + apply manifests)
make deploy-dev

# Watch the consumer
kubectl logs -n sandbox -l app=sandbox-consumer -f

# Corpus validation (see scripts/validation/README.md)
make validate-run RUN_ID=pilot7 REPS=1 CORPUS=validation/corpus MAX_INFLIGHT=15 IDLE_TIMEOUT=300
```

### Main orchestrators

| Target | Role |
|---|---|
| `make configuration` | Installs everything (apt deps, K3s, kubectl, Helm, Docker, k9s, Python) + kubeconfig + DNS fix |
| `make deploy` | Deploys the in-cluster infra in order: KEDA → Kafka → MinIO |
| `make launch` | Builds/imports images + deploys the workers (dev overlay) |
| `make fix-dns-fai` | Fixes SFR/Numericable NXDOMAIN hijacking on `*.cluster.local` (idempotent) |

### Individual targets

| Target | Role | When to use |
|---|---|---|
| `make install-k3s` | Installs K3s single-node | Standalone, called by `configuration` |
| `make install-kubectl` | kubectl standalone (apt repo, not the K3s wrapper) | Standalone, called by `configuration` |
| `make install-helm` / `install-docker` / `install-k9s` | Tooling install (idempotent) | Standalone, called by `configuration` |
| `make setup-kubeconfig` | Copies `/etc/rancher/k3s/k3s.yaml` → `~/.kube/config` | `x509: certificate signed by unknown authority` error |
| `make setup-keda` | Installs KEDA via Helm (namespace `keda`) | consumer `ScaledObject` in CrashLoop / KEDA missing |
| `make setup-kafka` / `deploy-minio` | Deploy Kafka / MinIO individually | Bring up one infra component |
| `make bootstrap-k3s` | Alias: kubeconfig + KEDA | Legacy / fresh K3s prep |
| `make bootstrap-in-cluster` | Alias: Kafka + MinIO | Legacy / infra only |
| `make setup-minio-operator` | **Deprecated** (StatefulSet pivot 2026-05-13) | Not used by any flow |

### Known troubleshooting

- **`x509: certificate signed by unknown authority`**: an old `~/.kube/config` points at a destroyed cluster. Fix: `make setup-kubeconfig`.
- **consumer `ScaledObject` in error / no scaling**: KEDA missing from the cluster. Fix: `make setup-keda`.
- **sandbox pods `CrashLoopBackOff` (Kafka unreachable)**: check `kubectl get pods -n kafka` (the Bitnami broker must be `Running`) and that the NetworkPolicies allow egress to `kafka.kafka.svc.cluster.local:9092`.
- **`helm: command not found`** during `setup-keda`: install Helm 3 ([helm.sh/docs/intro/install](https://helm.sh/docs/intro/install/)), or just run `make install-helm`.
- **MinIO `CrashLoopBackOff` / pods resolving `*.cluster.local` to a public IP** (SFR/Numericable NXDOMAIN hijacking): the K3s `resolv.conf` does not reset on cluster restart. Fix: `make fix-dns-fai` (forces `1.1.1.1`/`8.8.8.8`, idempotent).
- **`permission denied` on `docker` / `docker save`**: the docker group is not active in the current session. Log out / back in (or `newgrp docker`) after `make configuration`.

### In-cluster networking

Kafka and MinIO run in-cluster:
- **Kafka**: Bitnami Helm chart, namespace `kafka`, service `kafka.kafka.svc.cluster.local:9092`
- **MinIO**: standalone StatefulSet, namespace `minio`, service `minio.minio.svc.cluster.local:9000`

The consumer and the analysis pods reach these services via K8s DNS. The
`analysis-egress` / `consumer-egress` NetworkPolicies (dev overlay) allow
egress only to those 2 namespaces + DNS + the K8s API — all other traffic is blocked by
`deny-all-default` (enforced by Calico).

---

## Analysis pod isolation

| Parameter | Value |
|---|---|
| Capability | `SYS_PTRACE` only |
| Seccomp | `charon-seccomp.json` (whitelist) |
| NetworkPolicy | `analysis-deny-egress` — DENY-ALL egress |
| Hard timeout | `activeDeadlineSeconds: 180` |
| Resources | requests 500m/512Mi · limits 2000m/2Gi |

### NetworkPolicy consumer-egress — allowed destinations

| Destination | Port | Why |
|---|---|---|
| `namespaceSelector: kafka` | 9092 | Bitnami Kafka in-cluster |
| `namespaceSelector: minio` | 9000 | MinIO StatefulSet in-cluster |
| `namespaceSelector: default` | 443, 6443 | K8s API (`kubernetes` service in the default ns) — to create batch/v1 Jobs |
| any namespace | 53 UDP/TCP | cluster DNS (kube-dns) |

All other traffic is blocked by `deny-all-default`. Enforced by Calico (calico-system).

---

## Scalability

KEDA `ScaledObject`: 1→3 replicas on `kafka_consumergroup_lag` (topic `file.requested`,
3 partitions). `ResourceQuota`: 12 pods max in the sandbox namespace (consumers + analysis jobs).
