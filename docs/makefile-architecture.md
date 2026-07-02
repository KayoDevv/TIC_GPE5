# Build System — Makefile Architecture

This is the **authoritative standard** for the monorepo build system. It describes the
parent-child Makefile architecture and the **strict contract** every service must honour.
Items marked **MUST** / **MUST NOT** are enforced in review.

It is a companion to [CONTRIBUTING.md](CONTRIBUTING.md) — all rules there (English only, no
duplication, etc.) apply to Makefiles too.

---

## 1. Philosophy

One entry point, uniform verbs, no duplication.

- The **root `Makefile` is an orchestrator.** It owns the service registry, the cross-service
  dispatch, and all infrastructure / cluster (K3s) operations. It contains **no** per-service
  build logic.
- Each **service owns a child `Makefile`** that knows how to build/test/lint *itself* and
  nothing else.
- Shared logic lives **once** in `makefiles/` and is `include`d by children — never copied.
- Every child exposes the **same verbs**, so `make <verb> [SERVICE...]` works identically
  across a Poetry package, an npm extension, a Docker-only worker, or a Terraform module.

```
make test              # test every service
make test ML SHARED    # test only the ML layer and zt-shared
make build SANDBOX     # build only the sandbox images
make -C apps/frontend lint   # run a child directly (must always work standalone)
```

---

## 2. Layout

```
Makefile                      ← root orchestrator: registry, dispatch, infra/K3s ops
makefiles/
  common.mk                   ← shared vars + display macros (included by EVERY child)
  python.mk                   ← standard targets for Poetry services (include after common.mk)
apps/
  core-backend/Makefile       ← Python/Poetry  → includes common.mk + python.mk
  frontend/Makefile           ← npm/WXT        → includes common.mk, implements verbs
  workers/
    ml_layer/Makefile         ← Python/Poetry
    sandbox_layer/Makefile    ← Docker-only    → includes common.mk, implements verbs
    llm_layer/Makefile
    verdict_layer/Makefile
packages/
  core/Makefile               ← Python/Poetry  (zt-shared)
  kafka-schemas/Makefile      ← static JSON    → includes common.mk, implements verbs
infrastructure/
  k8s-manifests/Makefile      ← bespoke
  terraform/Makefile          ← bespoke
scripts/validation/Makefile   ← standalone tool Makefile, NOT a service child (see §8)
```

---

## 3. The standard target contract

**MUST:** every service child Makefile implements **all** of these verbs — even when a verb
does not apply (then it `skip`s, see §6). This is what makes the root dispatch uniform: a
missing verb breaks `make <verb>` for the whole repo.

| Verb        | Meaning                                  | If N/A for the service |
|-------------|------------------------------------------|------------------------|
| `install`   | Install dependencies                     | `skip`                 |
| `build`     | Build the package / image                | `skip`                 |
| `test`      | Run the test suite                       | `skip`                 |
| `lint`      | Static checks (must fail on violations)  | `skip`                 |
| `format`    | Auto-format the code                     | `skip`                 |
| `typecheck` | Type checking                            | `skip`                 |
| `run`       | Start the dev server / process           | `skip`                 |
| `deploy`    | Build + publish the artifact/image       | `skip`                 |
| `clean`     | Remove build artifacts                   | implement              |

Extra service-specific verbs are allowed (`test-e2e` on frontend, `test-cov` in `python.mk`,
`validate` on terraform) **in addition to** the contract, never instead of it.

**MUST:** an N/A verb uses the `skip` macro and exits 0 — it must **not** error and must
**not** silently do nothing. A skipped verb prints why, so a full-repo `make lint` is readable
and never aborts on a service that legitimately has no linter.

---

## 4. The root orchestrator

### Service registry
A service is registered in **three** places in the root `Makefile`:

```make
SANDBOX_DIR  := apps/workers/sandbox_layer          # 1. directory variable
SERVICE_NAMES := BACKEND FRONTEND ML SANDBOX ...     # 2. dispatch token
ALL_SVC_DIRS  := $(BACKEND_DIR) ... $(SANDBOX_DIR)   # 3. "all services" list
```

### Dispatch
```make
_SVC := $(filter $(SERVICE_NAMES),$(MAKECMDGOALS))
_TARGET_DIRS = $(if $(_SVC),$(foreach s,$(_SVC),$($(s)_DIR)),$(ALL_SVC_DIRS))
```
`make test ML` → `_SVC = ML` → delegates to `$(ML_DIR)`. With no service token, it fans out to
every directory. Each delegated verb runs:

```make
$(MAKE) --no-print-directory -C $$dir <verb>
```

---

## 5. Where a target belongs (strict boundary)

| Concern | Lives in |
|---|---|
| Build/test/lint/format/typecheck/run/deploy/clean **of one service** | that service's **child** Makefile |
| Cross-service fan-out of the verbs above | **root** dispatch (already generic — do not special-case a service in root) |
| Local infra (`up`/`down` Redis, `status`, `kafka-logs`) | **root** |
| Cluster ops (`configuration`, `deploy-infra`, `launch`, gVisor, NetworkPolicy, `clean`/`clean-all`) | **root** |
| Cross-service validation / benchmarking that drives the whole pipeline | **root** target that delegates to `scripts/validation/Makefile` |

**MUST NOT** put service build logic in root, and **MUST NOT** put infra/cluster logic in a
child. If you're editing root to add a per-service rule, you're doing it wrong — extend the
child and the registry instead.

