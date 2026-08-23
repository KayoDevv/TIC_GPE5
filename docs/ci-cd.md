# CHARON — CI/CD Complete Reference

> **Project:** GPE-ETNA / CHARON — Cybersecurity browser extension  
> **Repository:** https://github.com/KayoDevv/GPE-ETNA  
> **Last updated:** 2026-06-15

---

## Table of Contents

1. [Project at a Glance](#1-project-at-a-glance)
2. [Repository Layout (CI-relevant)](#2-repository-layout-ci-relevant)
3. [Full CI/CD Pipeline Diagram](#3-full-cicd-pipeline-diagram)
4. [Workflow Reference](#4-workflow-reference)
   - [sanity-checks.yml](#41-sanity-checksyml--pr-gate)
   - [ci-lint.yml](#42-ci-lintyml--infrastructure-lint)
   - [ci-tests.yml](#43-ci-testsyml--python-tests)
   - [ci-build.yml](#44-ci-buildyml--docker-build-verification)
   - [sandbox-llm-contract.yml](#45-sandbox-llm-contractyml--kafka-contract)
   - [schema-compatibility.yml](#46-schema-compatibilityyml--schema-evolution)
   - [cd-deploy.yml](#47-cd-deployyml--build-push--deploy)
5. [Shared Assets](#5-shared-assets)
   - [Composite Action: python-setup](#51-composite-action-python-setup)
   - [Script: check_schema_compat.py](#52-script-check_schema_compatpy)
6. [What Was Done (change log)](#6-what-was-done-change-log)
7. [GitHub Setup Checklist](#7-github-setup-checklist)
8. [What Is Still Pending](#8-what-is-still-pending)

---

## 1. Project at a Glance

CHARON is a cybersecurity browser extension (Chrome/Edge, Manifest V3) that
intercepts email attachments **before** the user can open them. It runs a
3-layer async analysis pipeline and returns a colour-coded verdict directly in
the browser without ever blocking it.

**V1 scope:** PDF and ELF Linux files only.

**Core constraint:** never block the browser, false-positive rate < 0.5 %.

**Pipeline layers:**

```
Browser drag-and-drop
        │
        ▼ TLS 1.3
 Core Backend (FastAPI)
        │ produces: file.requested (Kafka)
        ├──────────────────────────────────────────┐
        ▼                                          ▼
 ML Layer                                  Sandbox Layer
 Static analysis (LightGBM/ONNX)          Behavioral detonation (K8s Job · runc/gVisor)
 SLA < 500 ms                             SLA < 180 s
        │ ml_layer.result                          │ sandbox_layer.result
        │                                          │
        │                                    LLM Layer (only if suspect)
        │                                    Semantic analysis (Llama 3 8B · vLLM)
        │                                    SLA 3–5 s
        │                                          │ llm_layer.result
        └──────────────────┐    ┌──────────────────┘
                           ▼    ▼
                     Verdict Layer (Redis · Saga)
                           │ verdict_layer.result
                           ▼
                     Core Backend → WebSocket → Browser UI
                     Green / Orange / Red
```

---

## 2. Repository Layout (CI-relevant)

```
.github/
├── actions/
│   └── python-setup/
│       └── action.yml          ← Composite action: Python + Poetry + cache [NEW]
├── workflows/
│   ├── README.md               ← Workflow documentation [UPDATED]
│   ├── sanity-checks.yml       ← Secrets scan + forbidden files [existing]
│   ├── ci-lint.yml             ← YAML / K8s / Dockerfile / Terraform lint [existing, fixed]
│   ├── ci-tests.yml            ← Python tests (ruff + mypy + pytest) [NEW]
│   ├── ci-build.yml            ← Docker build verification, no push [NEW]
│   ├── sandbox-llm-contract.yml← Sandbox → LLM Kafka contract check [existing]
│   ├── schema-compatibility.yml← JSON schema BACKWARD_TRANSITIVE check [NEW]
│   └── cd-deploy.yml           ← Build + Trivy scan + push + deploy [existing, updated]
├── dependabot.yml              ← Automated dependency updates [NEW]
└── CODEOWNERS                  ← @KayoDevv @Dufeu-T [existing]

apps/
├── core-backend/               ← FastAPI gateway (no Dockerfile yet)
├── frontend/                   ← Vue 3 / WXT extension (no Dockerfile yet)
└── workers/
    ├── ml_layer/               ← LightGBM/ONNX · pyproject.toml ✓
    ├── sandbox_layer/          ← K8s Jobs + gVisor · 3 Dockerfiles ✓
    ├── llm_layer/              ← vLLM / Llama 3 (stub, no Dockerfile yet)
    ├── verdict_layer/          ← Redis Saga (stub, no Dockerfile yet)

packages/
├── core/                       ← Shared Pydantic models + Kafka · pyproject.toml ✓
└── kafka-schemas/              ← JSON Schema Draft-07 contracts (source of truth)

infrastructure/
├── terraform/                  ← Kafka topics + Schema Registry
└── k8s-manifests/
    ├── applications/sandbox/   ← K8s base manifests
    └── overlays/
        ├── dev/                ← K3s GPE-NYX [existing]
        └── prod/               ← Production (wired to cd-deploy.yml) [NEW]

scripts/
├── ci/
│   ├── __init__.py
│   └── check_schema_compat.py  ← BACKWARD_TRANSITIVE checker [NEW]
└── validation/                 ← Large-scale corpus validation harness
```

---

## 3. Full CI/CD Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PULL REQUEST → main                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  sanity-checks.yml          ci-lint.yml              ci-tests.yml          │
│  ┌─────────────────┐        ┌──────────────────┐     ┌──────────────────┐  │
│  │ Gitleaks        │        │ yamllint         │     │ test-core        │  │
│  │ Empty files     │        │ kubeconform      │     │ (packages/core)  │  │
│  │ Forbidden files │        │ hadolint         │     │  ruff+mypy+      │  │
│  │ Conflict markers│        │ docker compose   │     │  pytest 100%cov  │  │
│  │ Python syntax   │        │ terraform fmt    │     │       │          │  │
│  └─────────────────┘        │ terraform validate│    │       ▼          │  │
│                             └──────────────────┘     │ test-ml-layer    │  │
│                                                       │ (needs core)     │  │
│  ci-build.yml (9 images)                             │  ruff+mypy+      │  │
│  ┌──────────────────────────────────────────┐        │  pytest 100%cov  │  │
│  │ sandbox-consumer  sandbox-agent          │        │                  │  │
│  │ sandbox-pdf-agent                       │        │ test-sandbox-    │  │
│  │ core-backend*     frontend*              │        │ layer (pure core)│  │
│  │ ml-layer*         llm-layer*             │        │  ruff + pytest   │  │
│  │ verdict-layer*                           │        │  (no K8s needed) │  │
│  │ (* skip if Dockerfile not yet created)   │        │                  │  │
│  │ Build + Trivy scan — no push             │        │ test-core-       │  │
│  └──────────────────────────────────────────┘        │ backend          │  │
│                                                       │  ruff+mypy+      │  │
│                                                       │  pytest 100%cov  │  │
│                                                       └──────────────────┘  │
│                                                                             │
│  sandbox-llm-contract.yml           schema-compatibility.yml               │
│  (only when sandbox/llm changed)    (only when kafka-schemas/ changed)     │
│  ┌──────────────────────────┐       ┌──────────────────────────────────┐   │
│  │ Validate golden fixtures │       │ Per-schema BACKWARD_TRANSITIVE   │   │
│  │ against JSON schema      │       │ check: no new required fields,   │   │
│  │ LLM validator accepts    │       │ no type changes, no removals     │   │
│  │ CONTRACT_VERSION aligned │       │ under additionalProperties:false │   │
│  └──────────────────────────┘       └──────────────────────────────────┘   │
│                                                                             │
│  ⬆ All checks must pass. Enforced by branch ruleset on main. ⬆            │
│  (schema-compat and sandbox-llm-contract are path-filtered — they          │
│   show as "skipped" on unrelated PRs, which GitHub counts as passing)      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                       PR approved + merged
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    cd-deploy.yml (push to main)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  build-and-push (matrix: 9 images)                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  1. Build locally (load: true, no push)                              │  │
│  │  2. Trivy CVE scan → fails on CRITICAL or HIGH                       │  │
│  │  3. Push to ghcr.io/kayodevv/<image>:<git tag> + :latest            │  │
│  │  Images: charon-sandbox-consumer · ubuntu-sandbox · ubuntu-pdf-sandbox │  │
│  │     charon-core-backend* · charon-frontend*   │  │
│  │     charon-ml-layer* · charon-llm-layer* · charon-verdict-layer*    │  │
│  │  (* skipped gracefully until Dockerfile is added)                   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                              │                                             │
│                              ▼  (needs: build-and-push)                    │
│  deploy (environment: production — requires manual approval)               │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  kustomize edit set image ... (updates prod overlay with SHA tag)    │  │
│  │  kubectl apply -k infrastructure/k8s-manifests/overlays/prod        │  │
│  │                                                                      │  │
│  │  ⚠ Currently a STUB — uncomment when KUBECONFIG_B64 is set.        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Workflow Reference

### 4.1 `sanity-checks.yml` — PR Gate

| | |
|---|---|
| **Trigger** | PR → `main` |
| **Permissions** | `contents: read`, `pull-requests: read` |

| Job | What it does |
|---|---|
| `Credentials Checker` | Gitleaks full-history scan for leaked secrets or tokens |
| `Codebase Sanity Checks` | Empty files · forbidden files (`.DS_Store`, `*.pyc`, `__pycache__`) · merge conflict markers (`<<<<<<<`) · Python syntax (`python -m compileall`) |

---

### 4.2 `ci-lint.yml` — Infrastructure Lint

| | |
|---|---|
| **Trigger** | PR → `main` · Push to `main` or `feat/**` |

| Job | What it checks |
|---|---|
| `YAML Syntax Check` | All `*.yaml`/`*.yml` except `.github/` (yamllint with `.yamllint.yml` config) |
| `Kubernetes Manifest Validation` | K8s base manifests via kubeconform + kustomize overlays rendering |
| `Dockerfile Lint` | Every `Dockerfile*` via hadolint |
| `Docker Compose Validation` | `docker compose config --quiet` |
| `Terraform Validation` | `terraform fmt -check` + `terraform validate` (with retry on init) |

---

### 4.3 `ci-tests.yml` — Python Tests

| | |
|---|---|
| **Trigger** | PR → `main` · Push to `main` or `feat/**` |
| **Concurrency** | Cancels superseded runs on the same branch/PR |
| **Permissions** | `contents: read` |

| Job | Package | Toolchain | Notes |
|---|---|---|---|
| `Test · packages/core` | `packages/core` | Poetry · Python 3.11 · ruff · mypy strict · pytest 100 % coverage | Foundation — all others depend on it |
| `Test · apps/workers/ml_layer` | `apps/workers/ml_layer` | Poetry · Python 3.11 · ruff · mypy strict · pytest 100 % coverage | `needs: test-core` — validates after foundation |
| `Test · apps/workers/sandbox_layer (pure core)` | `apps/workers/sandbox_layer/agent/tests/` | pip · Python 3.11 · ruff · pytest | **Pure core only** — no K8s, no strace, no MinIO. Runs golden tests + hypothesis unit tests. `aiokafka` installed because `run_analysis.py` imports `AIOKafkaProducer` at module level. I/O shell validated by `make sandbox-validate` on the VM. |
| `Test · apps/core-backend` | `apps/core-backend` | Poetry · Python 3.11 · ruff · mypy strict · pytest 100 % coverage | Runs independently (no `needs:`) in parallel with the other jobs |

Three of the four jobs use the **`.github/actions/python-setup`** composite action (the sandbox job uses `pip` directly since `sandbox_layer` has no `pyproject.toml`).

---

### 4.4 `ci-build.yml` — Docker Build Verification

| | |
|---|---|
| **Trigger** | PR → `main` only |
| **Concurrency** | Cancels superseded runs |
| **push** | `false` — verification only, nothing is published |

Matrix loaded from `.github/service-matrix.json` (shared source of truth with `cd-deploy.yml` — no manual sync needed). Each image goes through two steps:

1. **Build locally** (`load: true`, not published)
2. **Trivy CVE scan** — exits 1 on any CRITICAL or HIGH with a fix available (`ignore-unfixed: true`)

Services without a Dockerfile are **skipped gracefully** (not failed):

| Image | Dockerfile | Status |
|---|---|---|
| `sandbox-consumer` | `apps/workers/sandbox_layer/Dockerfile.consumer` | ✅ Exists |
| `sandbox-agent` | `apps/workers/sandbox_layer/Dockerfile.agent` | ✅ Exists |
| `sandbox-pdf-agent` | `apps/workers/sandbox_layer/Dockerfile.pdf-agent` | ✅ Exists |
| `core-backend` | `apps/core-backend/Dockerfile` | ⏭ Skipped (not yet created) |
| `frontend` | `apps/frontend/Dockerfile` | ⏭ Skipped |
| `ml-layer` | `apps/workers/ml_layer/Dockerfile` | ⏭ Skipped |
| `llm-layer` | `apps/workers/llm_layer/Dockerfile` | ⏭ Skipped |
| `verdict-layer` | `apps/workers/verdict_layer/Dockerfile` | ⏭ Skipped |

Caches layers via `type=gha` to speed up repeated PR builds.

---

### 4.5 `sandbox-llm-contract.yml` — Kafka Contract

| | |
|---|---|
| **Trigger** | PR → `main` · only when `apps/workers/sandbox_layer/**`, `apps/workers/llm_layer/**`, or `packages/kafka-schemas/sandbox_layer.result.json` change |

Three guarantees:
1. **Golden fixtures are valid** against the official `sandbox_layer.result.json` JSON Schema
2. **LLM consumer accepts** those same fixtures (`validate_sandbox_input.py`)
3. **CONTRACT_VERSION files** on both sides are aligned (prevents silent drift)

---

### 4.6 `schema-compatibility.yml` — Schema Evolution

| | |
|---|---|
| **Trigger** | PR → `main` · only when `packages/kafka-schemas/**` or `scripts/ci/check_schema_compat.py` change |

Matrix: one job per Kafka schema file (5 total).

For each schema, the job:
1. Checks if the schema actually changed in this PR (if not → skip)
2. Fetches the **old version** from `origin/main` (if first introduction → skip, always OK)
3. Runs `scripts/ci/check_schema_compat.py` — pure Python, no Kafka cluster needed

**BACKWARD_TRANSITIVE rules enforced:**

| Breaking change | Why it breaks consumers |
|---|---|
| New `required` field without `default` | Old messages won't carry the field — deserialization fails |
| Field type changed | Old messages carry the old type — parsing fails |
| Field removed when `additionalProperties: false` | Old messages have the field — new schema rejects them |

> **Do not add this check as a required status check in the branch ruleset.** GitHub marks path-filtered jobs as `skipped`, which counts as passing. Adding it as required would block every PR that doesn't touch schemas.

---

### 4.7 `cd-deploy.yml` — Build, Push & Deploy

| | |
|---|---|
| **Trigger** | Push to `main` (after PR merge) · `workflow_dispatch` (manual) |
| **Permissions** | `contents: read`, `packages: write` |

**Job 1 — `build-and-push`** (matrix: 9 images from `.github/service-matrix.json`, `fail-fast: false`)

Each image goes through 3 steps:
```
Build locally (push: false, load: true)
        │
        ▼
Trivy CVE scan
  severity: CRITICAL,HIGH
  ignore-unfixed: true
  exit-code: 1  ← blocks push on any hit
        │
        ▼ (only if clean)
Push to ghcr.io/kayodevv/<image>  (see image table above)
  tags: <git tag>  (immutable, used by K8s — e.g. v1.3.0)
        :latest     (floating, for quick pulls)
```

**Job 2 — `deploy`** (`needs: build-and-push`, `environment: production`)

- Requires **manual approval** from reviewers configured in the GitHub `production` environment
- Currently a **stub** — the `kustomize edit set image` + `kubectl apply -k overlays/prod` lines are commented out, waiting for `KUBECONFIG_B64` to be configured

**Registry:** `ghcr.io` using `GITHUB_TOKEN` — no extra secrets needed. `OWNER` is pinned to `kayodevv` (lowercase) in the workflow env because OCI image references must be lowercase and the repo name contains an uppercase letter.

**Image naming** (matches K8s manifests exactly):

| Matrix name | GHCR image pushed |
|---|---|
| `sandbox-consumer` | `ghcr.io/kayodevv/charon-sandbox-consumer` |
| `sandbox-agent` | `ghcr.io/kayodevv/ubuntu-sandbox` |
| `sandbox-pdf-agent` | `ghcr.io/kayodevv/ubuntu-pdf-sandbox` |
| `core-backend` | `ghcr.io/kayodevv/charon-core-backend` |
| `frontend` | `ghcr.io/kayodevv/charon-frontend` |
| `ml-layer` | `ghcr.io/kayodevv/charon-ml-layer` |
| `llm-layer` | `ghcr.io/kayodevv/charon-llm-layer` |
| `verdict-layer` | `ghcr.io/kayodevv/charon-verdict-layer` |

---

## 5. Shared Assets

### 5.1 Composite Action: `python-setup`

**Path:** `.github/actions/python-setup/action.yml`

Eliminates duplicated Python/Poetry boilerplate across `ci-tests.yml` jobs.

**Inputs:**

| Input | Default | Description |
|---|---|---|
| `python-version` | `"3.11"` | Python version |
| `working-directory` | *(required)* | Path to the package root (where `pyproject.toml` lives) |

**What it does:**
1. `actions/setup-python@v5` — installs the requested Python version
2. `pipx install poetry` — installs Poetry (idempotent, pipx is pre-installed on GitHub runners)
3. `poetry config virtualenvs.in-project true` — keeps `.venv` inside the package directory
4. `actions/cache@v4` — caches `.venv` keyed by `OS + python-version + poetry.lock` hash
5. `poetry install --with dev` — installs all deps (skipped if cache hit)

---

### 5.2 Script: `check_schema_compat.py`

**Path:** `scripts/ci/check_schema_compat.py`

Pure Python (stdlib only, no dependencies to install). Called by `schema-compatibility.yml`.

```
Usage: python scripts/ci/check_schema_compat.py <old_schema.json> <new_schema.json>

Exit codes:
  0 — compatible
  1 — breaking change detected
  2 — usage / I/O error
```

The script applies all three rules **recursively**: it walks nested `object` properties and `array` item schemas (e.g. `iocs[].type`, `email_context.sender`) applying the same checks at every level — a breaking change inside a nested structure is caught just like a top-level one. It prints a human-readable diagnosis for any violation.

---

## 6. What Was Done (Change Log)

### New files

| File | What it is |
|---|---|
| `.github/actions/python-setup/action.yml` | Composite action — Python + Poetry + virtualenv cache |
| `.github/workflows/ci-tests.yml` | Python tests workflow (PR + push) |
| `.github/workflows/ci-build.yml` | Docker build verification workflow (PR only) |
| `.github/workflows/schema-compatibility.yml` | Kafka JSON schema BACKWARD_TRANSITIVE check |
| `.github/dependabot.yml` | Automated dependency updates (Actions + pip × 2 + Docker × 2) |
| `scripts/ci/__init__.py` | Python module marker |
| `scripts/ci/check_schema_compat.py` | BACKWARD_TRANSITIVE schema checker script |
| `infrastructure/k8s-manifests/overlays/prod/kustomization.yaml` | Production Kustomize overlay |
| `infrastructure/k8s-manifests/components/in-cluster-endpoints/consumer-env-patch.yaml` | Consumer in-cluster endpoints (dev + prod) |
| `.github/service-matrix.json` | Shared 9-service matrix — single source of truth for `ci-build.yml` and `cd-deploy.yml` |
| `docs/ci-cd.md` | This document |

### Modified files

| File | What changed |
|---|---|
| `.github/workflows/cd-deploy.yml` | Fixed matrix (`path:` → `dockerfile:`); added 3 sandbox Dockerfiles +             ; added Trivy CVE scan between build and push; improved deploy stub; matrix moved to `service-matrix.json` |
| `.github/workflows/ci-tests.yml` | Added `Test · apps/core-backend` job (folded from the deleted `core-backend-ci.yml`; runs in parallel with no `needs:`) |
| `.github/workflows/ci-build.yml` | Added Trivy CVE scan between build and push-verification steps; matrix now sourced from `service-matrix.json` |
| `.github/workflows/ci-lint.yml` | Fixed 5 occurrences of `checkout@v5` → `@v4` (inconsistency with all other workflows) |
| `.github/workflows/README.md` | Updated workflow diagram, job names, required checks list, schema-compat description |
| `scripts/ci/check_schema_compat.py` | Made the checker recurse through nested `object` properties and `array` item schemas |

### Deleted files

| File | Reason |
|---|---|
| `.github/workflows/publish-images.yml` | Consolidated into `cd-deploy.yml` — was building and pushing duplicate images on every merge to `main` |
| `.github/workflows/core-backend-ci.yml` | Folded its `Test · apps/core-backend` job into `ci-tests.yml` — all Python test jobs now live in a single workflow |

---

## 7. GitHub Setup Checklist

These actions **cannot be done from a local clone** — they require access to the GitHub repository settings.

### 7.1 Branch ruleset on `main` 🔴 Critical

**Settings → Rules → Rulesets → New branch ruleset**

Target branch: `main`

Enable:
- [x] Require a pull request before merging
  - Required approvals: **1**
- [x] Require status checks to pass — add **each of the following by exact name**:

```
Credentials Checker
Codebase Sanity Checks
YAML Syntax Check
Kubernetes Manifest Validation
Dockerfile Lint
Docker Compose Validation
Terraform Validation
Test · packages/core
Test · apps/workers/ml_layer
Test · apps/workers/sandbox_layer (pure core)
Test · apps/core-backend
Build · sandbox-consumer
Build · sandbox-agent
Build · sandbox-pdf-agent
```

> **Do NOT add** `BACKWARD_TRANSITIVE · *` or `Validate sandbox -> LLM contract` — these are path-filtered and show as `skipped` on most PRs. GitHub treats `skipped` as passing.

- [x] Require branches to be up to date before merging
- [x] Block force pushes

---

### 7.2 `production` environment 🔴 Critical

**Settings → Environments → New environment** → name: `production`

- Add required reviewers (yourself + teammates)
- The `deploy` job in `cd-deploy.yml` will pause after `build-and-push` and wait for a reviewer to approve before touching the cluster

Without this environment, the deploy job runs immediately after a merge with no human gate.

---

### 7.3 Gitleaks license (private repo only) 🟡

If the repository is **private**, `gitleaks-action@v2` requires a license.

**Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `GITLEAKS_LICENSE` | Your Gitleaks license key |

---

### 7.4 ghcr.io package visibility 🟡

After the first `cd-deploy.yml` run pushes images, each package defaults to **private** on ghcr.io. If the K8s cluster needs to pull images without credentials:

**github.com → Packages → [each image] → Package settings → Change visibility → Public**

Alternatively, configure `imagePullSecrets` in the K8s manifests and store the credentials as a cluster secret.

---

### 7.5 Deployment secrets — when cluster is ready 🟢 Future

When wiring the real deploy step in `cd-deploy.yml`, add one of:

| Option | Secret(s) to add |
|---|---|
| Generic kubeconfig | `KUBECONFIG_B64` (base64 of `~/.kube/config`) |
| AWS EKS | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` |
| GKE | `GCP_SA_KEY` (service account JSON) |

Then uncomment the `kustomize edit set image` + `kubectl apply -k` block in `cd-deploy.yml`.

---

## 8. What Is Still Pending

### 8.1 Dockerfiles for 5 services

These services currently have no `Dockerfile`. The CI workflows skip them gracefully, but they must be created before those services can be built and deployed via the CD pipeline.

| Service | Path |
|---|---|
| core-backend (FastAPI) | `apps/core-backend/Dockerfile` |
| frontend (Vue 3 / WXT) | `apps/frontend/Dockerfile` |
| ml-layer (LightGBM/ONNX) | `apps/workers/ml_layer/Dockerfile` |
| llm-layer (vLLM / Llama 3) | `apps/workers/llm_layer/Dockerfile` |
| verdict-layer (Redis / Saga) | `apps/workers/verdict_layer/Dockerfile` |

---

### 8.2 `sandbox_layer` has no `pyproject.toml`

The sandbox test job installs `pydantic`, `aiokafka`, `pytest`, and `ruff` manually via `pip`. This works, but it is inconsistent with the rest of the project. Adding a `pyproject.toml` to `apps/workers/sandbox_layer/` would:
- Allow the `python-setup` composite action to be reused
- Enable `poetry run mypy` strict type checking
- Enforce the 100% coverage rule consistently

---

### 8.3 No prod K8s overlay customization

`infrastructure/k8s-manifests/overlays/prod/` was created as a skeleton identical to `dev`. Before wiring the real deploy, review and adjust:
- Resource requests/limits per service (prod may differ from dev)
- Replicas (KEDA min/max per prod traffic)
- Any prod-specific env vars (logging levels, timeouts, etc.)

---

### 8.4 No image tag pinning in prod overlay

The `kustomization.yaml` in the prod overlay has `images: []`. When activating the deploy step, this list must be populated with the exact version tags built by `cd-deploy.yml`. This is already documented in the commented-out deploy step.

---

### 8.5 Dependabot labels don't exist yet

`.github/dependabot.yml` assigns labels `dependencies`, `ci`, `python`, and `docker` to its PRs. These labels must be created in **Settings → Labels** (or directly on a PR) before they take effect. Dependabot will still open PRs without them, but they won't be categorised.

---

### 8.6 Windows PE / Office formats (V2 scope)

The entire Windows analysis path (PE static model, KVM detonation, Office OLE/VBA, ZIP recursive decompression) is out of scope for V1. When V2 starts, the following CI additions will be needed:
- A new `pyproject.toml` test job for the Windows agent
- An update to the sandbox Docker matrix (new image for PE/KVM)
- New entries in `packages/kafka-schemas/` (schema-compat will catch regressions automatically)

---

### 8.7 Pre-commit hooks (optional)

No `.pre-commit-config.yaml` exists. Adding one would run `ruff`, `mypy`, and `yamllint` locally before each commit, catching issues before CI rather than after. This is optional but reduces round-trip time.

---

*Document generated 2026-06-05. Keep in sync with workflow changes.*
