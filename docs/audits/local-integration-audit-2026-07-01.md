# Local end-to-end integration audit — 2026-07-01

**Scope.** Exercise the whole analysis pipeline on a laptop (macOS), backend → ML →
sandbox → LLM → verdict, using **real** files from the ML training corpus
(`apps/workers/ml_layer/data/{benign,malicious}`) and a faked `file.requested`
event. Measure per-worker behaviour and latency, and surface integration defects.

**Verdict up front.** The event backbone works: all three verdict outcomes
(`blocked` / `warning` / `allowed`) were reproduced, including the **real HF-router
LLM** both ways. But two **high-severity integration gaps** mean the happy path for
a *clean, terminal-verdict* file does not reach the user, and the backend never
consumes verdicts at all. Details in [§4](#4-findings--fixes).

---

## 1. Environment

| Piece | How it ran | Notes |
|---|---|---|
| Kafka / MinIO / Redis | `docker compose -f docker-compose.local.yml up -d` | 5 topics + 2 buckets auto-created, all healthy |
| `core-backend` | **not run** (see [F-C](#f-c)) | `/analyze` JWT is `NotImplementedError`; we faked `file.requested` directly instead |
| `ml_layer` | host `poetry run python -m ml_layer.worker` | real ONNX model `models/ml_model_pdf.onnx` |
| `sandbox_layer` | **mock stand-in** | real sandbox is Kubernetes + Firecracker only — impossible on macOS (see [F-sandbox](#sandbox)) |
| `llm_layer` | host `poetry run python -m llm_layer` (dev profile) | real HF router, token supplied; also tested tokenless (degraded fail-safe) |
| `verdict_layer` | host `poetry run python -m verdict_layer.main` | Redis; `SANDBOX_TIMEOUT_SECONDS=20` for a fast reaper test |

**Samples (real corpus files):**
- benign: `data/benign/02eounrel.pdf` — 396 KB, 34 pp, `sha 82f45f65…`
- malicious: `data/malicious/028d311e…` — 1.09 MB, 11 pp, `sha 028d311e…`

The harness (feeder, mock sandbox, collector, analyzer) lives in the session
scratchpad under `scratchpad/harness/` — see [§6](#6-reproduce). It is not yet in
the repo; say the word and I'll land the mock sandbox + feeder under
`scripts/validation/local/`.

---

## 2. Scenario matrix (observed)

All latencies are wall-clock from `file.requested` to the named result, measured
by a single collector tapping every topic (one clock).

| # | Input | ML score | Sandbox verdict | LLM | **Final verdict** | Path exercised |
|---|---|---|---|---|---|---|
| 1 | malicious.pdf, suspicious email | **99** (1429 ms ⚠) | needs_more_context | (short-circuited) | **blocked** @ ~1.4 s | ML-critical (`score>90`) |
| 2 | benign.pdf, neutral email | 0 (76 ms) | **benign** (terminal) | *skipped* | **⚠ NONE — job hung** | reveals [F-A](#f-a) |
| 3 | benign.pdf, sandbox absent | 0 (107 ms) | *(none)* | — | **warning** @ 20 s | reaper timeout → `warning` |
| 4 | benign.pdf, escalation | 0 (77 ms) | needs_more_context | is_malicious=True (degraded) | **blocked** @ ~0.87 s | full ML→sandbox→LLM→verdict |
| 5 | benign.pdf, suspicious email | 0 | needs_more_context (suspicious summary) | **is_malicious=True, conf 90** (real HF) | **blocked** @ 1.68 s | full chain, **real LLM** |
| 6 | benign.pdf, neutral email | 0 | needs_more_context (clean summary) | **is_malicious=False, conf 100** (real HF) | **allowed** @ 1.47 s | full chain, **real LLM** |

Scenario 4 shows the **complete chain resolves end-to-end** in sub-second even with
the LLM degraded. Scenarios 5–6 (real HF-router LLM, token supplied) prove the
**real semantic path both ways**: a suspicious summary → `blocked`, a clean summary
→ **`allowed`** — the clean happy path *does* work **when the sandbox escalates**
(`needs_more_context`). The [F-A](#f-a) hang is specific to *terminal* sandbox
verdicts, where the LLM never fires.

---

## 3. Per-worker findings

### ML Layer — works, but **breaches its 500 ms SLA on the files that matter**
- Discriminates cleanly: malicious `risk_score=99`, benign `0`. Tags fire
  correctly (`high_entropy`, `has_javascript`, `known_malware` on the malware;
  `high_entropy` only on the benign).
- **SLA:** benign (396 KB) = **76–107 ms** ✓. Malicious (1.09 MB) = **~1.36–1.43 s**,
  **consistently** (6/6 feeds breached). This is **not** cold-start — it is
  `PDFFeatureExtractor.extract` (pikepdf parse + entropy + JS regex scan over
  streams) scaling with document complexity. Inference is negligible; feature
  extraction is the bottleneck, and it is worst on exactly the adversarial PDFs
  the layer exists to catch. → see [F-E](#f-e).
- Minor: the benign sample is tagged `high_entropy` — tag noise, not a
  misclassification (score stayed 0).

### <a id="sandbox"></a>Sandbox Layer — not locally runnable (by design)
- `consumer.py` spawns one **Kubernetes Job** per sample (Firecracker/gVisor
  detonation, `kubernetes` client, cluster DNS). There is no local/degraded mode,
  so it cannot run in the compose harness on macOS.
- Covered with a **mock stand-in** that emits schema-valid `sandbox_layer.result`
  across all bands. **This validates wiring/contract only — not detonation
  quality.** Real sandbox efficacy must be measured via the existing k3s
  `scripts/validation` pipeline.

### LLM Layer — works (real model verified); resilient; two config gotchas
- Real HF-router run (token supplied) returns well-formed decisions with genuine
  reasoning that contrasts the email's *claim* vs the file's *behaviour* — e.g.
  scenario 5: *"claimed to be an overdue invoice … but the file attempted to run
  embedded JavaScript and connect to a suspicious domain"* → `is_malicious=true`,
  conf 90. Scenario 6 (clean) → `is_malicious=false`, conf 100.
- **Latency:** warm HF-router inference (guard→prompt→infer→parse) = **660–859 ms**,
  comfortably inside the 3–5 s SLA. The *first* request after startup is a
  cold-start outlier (~30 s router warmup) — worth noting for the TTFT KPI.
- Dev profile reaches `router.huggingface.co` (egress OK), and the degraded path
  (below) was verified by first running with **no** token (clean `401` →
  fail-safe), then re-running with the token for the real decisions.
- **Fail-safe verified:** on auth/inference failure the circuit breaker →
  `AllEndpointsFailed` → `degraded_result` (`is_malicious=True`, confidence `0`) —
  a verdict is always published, the user is never silently dropped. 
- Correctly **skips terminal verdicts** (`benign`/`malicious`/`error`) and only
  resolves `needs_more_context`. This is right for the LLM — but it is the direct
  cause of [F-A](#f-a) downstream.
- Gotcha: `KAFKA_BOOTSTRAP` defaults to **`kafka:9092`** while every other worker
  defaults to `localhost:9092` → [F-D](#f-d).

### Verdict Layer — works for 3 of 4 branches; **hangs on the 4th**
- ML-critical (`score>90`) → `blocked` ✓; LLM-malicious → `blocked` ✓;
  reaper timeout → `warning` ✓.
- **Hangs** when the sandbox returns a *terminal* verdict and ML ≤ 90 → [F-A](#f-a).

### Core Backend — not exercised end-to-end
- `/analyze` unusable ([F-C](#f-c)); verdict consumer never started ([F-B](#f-b)).

---

## 3b. Fixes applied (branch `fix/local-integration-audit`)

All four HIGH/MEDIUM findings are fixed, with tests. Every file changed is at
100% coverage; the remaining `make test-cov` gaps are **pre-existing** on
untouched code (dead DI helpers, `ws.py` error paths, `worker.py` error branch).

| Finding | Fix | Verification |
|---|---|---|
| **F-A** | Plumbed the sandbox verdict through `main → saga → state_store → decision_matrix`. `is_complete()` no longer waits for an LLM result on a *terminal* verdict or timeout; `decide()` now blocks on sandbox `malicious` and warns on sandbox `error`. | verdict_layer **100%** cov, 67 tests. **Live:** benign terminal → `allowed`, malicious terminal → `blocked`, both without the LLM (previously hung). |
| **F-B** | `lifespan` now starts a `KafkaSubscriber` on `verdict.result` whose handler (`build_verdict_handler`) calls `verdict_dispatcher.dispatch`. | `verdict_consumer.py` **100%** cov; lifespan start/stop + handler unit-tested. |
| **F-C** | Env-gated `AUTH_DEV_MODE` in `Settings` + bypass in `verify_jwt` (loud warning, fixed dev identity) so ingress is testable before SSO lands. | new `TestDevMode` test; ruff/mypy clean. |
| **F-E** | Vectorised `shannon_entropy` with numpy `bincount` (was a 126M-call pure-Python byte loop). | **Identical values** (max Δ 2e-14); malicious PDF extraction **1429 ms → 197 ms**, back inside the 500 ms SLA. `common.py`/`pdf.py`/`analyzer.py` **100%** cov. |

Not addressed (LOW, out of the requested HIGH/MED scope): F-D (`llm_layer` Kafka
default) and F-F (Kafka message key).

---

## 4. Findings & fixes

### <a id="f-a"></a>F-A — Verdict saga hangs on a terminal sandbox verdict · **HIGH**
`StateStore.is_complete()` requires `ml_score` **and** `sandbox_received` **and**
`llm_is_malicious`. But `llm_layer` only emits for `needs_more_context`; for a
terminal `benign`/`malicious`/`error` sandbox verdict it emits **nothing**. The
reaper only rescues jobs where the sandbox was *never received* — so a job with a
terminal sandbox verdict and sub-critical ML score is **never resolved** and dies
at the Redis TTL (300 s). Reproduced in scenario 2: benign file → **no verdict**.
Impact: **every clean file with ML ≤ 90 silently produces no verdict** → the
backend WS times out (130 s) → the user sees nothing.

*Fix (pick one, verdict-side is safest):* in `is_complete()` / the saga, treat a
terminal sandbox verdict as sufficient (don't wait for an LLM result that will
never come); **or** have `llm_layer` emit a pass-through `llm_layer.result` for
terminal verdicts; **or** extend the reaper to also resolve jobs stuck awaiting
the LLM. The verdict layer must not depend on an LLM message that the LLM
contract says won't be sent.

### <a id="f-b"></a>F-B — Core backend never consumes `verdict.result` · **HIGH**
`main.py` `lifespan` builds a `VerdictDispatcher` but starts **no**
`KafkaSubscriber` on `verdict.result`. The WS route in `routes/ws.py` registers a
callback, but nothing ever calls `dispatcher.dispatch()`. So even when the verdict
layer emits, **the backend never receives it** and the WebSocket cannot deliver it
to the extension. The "verdict → backend → frontend" leg is unwired.

*Fix:* start a `KafkaSubscriber(verdict.result, VerdictResultEvent)` in `lifespan`
whose handler calls `app.state.verdict_dispatcher.dispatch(job_id, payload)`.

### <a id="f-c"></a>F-C — `/analyze` auth is `NotImplementedError` · **MEDIUM**
`auth._get_public_key` raises `NotImplementedError`, and there is no dev bypass, so
the real ingress endpoint cannot be tested locally at all. We faked `file.requested`
directly (as requested). *Fix:* a dev auth mode (static key / disabled JWT behind
an env flag) so the HTTP ingress is testable before SSO lands.

### <a id="f-d"></a>F-D — `llm_layer` Kafka default diverges · **LOW**
`llm_layer` defaults `KAFKA_BOOTSTRAP=kafka:9092`; all others use
`localhost:9092`. Easy local misconfig. *Fix:* align defaults (or centralise in
`zt_shared`).

### <a id="f-e"></a>F-E — ML feature extraction blows the 500 ms SLA on large PDFs · **MEDIUM**
~1.4 s (≈3× budget) on the 1.09 MB sample, consistently. *Fix:* profile/optimise
`PDFFeatureExtractor` (cap object/stream traversal, bound regex scan bytes like the
existing 1 MB entropy cap), and/or move to a process pool so parse cost can't
starve the async loop under load.

### <a id="f-f"></a>F-F — Kafka messages carry no key · **LOW–MEDIUM**
`KafkaPublisher.publish` calls `send_and_wait(topic, value=…)` with **no key**, so
events round-robin across the 3 partitions. CLAUDE.md states `job_id` is the
message key "to guarantee partition ordering" — that guarantee is not met. Harmless
for the current per-job idempotent consumers, but it contradicts the documented
contract. *Fix:* key on `job_id` in `publish`.

---

## 5. What was NOT proven
- **Real sandbox detonation quality** — only the contract/wiring, via a mock.
  Real sandbox efficacy must be measured via the k3s `scripts/validation` pipeline.
- **Backend HTTP ingress and WS delivery** — blocked by F-C and F-B.

Real LLM semantic accuracy **was** verified both ways (scenarios 5–6): suspicious
→ `blocked`, clean → `allowed`. Note the clean happy path only reaches a verdict
when the sandbox escalates (`needs_more_context`); for a *terminal* clean verdict
it still hangs — that is [F-A](#f-a), unrelated to the LLM.

---

## 6. Reproduce

```bash
# infra
docker compose -f docker-compose.local.yml up -d

# workers (each in its own shell, from the repo root)
cd apps/workers/ml_layer      && poetry run python -m ml_layer.worker
cd apps/workers/verdict_layer && SANDBOX_TIMEOUT_SECONDS=20 REAPER_INTERVAL_SECONDS=3 poetry run python -m verdict_layer.main
cd apps/workers/llm_layer     && KAFKA_BOOTSTRAP=localhost:9092 poetry run python -m llm_layer   # + HF_TOKEN for real

# harness (scratchpad/harness/)
poetry run python collect.py &                                  # tap all 5 topics
SANDBOX_BAND=needs_more_context SANDBOX_FLAVOR=suspicious \
  poetry run python mock_sandbox.py &                           # sandbox stand-in
poetry run python feed.py samples/malicious.pdf --subject "..." # fake file.requested
poetry run python analyze.py                                    # per-job timeline + latency
```
