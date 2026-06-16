# GPE-ETNA — Zero-Trust Endpoint Security

B2B SaaS cybersecurity product for email attachment analysis. Built on an event-driven microservices architecture (Kafka, Scatter-Gather pattern).

**Core constraints:** never block the browser (100% async) · false positive rate < 0.5%

---

## How it works

When a user downloads an email attachment, the browser extension silently intercepts the click and submits the file to the backend. Three independent analysis workers run in parallel. A final aggregator consolidates their results and pushes a verdict back to the browser in real time.

```
Browser Extension (Chrome / Edge)
    │
    ▼ REST upload
Core Backend (FastAPI)
    │  produces: file.requested
    ├──────────────────────────────────────────────────┐
    ▼                                                  ▼
ML Layer                                        Sandbox Layer
Static analysis (ONNX)                          Behavioral detonation (K8s Job · runc)
SLA < 500 ms                                    SLA < 120 s
    │ ml_layer.result                                  │ sandbox_layer.result
    │                                                  ├──────────────────────┐
    │                                                  ▼                      │
    │                                            LLM Layer                   │
    │                                            Semantic analysis (vLLM)    │
    │                                            SLA 3–5 s                   │
    │                                                  │ llm_layer.result     │
    └─────────────────┐         ┌─────────────────────┘                      │
                      ▼         ▼         ▼                                  │
                    Verdict Layer (Redis + Saga)  ◄────────────────────────────┘
                          │ verdict.result
                          ▼
                    Core Backend → WebSocket → Browser Extension
```

---

## Services

| Service | Stack | Role | SLA |
|---|---|---|---|
| **Frontend** | Vue 3, WXT, TypeScript, Tailwind | Chrome/Edge extension (Manifest V3). Intercepts downloads, shows verdict UI | — |
| **Core Backend** | Python, FastAPI | Entry point: validates (≤ 35 MB), uploads to S3/MinIO, emits Kafka event, pushes verdict via WebSocket | — |
| **ML Layer** | Python, LightGBM/ONNX Runtime | Static analysis: entropy, PE sections, imports/exports → risk score 0–100 | < 500 ms |
| **Sandbox Layer** | Python, K8s `batch/v1 Job` (hardened `runc` + seccomp, gVisor optional) | Behavioral detonation in isolated containers, `strace` + state-diff + `/proc` forensics → IOC list (MITRE ATT&CK) | < 120 s |
| **LLM Layer** | Python, vLLM, Llama-3-8B | Correlates email context + sandbox IOCs → binary decision + human-readable explanation | 3–5 s |
| **Verdict Layer** | Python, Redis | Saga aggregator: collects async results, applies decision matrix, emits final verdict | — |

### Decision matrix

| Condition | Verdict |
|---|---|
| `ml_layer.risk_score > 90` | `blocked` immediately (remaining layers run for audit logs) |
| `llm_layer.is_malicious == true` | `blocked` |
| Sandbox timeout after 125 s | `warning` or `blocked` (per-tenant config) |
| All results received, none of the above | `allowed` |

### Frontend visual states

| Verdict | UI |
|---|---|
| `allowed` | Green indicator |
| `blocked` | Red indicator |
| `warning` | Orange indicator + side panel with LLM explanation |

---

## Kafka Topics

All topics: `retention.ms=3600000` (60 min, GDPR), `replication_factor=3`, TLS 1.3 in production.

| Topic | Producer | Consumers | Schema file |
|---|---|---|---|
| `file.requested` | Core Backend | ML Layer, Sandbox Layer | `packages/kafka-schemas/file.requested.json` |
| `ml_layer.result` | ML Layer | Verdict Layer | `packages/kafka-schemas/ml_layer.result.json` |
| `sandbox_layer.result` | Sandbox Layer | LLM Layer, Verdict Layer | `packages/kafka-schemas/sandbox_layer.result.json` |
| `llm_layer.result` | LLM Layer | Verdict Layer | `packages/kafka-schemas/llm_layer.result.json` |
| `verdict.result` | Verdict Layer | Core Backend | `packages/kafka-schemas/verdict_layer.result.json` |