---

## 6. Child Makefile patterns

### Pattern A — Python / Poetry service (the default)

Set a few variables, include the two shared files, done. `python.mk` provides every contract
verb (ruff lint/format, mypy typecheck, pytest, coverage) guarded by a `pyproject.toml` check.

```make
# apps/core-backend/Makefile — the whole file
SERVICE_NAME := core-backend
SRC_DIR      := src
TEST_DIR     := tests
COVERAGE_MIN := 100
DEV_CMD      := poetry run uvicorn src.backend.main:app --reload --port 8000

include ../../makefiles/common.mk
include ../../makefiles/python.mk
```

**MUST** prefer this pattern for any Poetry service — do not hand-roll ruff/mypy/pytest
recipes that `python.mk` already standardises.

### Pattern B — bespoke service (npm, Docker-only, static, infra)

When the toolchain isn't Poetry, include **only** `common.mk` and implement the contract verbs
yourself, using the shared macros. Map the verbs onto the native tool and `skip` the rest:

```make
# apps/workers/sandbox_layer/Makefile (Docker-only) — excerpt
SERVICE_NAME := sandbox-layer
include ../../../makefiles/common.mk

.PHONY: help install build test lint format typecheck run deploy clean

build:
	$(call header,"$(SERVICE_NAME) — build (3 images)")
	docker build -t $(AGENT_IMAGE) -f Dockerfile.agent $(ROOT)

lint:
	$(call skip,"$(SERVICE_NAME)","no pyproject.toml")
```

Real examples to copy from: `frontend` (npm/WXT, adds `test-e2e`), `kafka-schemas` (JSON
validation, `test: lint`), `terraform` (`fmt`/`validate`).

---

## 7. `makefiles/common.mk` reference

Included **first** by every child. Provides:

| Symbol | Purpose |
|---|---|
| `ROOT_DIR` | Monorepo root (walks up to the dir containing `docker-compose.yml`) |
| `DOCKER_COMPOSE`, `POETRY` | Resolved tool invocations |
| `_RST _BOLD _DIM _CYN _YLW _GRN _RED` | ANSI color codes |
| `$(call header,"text")` | Top-level banner line |
| `$(call section,"text")` | Sub-section line |
| `$(call ok,"text")` / `warn` / `err` | Status lines |
| `$(call skip,"name","reason")` | Standard "verb not applicable" line |

**MUST** use these macros for output instead of re-declaring colors or hand-writing `printf`
banners — that is the DRY rule applied to Make.

## 8. `makefiles/python.mk` reference

Included **after** `common.mk` in Poetry services. Inputs (set before the include):

| Variable | Default | Meaning |
|---|---|---|
| `SERVICE_NAME` | dir name | Display name |
| `SRC_DIR` | `src` | Source dir (mypy / coverage target) |
| `TEST_DIR` | `tests` | Test dir |
| `COVERAGE_MIN` | `100` | Coverage gate for `test-cov` |
| `DEV_CMD` | — | Command for `run` (optional) |
| `BUILD_CMD` | — | Override for `build` (optional) |

Provides the full contract plus `test-cov`, each guarded by `_HAS_PYPROJECT` so a service
without a `pyproject.toml` cleanly skips rather than errors. `lint` = `ruff check`,
`format` = `ruff format` + `ruff check --fix`, `typecheck` = `mypy $(SRC_DIR)`,
`test` = `pytest $(TEST_DIR)`. These mirror the settings in [CONTRIBUTING.md §13](CONTRIBUTING.md).

> `scripts/validation/Makefile` is **not** a service child and is **not** in the registry. It
> is a standalone tool Makefile for the sandbox detection harness; the root reaches it only
> through a dedicated delegating target (e.g. `sandbox-validate`), never through the service
> dispatch.

---

## 9. Adding a new service — checklist

1. Create `<path>/Makefile`.
2. Choose a pattern:
   - **Poetry** → set `SERVICE_NAME`/`SRC_DIR`/`TEST_DIR`/`COVERAGE_MIN`(+`DEV_CMD`), then
     `include …/makefiles/common.mk` and `…/python.mk`. (Mind the correct number of `../`.)
   - **Other** → `include …/makefiles/common.mk`, declare `.PHONY`, implement **all nine**
     contract verbs (`skip` the N/A ones).
3. Register it in the **root `Makefile`** in all three spots: `<NAME>_DIR`, `SERVICE_NAMES`,
   `ALL_SVC_DIRS`. Add it to the `help` SERVICES line.
4. Verify standalone: `make -C <path> help` and `make -C <path> lint`.
5. Verify dispatch: `make lint <NAME>` from the repo root.

---

## 10. Rules (summary)

**MUST**
- Implement the full nine-verb contract in every service child Makefile.
- Make every child runnable standalone (`make -C <dir> <verb>`).
- Register new services in the root registry's three lists.
- Use `common.mk` macros for all output; use `python.mk` for Poetry services.
- Make tunable values overridable with `?=`.
- Mark non-file targets `.PHONY`.
- Write everything in **English** ([CONTRIBUTING.md §1](CONTRIBUTING.md)).

**MUST NOT**
- Put per-service build logic in the root Makefile, or infra/cluster logic in a child.
- Duplicate recipes, colors, or banners that `common.mk` already provides.
- Let an N/A verb error or silently no-op — it must `skip`.
- Special-case a single service inside the root dispatch loop.
