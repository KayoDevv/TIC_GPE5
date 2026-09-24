# GitHub Actions — CI/CD Workflows

## Overview

```
PR opened → main
    ├── sanity-checks.yml       Secrets scan (Gitleaks), forbidden files, conflict markers, Python syntax
    ├── ci-lint.yml             YAML, Kubernetes manifests, Dockerfiles, docker-compose, Terraform
    ├── ci-sast.yml             Semgrep SAST over the Python and TypeScript sources
    ├── ci-tests.yml            Ruff + mypy + pytest (100 % coverage) for each Python package
    ├── ci-build.yml            Docker image build verification — no push (all 9 images)
    ├── ci-sca.yml              Dependency CVEs in the lock files (Trivy fs)
    ├── sandbox-llm-contract.yml  Sandbox → LLM contract: golden fixtures + LLM validator + CONTRACT_VERSION alignment
    └── schema-compatibility.yml  Kafka JSON schema BACKWARD_TRANSITIVE check (only when packages/kafka-schemas/** changes)

Push to update-image or main
    └── cd-publish-images.yml   Build + Trivy-scan + push every image whose
                                `# ghcr-image:` header version is absent from GHCR

git tag v*
    └── cd-deploy.yml           Promote those header versions to `latest`
                                (manifest copy, no rebuild)
            └── deploy-pipeline.yml   Roll the tagged commit onto GPE-NYX
```

### Where a version comes from

Each Dockerfile declares its own version in a `# ghcr-image: <name>:<version>`
header. That header is the single source of truth: `makefiles/versions.mk`, the
kustomization `newTag:` values and the consumer env values are derived from it
by `make sync-versions`, and `sanity-checks.yml` fails the build when they
drift. Bumping a header releases that one image; a git tag releases the
repository, not the images.

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

### `ci-sast.yml` — SAST
| | |
|---|---|
| Trigger | PR → `main`, when the `sast` filter matches (any `.py`/`.ts`/`.tsx`/`.js`/`.jsx` or the SAST plumbing) |
| Jobs | Semgrep (`p/default`, `p/python`, `p/typescript`) over the whole tree. One scan to JSON, then `scripts/ci/semgrep_report.py` prints every severity and fails on `ERROR` only. The report is uploaded as the `semgrep-report` artifact (7 days). |
| Gate | `ERROR` findings block the merge; `WARNING`/`INFO` are printed without blocking |
| Note | The semgrep version is pinned — an unpinned engine changes its rules between runs, so the same commit could pass today and fail tomorrow |

Complements the two scanners already in place rather than duplicating them:
Gitleaks reads the git history, Trivy reads the built image filesystem, Semgrep
reads the source code itself — the only layer that was uncovered.

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

### `ci-sca.yml` — Dependency CVEs (SCA)
| | |
|---|---|
| Trigger | PR → `main`, when the `sca` filter matches (any lock file, manifest, or the SCA plumbing) |
| Jobs | `trivy fs` over the repository — reads `poetry.lock` and `package-lock.json` directly |
| Gate | `CRITICAL` blocks the merge; `HIGH` is printed without blocking |

Covers what `ci-build.yml` structurally cannot. Trivy on an image only sees
what was installed into it, so the declared dependency tree stays unscanned:
`apps/frontend` and `apps/website` ship no image at all, and no image carries
the dev groups (pytest, ruff, mypy) that still run in CI with access to the
runner. Same severity split as the SAST gate — the top severity blocks, the
rest stays visible — because the repository had a HIGH backlog when the scan
landed. Tighten to `CRITICAL,HIGH` once that backlog is cleared.

### `schema-compatibility.yml` — Kafka Schema Compatibility
| | |
|---|---|
| Trigger | PR → `main` touching `packages/kafka-schemas/**` or `scripts/ci/check_schema_compat.py` |
| Jobs | Matrix (one job per schema file). Fetches the old version from `origin/main`, runs `scripts/ci/check_schema_compat.py` — no new required fields, no type changes, no removals under `additionalProperties: false`. Pure Python, no Kafka cluster required. |

### `cd-publish-images.yml` — Publish images
| | |
|---|---|
| Trigger | Push to `update-image` or `main` · manual via `workflow_dispatch` |
| Jobs | `plan` (compare each `# ghcr-image:` header against GHCR) → `publish` (matrix over the missing ones only) |
| Gate | Trivy CRITICAL/HIGH with a fix available blocks the push |
| Note | Tags are immutable — an already-published version is skipped, republishing means bumping the header |

### `cd-deploy.yml` — Release (promote to latest)
| | |
|---|---|
| Trigger | `git tag v*` · manual via `workflow_dispatch` |
| Jobs | Verify every header version is on GHCR → `docker buildx imagetools create` onto `latest` → verify digests match |
| Note | No rebuild. Fails before moving anything if any version is missing, so `latest` is never half-promoted |

### `deploy-pipeline.yml` — Deploy onto GPE-NYX
| | |
|---|---|
| Trigger | After `cd-deploy.yml` succeeds · manual via `workflow_dispatch` with a `ref` (branch/tag/SHA, default `main`) |
| Jobs | OpenVPN + SSH → `kubectl apply -k` the pipeline and the sandbox prod overlay |
| Versions | Taken from the kustomizations (Deployments) and from the Dockerfile headers (agent env values) — the input selects the commit, never the tag |

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
SAST result
SCA result
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

Tags: the Dockerfile's `# ghcr-image:` version (immutable, what the manifests
reference) + `latest` (floating, moved by `cd-deploy.yml` on a git tag).

---

## Future Steps

These are stubbed or commented out. Uncomment/implement when ready.

### Add tests for a new Python worker

In `ci-tests.yml`, copy the `test-core-backend` job block and adjust:
- `working-directory` → path to the worker
- `needs` → add a dependency on `test-core` (and any shared package it uses)
- Cache key → include the worker's `poetry.lock`

### Add a Dockerfile for a service

Add the service to `.github/service-matrix.json` and a filter to `.github/filters.yml`
(a matrix entry with no filter is never selected), then give the Dockerfile a
`# ghcr-image: <name>:<version>` header. `ci-build.yml`, `cd-publish-images.yml`
and the version check pick it up from there.

### Add frontend tests (Vue 3 / WXT)

In `ci-tests.yml`, uncomment the `test-frontend` job block. Adjust the test command to match your test runner (`vitest`, `jest`, etc.).

E2E tests (Playwright) will need a separate job with a running browser — add it when the extension is ready for integration testing.

### Detonation agents

`ubuntu-sandbox` and `ubuntu-pdf-sandbox` are never pulled by the cluster: the
analysis Jobs run without credentials, and since KEP-2535 the kubelet forces a
re-auth pull for any image previously pulled with credentials. Run
**Import sandbox agent images** (`import-sandbox-agents.yml`) after publishing a
new agent version and before deploying — a missing tag means `ErrImageNeverPull`.

