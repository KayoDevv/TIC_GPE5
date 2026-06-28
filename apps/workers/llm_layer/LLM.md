# LLM Worker — Technology Stack

> **Business context — "The Semantic Analyst"**: correlates the initial email context with the technical sandbox results to determine the real intent of the file, and translates technical logs into a clear human-readable summary for non-technical users.

---

## Model

### Primary: `meta-llama/Llama-3.3-70B-Instruct`

**Provider**: Meta
**License**: Llama 3.3 Community License
**Parameters**: 70 billion
**Architecture**: Transformer (decoder-only)
**Context window**: 128,000 tokens

**Why Llama 3.3 70B**:
- Strong instruction following on bounded reasoning tasks (email <-> sandbox correlation)
- Served by the HuggingFace Inference Providers router in development, same OpenAI-compatible API as the production vLLM
- The default model id is overridable via `LLM_MODEL_PRIMARY` — the worker code is model-agnostic

> Note: the default is `Llama-3.3-70B-Instruct`. Earlier specs targeted the 8B for latency; the larger model is the current choice and can be swapped per environment via env vars.

### Fallback: `mistralai/Mistral-7B-Instruct-v0.3`

**Provider**: Mistral AI
**License**: Apache 2.0
**Parameters**: 7 billion

Activated by circuit-breaker if Llama 3 is unavailable or experiencing cold start > 8 seconds. Same license, smaller memory footprint, slightly faster inference.

---

## Inference Infrastructure

### Development Phase: HuggingFace Serverless Inference API

**Service**: `router.huggingface.co` (Inference Providers, `/v1/chat/completions`)
**Authentication**: Bearer token (HuggingFace fine-grained token with the "Make calls to Inference Providers" permission)
**Hosting**: Managed by HuggingFace (no GPU provisioning)
**Free quota**: ~1,000 requests/day
**API format**: OpenAI-compatible (`/v1/chat/completions`)

**Advantages**:
- Zero infrastructure to manage
- No GPU purchase or rental required
- Immediate availability for development testing
- Same API format as production (vLLM)

**Disadvantages**:
- Cold start latency: 20–60 seconds if model not pre-loaded
- Variable latency under HuggingFace load
- GDPR violation if sending real malware samples — development only with fictitious data

**Use case**: Rapid iteration on prompts, response validation, Kafka integration testing.

### Production Phase: vLLM On-Premise

**Service**: Self-hosted vLLM server
**Hardware**: NVIDIA A10G (24 GB) or RTX 4090 (24 GB)
**Quantization**: AWQ INT4 (~4.5 GB VRAM per model)
**Deployment**: Kubernetes pod (K3s cluster)
**Port**: 8000 (primary Llama 3), 8001 (fallback Mistral 7B)
**API format**: OpenAI-compatible (`/v1/chat/completions`)

**Why vLLM**:
- Native support for PagedAttention (KV cache optimization — optimizes VRAM usage)
- Continuous batching (efficient GPU utilization with sparse requests)
- High token/sec throughput and low Time-To-First-Token (TTFT) — required by the 3–5 s SLA
- OpenAI API compatibility (zero code changes from dev)
- AWQ quantization support (4-bit, minimal quality loss)
- Native guided decoding / structured outputs (JSON schema enforcement)

**Transport decision — REST over gRPC**: a remote gRPC server was considered as an alternative inference transport. REST (OpenAI-compatible) was retained because it is natively exposed by both vLLM and the HuggingFace Serverless API, which guarantees an identical client code path in development and production. gRPC would require maintaining a separate client and protobuf contract for no measurable latency gain at this request volume (LLM is only invoked on Orange verdicts).

**Network security**:
- TLS 1.3 endpoint encryption (self-signed cert in dev, proper cert in production)
- API key authentication (Bearer token)
- Internal K8s namespace isolation
- No public network exposure

---

## Inference Parameters

| Parameter | Value | Rationale |
|---|---|---|
| **Temperature** | 0.2 | Constraint: 0.1–0.3. Very low temperature to avoid hallucinations on security decisions. Verdict must be deterministic; slight variation acceptable for UI text. |
| **Top-p (nucleus sampling)** | 0.9 | Standard default. Prevents improbable token selection while preserving model diversity. |
| **Max tokens (output)** | 512 | Balanced for 3–5 s latency + concise explanation for UI. Prevents verbose responses. |
| **Max tokens (context)** | 128,000 | Llama 3.3 70B context window. Prompt (system + user + sandbox report) fits easily. |

