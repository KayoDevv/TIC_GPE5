# GitHub Actions — CI/CD Workflows

## Overview

```
PR opened → main
    ├── sanity-checks.yml       Secrets scan (Gitleaks), forbidden files, conflict markers, Python syntax
    ├── ci-lint.yml             YAML, Kubernetes manifests, Dockerfiles, docker-compose, Terraform
    ├── ci-tests.yml            Ruff + mypy + pytest (100 % coverage) for each Python package
    ├── ci-build.yml            Docker image build verification — no push (all 9 images)
    ├── sandbox-llm-contract.yml  Sandbox → LLM contract: golden fixtures + LLM validator + CONTRACT_VERSION alignment
    └── schema-compatibility.yml  Kafka JSON schema BACKWARD_TRANSITIVE check (only when packages/kafka-schemas/** changes)

PR merged → main  (triggered by push to main)
    └── cd-deploy.yml
            ├── build-and-push  Build + push all 9 images to container registry
            └── deploy          Apply K8s manifests (stub — see Future Steps below)
```

All checks must pass before a PR can be merged. See **GitHub Setup** below to enforce this.

---

## Workflow details

### `sanity-checks.yml` — Sanity & Credentials Checks
| | |
|---|---|
| Trigger | PR → `main` |
| Jobs | Gitleaks (secrets scan) · empty files · forbidden files (`.DS_Store`, `*.pyc`, `__pycache__`) · merge conflict markers · Python syntax |

### `ci-lint.yml` — Lint YAML, Kubernetes, Docker, Terraform
| | |
|---|---|
| Trigger | Push to `main` or `feat/**` · PR → `main` |
| Jobs | yamllint · kubeconform (K8s manifests) · hadolint (Dockerfiles) · docker compose config · terraform fmt + validate |

### `ci-tests.yml` — Tests
| | |
|---|---|
| Trigger | PR → `main` |
| Jobs | `test-core` · `test-ml-layer` (needs `test-core`) · `test-sandbox-layer` · `test-core-backend` |
| Standard | ruff lint · mypy strict · pytest with 100 % coverage enforced |

### `ci-build.yml` — Build Docker Images
| | |
|---|---|
| Trigger | PR → `main` |
| Jobs | Matrix build across all 6 services — skips gracefully if no Dockerfile exists yet |
| Note | Build only, no push. Purpose: verify the Dockerfile compiles before merge |

### `schema-compatibility.yml` — Kafka Schema Compatibility
| | |
|---|---|
| Trigger | PR → `main` touching `packages/kafka-schemas/**` or `scripts/ci/check_schema_compat.py` |
| Jobs | Matrix (one job per schema file). Fetches the old version from `origin/main`, runs `scripts/ci/check_schema_compat.py` — no new required fields, no type changes, no removals under `additionalProperties: false`. Pure Python, no Kafka cluster required. |

### `cd-deploy.yml` — Build, Push & Deploy
| | |
|---|---|
| Trigger | Push to `main` (i.e. after PR merge) · manual via `workflow_dispatch` |
| Jobs | `build-and-push` (matrix, all 9 images) → `deploy` (K8s, stub) |
| Registry | Defaults to `ghcr.io` with `GITHUB_TOKEN` — see **Registry** section below |

---

## GitHub Setup (required)

### 1. Branch protection on `main`

Go to **Settings → Branches → Add branch ruleset → target: `main`** and enable:

- **Require a pull request before merging**
  - Required approvals: 1
- **Require status checks to pass**
  - Add each check name listed below
- **Require branches to be up to date before merging**
- **Block force pushes**

Required status checks to add:

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
Build · core-backend
Build · frontend
Build · ml-layer
Build · llm-layer
Build · verdict-layer
```

> `schema-compatibility` and `sandbox-llm-contract` only run when their respective paths change. Do **not** add them as required checks — GitHub marks skipped jobs as passing, so they gate correctly without blocking unrelated PRs.

### 2. `production` environment (deploy gate)

Go to **Settings → Environments → New environment** → name it `production`.

- Add **required reviewers** (yourself + teammates)
- The `deploy` job will pause and wait for manual approval before running

---

## Registry configuration

The CD workflow uses `ghcr.io` (GitHub Container Registry) with `GITHUB_TOKEN` — no extra secrets needed. The owner is pinned to `kayodevv` (lowercase, forced in the workflow env) because the repo name contains an uppercase letter and OCI references must be lowercase.

Image names match the existing K8s manifests exactly:

| Service | GHCR image |
|---|---|
| Sandbox consumer (Deployment) | `ghcr.io/kayodevv/charon-sandbox-consumer` |
| Sandbox ELF agent (Job) | `ghcr.io/kayodevv/ubuntu-sandbox` |
| Sandbox PDF agent (Job) | `ghcr.io/kayodevv/ubuntu-pdf-sandbox` |
| Core backend | `ghcr.io/kayodevv/charon-core-backend` |
| Frontend | `ghcr.io/kayodevv/charon-frontend` |
| ML layer | `ghcr.io/kayodevv/charon-ml-layer` |
| LLM layer | `ghcr.io/kayodevv/charon-llm-layer` |
| Verdict layer | `ghcr.io/kayodevv/charon-verdict-layer` |

Tags: `sha-<SHA>` (immutable, used by K8s prod overlay) + `latest` (floating).

---

## Future Steps

These are stubbed or commented out. Uncomment/implement when ready.

### Add tests for a new Python worker

In `ci-tests.yml`, copy the `test-core-backend` job block and adjust:
- `working-directory` → path to the worker
- `needs` → add a dependency on `test-core` (and any shared package it uses)
- Cache key → include the worker's `poetry.lock`

### Add a Dockerfile for a service

`ci-build.yml` and `cd-deploy.yml` already include all 6 services in their matrix.
Just add the `Dockerfile` to the service directory — both workflows will pick it up automatically on the next PR.

### Add frontend tests (Vue 3 / WXT)

In `ci-tests.yml`, uncomment the `test-frontend` job block. Adjust the test command to match your test runner (`vitest`, `jest`, etc.).

E2E tests (Playwright) will need a separate job with a running browser — add it when the extension is ready for integration testing.

### Wire up the real deployment

In `cd-deploy.yml`, inside the `deploy` job, replace the stub step with actual kubectl steps.
Three commented-out options are provided:

- **Generic kubeconfig** — store the base64-encoded kubeconfig as `secrets.KUBECONFIG_B64`
- **AWS EKS** — use `aws-actions/configure-aws-credentials` + `aws eks update-kubeconfig`
- **GKE** — use `google-github-actions/get-gke-credentials`

Then uncomment the `kustomize edit set image` + `kubectl apply -k` lines and point them at the right overlay (`infrastructure/k8s-manifests/overlays/prod`).

Secrets to add when the cluster is ready:

| Secret | Description |
|---|---|
| `KUBECONFIG_B64` | Base64-encoded kubeconfig (generic option) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS credentials (EKS option) |
| `GCP_SA_KEY` | GCP service account JSON (GKE option) |