Message key: `job_id` (UUID string) — guarantees partition ordering per analysis job.
Schema evolution rule: `BACKWARD_TRANSITIVE` — new optional fields only, no removals, no type changes.

---

## Monorepo Structure

```
apps/
├── frontend/               # Vue 3 + WXT browser extension
├── core-backend/           # FastAPI gateway
└── workers/
    ├── ml_layer/           # Static ML analysis
    ├── sandbox_layer/      # K8s Job behavioral sandbox (strace + /proc)
    ├── llm_layer/          # LLM semantic analysis
    └── verdict_layer/      # Saga aggregator

packages/
├── core/                   # Shared Python library: Pydantic event models + KafkaPublisher
└── kafka-schemas/          # JSON Schema Draft-07 contracts (source of truth)

infrastructure/
├── terraform/              # Kafka topics + Schema Registry provisioning
└── k8s-manifests/          # Kubernetes manifests (bases / overlays / monitoring)

docs/
└── architecture/           # Kafka and Schema Registry specifications
```

---

## Local Development

### Prerequisites

- Docker + Docker Compose
- Python 3.9+ with Poetry
- Node.js 18+ (frontend)

### Start the infrastructure stack

```bash
docker compose up -d
```

This starts: **Redis** · **MinIO** (S3-compatible, console at `http://localhost:9001`) · **Zookeeper** · **Kafka** (`localhost:9092`) · **Schema Registry** (`http://localhost:8081`) · **kafka-init** (creates topics + registers schemas automatically).

```bash
docker compose down   # tear down
```

### Shared Python package

```bash
cd packages/core
poetry install
poetry run pytest                    # run all tests
poetry run pytest tests/test_models.py::test_file_requested_event_valid  # single test
poetry run pytest --cov              # coverage (must be 100%)
poetry run ruff check .              # lint
poetry run mypy src/                 # type check
```

### Infrastructure (Terraform)

```bash
terraform -chdir=infrastructure/terraform init
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform fmt -recursive
```

---

## CI / CD

| Workflow | Trigger | What it checks |
|---|---|---|
| `ci-lint` | push / PR → `main` | yamllint · kubeconform (K8s manifests) · hadolint (Dockerfiles) · docker compose config · terraform fmt + validate |
| `sanity-checks` | PR → `main` | Gitleaks (secrets) · empty files · forbidden files (`.DS_Store`, `*.pyc`, `__pycache__`) · merge conflict markers · Python syntax |
| `ci-tests` | PR → `main`, push → `main` / `feat/**` | Test · packages/core · Test · apps/workers/ml\_layer · Test · apps/workers/sandbox\_layer · **Test · apps/core-backend** |
| `ci-build` | PR → `main` | Build · (all 9 services) — Dockerfile compiles cleanly + Trivy CVE scan (CRITICAL/HIGH gate) |
| `schema-compatibility` | PR → `main` touching `packages/kafka-schemas/**` | Spins up Kafka stack, registers current `main` schemas, tests PR schemas for `BACKWARD_TRANSITIVE` compatibility |
| `cd-deploy` | push → `main` | Build → Trivy scan → push to `ghcr.io/kayodevv/charon-*` (sha + latest tags) → deploy stub |

---

## Code Standards

- **Python workers and backend:** TDD with `pytest-asyncio` (`asyncio_mode = "auto"`), 100% test coverage enforced
- **Linting:** Ruff (line length 100, rules E/F/B/I) + MyPy strict
- **Frontend:** Manifest V3, Shadow DOM for CSS isolation, Playwright for E2E tests
- **Sandbox:** payloads run in ephemeral, hardened K8s Jobs (`runc` + seccomp whitelist + `cap-drop ALL` + non-root UID 10001 + NetworkPolicy deny-all); gVisor (`runsc`) enableable via `SANDBOX_RUNTIME_CLASS=gvisor`. Each Job is destroyed after execution.
- **LLM:** temperature 0.1–0.3 (no hallucinations on security decisions)