**Temperature justification**:
- At 0.2: Llama 3 selects the most likely token ~95% of the time, with rare alternative tokens.
- Ensures the same malware report produces the same verdict every time (reproducibility).
- Still allows slight variation in explanation phrasing (user-facing text).

---

## Prompt Engineering

**Strict template** — the prompt is not free-form. It is assembled from a fixed structure:

- **System message**: role definition ("defensive cybersecurity analyst"), output format specification, immutable rules (never provide attack reproduction details, verdict boundaries)
- **User message**: injects the business context (sender, subject, email body) and links it to the IOC JSON report generated by the Sandbox Layer

The template enforces correlation: the LLM is explicitly asked to compare what the email *claims* (e.g. "invoice PDF") against what the sandbox *observed* (e.g. network connection attempt, crontab modification).

---

## Structured Outputs (Guided Decoding)

**Mechanism**: vLLM guided decoding (`guided_json` parameter, backed by Outlines)

The LLM output schema is defined as a Pydantic model and passed as a JSON Schema in the API request. vLLM constrains token generation so the output is **guaranteed to be syntactically valid JSON conforming to the schema** — no regex recovery, no malformed responses.

**Schema enforced**:

| Field | Type | Constraint |
|---|---|---|
| `is_malicious` | boolean | Binary decision (Option A, implemented) |
| `explanation_text` | string | User-facing text, non-technical (e.g. understandable by an SME's IT manager) |
| `confidence_score` | integer or null | 0–100 confidence in the decision |

**Security benefit**: the verdict field is constrained at the decoding level. The model cannot hallucinate an out-of-schema verdict value, which removes an entire class of parsing edge cases from the security decision path.

**Environment caveat**:
- **Production (vLLM)**: guided decoding is native and always enforced.
- **Development (HF Serverless)**: structured output support is not guaranteed across models. A lightweight fallback parser handles this case in development only; it is dead code in production.

### Resolved — verdict field format (Option A, binary)

The implemented contract is **Option A — binary**: the LLM emits `is_malicious: boolean` + `explanation_text: string` + `confidence_score: integer`. It is a binary *signal*, not the final decision — the Verdict Engine (which prioritises the ML/Sandbox layers) makes the allow/block/warning call. The LLM cannot force-block or force-allow; it only resolves the grey (`needs_more_context`) band. The Kafka schema reflects this: `packages/kafka-schemas/llm_layer.result.json`.

---

## Communication Protocol

### Worker -> LLM Service

**Protocol**: HTTPS REST
**Endpoint**: `/v1/chat/completions`
**Method**: POST
**Content-Type**: application/json
**Authentication**: Bearer token (HF or internal API key)

**Timeout**: 30 seconds (development), 8 seconds (production)

- Development: 30 s to account for HuggingFace cold start (20–60 s possible)
- Production: 8 s allows one retry before SLA breach (total LLM time <= 5 s)

**Request format**: OpenAI-compatible messages array:
- `system` role: LLM instructions, role definition, output format specification
- `user` role: sandbox report + email content + correlation request

**Response format**: JSON object with:
- `choices[0].message.content`: schema-valid JSON (guided decoding in production)

### Fallback Strategy

If Llama 3 endpoint times out or returns HTTP error:
1. Retry once on same endpoint
2. If retry fails, switch to Mistral 7B endpoint
3. If Mistral also fails, emit degraded verdict (Orange) with error flag
4. Never block user analysis pipeline — always publish a result

---

## Language & Libraries

### Worker Implementation

**Language**: Python 3.12
**Async runtime**: asyncio
**Code guidelines**: strict TDD with `pytest-asyncio` — every component (prompt builder, client, parser, verdict logic) is developed test-first

Python's asyncio is essential because the worker is I/O-bound: waiting on the Kafka consumer and on network calls to the LLM. Async lets a single worker handle many concurrent analyses. The email context arrives inline in the sandbox event — the LLM layer does not fetch from MinIO.

### LLM Client Library

**`httpx`** (async HTTP client) — a single OpenAI-compatible code path drives both
the HuggingFace router (dev) and vLLM (prod). REST was chosen over a provider SDK so
the same client serves both profiles with no extra SDK/protobuf contract. The worker
injects the Bearer token and applies the per-request timeout; the **circuit breaker**
(not the HTTP lib) owns retries and the primary→fallback switch.

### Supporting Libraries

| Library | Purpose |
|---|---|
| `aiokafka` | Async Kafka consumer/producer (via `zt_shared`) |
| `httpx` | Async OpenAI-compatible HTTP client (dev HF router + prod vLLM) |
| `pydantic` | Kafka message validation + JSON Schema source for guided decoding |
| `pytest-asyncio` | TDD test framework (async test support) |
| `json` + `re` | Fallback parsing (development / HF router only) |

---

## Message Flow

### Input: Kafka Topic `sandbox_layer.result`

The worker consumes events where:
- `verdict == "needs_more_context"` (the grey band; `benign`/`malicious`/`error` are skipped, a missing verdict is still analysed)
- Payload carries the technical report **and** the inline email context: `anomaly_score`, `signals`, `iocs`, `behavior_summary`, `email_context`

### Processing

1. **Parse and aggregate** the technical data from the Sandbox report
2. **Build prompt** from the strict template: system instructions + email business context (sender, subject, body) + IOC JSON report
3. **Call LLM asynchronously**: POST to HuggingFace Serverless or vLLM endpoint (temperature 0.2)
4. **Validate response**: guided decoding guarantees schema-valid JSON in production (vLLM); a lightweight fallback parser covers development (HF Serverless)
5. **Apply verdict logic**: cap confidence on partial evidence (sandbox timeout), append the prompt-injection hint when the sandbox neutralised injection-shaped content, then publish the binary signal

### Output: Kafka Topic `llm_layer.result`

The worker publishes the binary signal (`is_malicious`), the user-facing `explanation_text`, and `confidence_score` (`LlmLayerResultEvent`). On inference/parse failure it publishes a cautious degraded result (`is_malicious=true`, `confidence=0`) so a verdict is always emitted.

**Output trust**: `explanation_text` is generated by the LLM from attacker-influenced input. The worker neutralises it at the output boundary (`guard.sanitize_explanation`: control/non-printable chars, chat-template tokens, turn prefixes, length cap), but the Frontend MUST still output-encode it (HTML-escape) — output encoding is contextual to the consumer, not the producer.

---

## Constraints

| Constraint | Value | Reason |
|---|---|---|
| **Temperature range** | 0.1–0.3 | Project requirement — no hallucinations on security decisions |
| **Max output tokens** | 512 | SLA: 3–5 s total + concise explanation |
| **SLA** | 3–5 s for full explanation generation | Requires high token/sec model + low TTFT |
| **Activation condition** | Orange verdicts only | Reduce LLM calls; reserve for uncertain cases |
| **Data residency** | On-premise only (prod) | GDPR + NIS2 — no sending malware to external APIs |
| **Uptime requirement** | 99.5% (degraded mode acceptable) | Circuit-breaker fallback ensures no user blocking |
| **Cost per inference** | $0 (model free) | Llama 3 Apache 2.0; infra cost only |
| **Code quality** | TDD strict (pytest-asyncio) | Team-wide guideline |

---

## Development vs. Production Toggle

**Single environment variable controls both**:
- If `VLLM_URL` is not set -> use HuggingFace Serverless (development)
- If `VLLM_URL` is set -> use on-premise vLLM (production)

**No code changes required.** The Python worker remains identical.

### Development

```
HF_TOKEN=hf_xxxxxxxxxxxx
LLM_TEMPERATURE=0.2
KAFKA_BOOTSTRAP=kafka:9092
```

### Production

```
VLLM_URL=https://gpu-node.charon.internal:8000
VLLM_API_KEY=internal-secret
LLM_TEMPERATURE=0.2
KAFKA_BOOTSTRAP=kafka:9092
```

---

## Dependencies Summary

| Dependency | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Runtime |
| aiokafka | 0.10+ | Async Kafka (via zt_shared) |
| httpx | 0.28+ | Async OpenAI-compatible HTTP client (dev + prod) |
| pydantic | 2.0+ | Message validation + guided decoding schema |
| pytest-asyncio | 0.24+ | TDD test framework |

---

## Next Steps (Implementation Order)

1. ~~Resolve the verdict contract decision~~ — **done**: Option A (binary `is_malicious`); the `llm_layer.result` schema is finalised
2. **Prepare HF token** and agree to Llama 3 model terms
3. **Test HuggingFace Serverless** with sample prompts (curl or Postman)
4. **Write tests first (TDD)**, then build the Kafka consumer that filters Orange verdicts
5. **Implement prompt builder** from the strict template (tests first)
6. **Define Pydantic output schema** and wire guided decoding (vLLM) + fallback parser (dev only)
7. **Write circuit-breaker** for Mistral fallback
8. **Test end-to-end** on fictitious sandbox reports
9. **Deploy vLLM to GPU node** (production only) and validate TTFT / SLA
10. **Monitor SLA** with Prometheus metrics
