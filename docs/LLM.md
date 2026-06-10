# CHARON — LLM Layer 

---

## Model

### Primary: `meta-llama/Meta-Llama-3-8B-Instruct`

**Provider**: Meta  
**License**: Apache 2.0 (commercially unrestricted)  
**Parameters**: 8 billion  
**Architecture**: Transformer (decoder-only)  
**Context window**: 8,192 tokens  
**Training data**: Publicly available datasets + proprietary instruction-tuning corpus  

**Why Llama 3 8B**:
- Unrestricted commercial license (Apache 2.0) — no royalties, no usage restrictions
- Strong instruction following on bounded reasoning tasks (email ↔ sandbox correlation)
- Available natively on HuggingFace Serverless Inference API
- Mature ecosystem for fine-tuning (LoRA tooling well-documented)
- 8B parameters = good precision-to-latency ratio for real-time inference

### Fallback: `mistralai/Mistral-7B-Instruct-v0.3`

**Provider**: Mistral AI  
**License**: Apache 2.0  
**Parameters**: 7 billion  

Activated by circuit-breaker if Llama 3 is unavailable or experiencing cold start > 8 seconds. Same license, smaller memory footprint, slightly faster inference.

---

## Inference Infrastructure

### Development Phase: HuggingFace Serverless Inference API

**Service**: `api-inference.huggingface.co`  
**Authentication**: Bearer token (HuggingFace user token)  
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

**Use case**: Rapid iteration on prompts, response parsing, Kafka integration testing.

### Production Phase: vLLM On-Premise

**Service**: Self-hosted vLLM server  
**Hardware**: NVIDIA A10G (24 GB) or RTX 4090 (24 GB)  
**Quantization**: AWQ INT4 (~4.5 GB VRAM per model)  
**Deployment**: Kubernetes pod (K3s cluster)  
**Port**: 8000 (primary Llama 3), 8001 (fallback Mistral 7B)  
**API format**: OpenAI-compatible (`/v1/chat/completions`)  

**Why vLLM**:
- Native support for PagedAttention (KV cache optimization)
- Continuous batching (efficient GPU utilization with sparse requests)
- OpenAI API compatibility (zero code changes from dev)
- AWQ quantization support (4-bit, minimal quality loss)
- Highly optimized inference (3–5 s latency achievable)

**Network security**:
- TLS 1.3 endpoint encryption (self-signed cert in dev, proper cert in production)
- API key authentication (Bearer token)
- Internal K8s namespace isolation
- No public network exposure

---

## Inference Parameters

| Parameter | Value | Rationale |
|---|---|---|
| **Temperature** | 0.2 | Constraint: 0.1–0.3. Stability required for security decisions. Random variation acceptable for UI text, but verdict must be deterministic. |
| **Top-p (nucleus sampling)** | 0.9 | Standard default. Prevents improbable token selection while preserving model diversity. |
| **Max tokens (output)** | 512 | Balanced for 3–5 s latency + concise explanation for UI. Prevents verbose responses. |
| **Max tokens (context)** | 8,192 | Llama 3 context window. Prompt (system + user + sandbox report) fits easily. |

**Temperature justification**: 
- At 0.2: Llama 3 selects the most likely token ~95% of the time, with rare alternative tokens.
- Ensures the same malware report produces the same verdict every time (reproducibility).
- Still allows slight variation in explanation phrasing (user-facing text).

---

## Communication Protocol

### Worker → LLM Service

**Protocol**: HTTPS REST  
**Endpoint**: `/v1/chat/completions`  
**Method**: POST  
**Content-Type**: application/json  
**Authentication**: Bearer token (HF or internal API key)  

**Timeout**: 30 seconds (development), 8 seconds (production)

- Development: 30 s to account for HuggingFace cold start (20–60 s possible)
- Production: 8 s allows one retry before SLA breach (total LLM time ≤ 5 s)

**Request format**: OpenAI-compatible messages array:
- `system` role: LLM instructions, role definition, output format specification
- `user` role: sandbox report + email content + correlation request

**Response format**: JSON object with:
- `choices[0].message.content`: String (LLM-generated text, hopefully JSON)

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

Python's asyncio is essential because the worker is I/O-bound: waiting on Kafka consumer, waiting on network calls to LLM, waiting on MinIO for email content. Async allows a single worker thread to handle hundreds of concurrent analyses.

### LLM Client Library

**Primary**: `huggingface_hub.InferenceClient` (official HuggingFace library)  
**Fallback**: `httpx` (async HTTP client, manual API calls)  

`InferenceClient` handles:
- Bearer token injection
- Automatic retries on transient errors
- OpenAI API compatibility layer
- Model endpoint switching (HF Serverless vs vLLM)

### Supporting Libraries

| Library | Purpose |
|---|---|
| `aiokafka` | Async Kafka consumer/producer |
| `pydantic` | Schema validation for Kafka messages |
| `json` + `re` | Response parsing and JSON error recovery |
| `minio` | Async S3-compatible client (fetch email content) |

---

## Message Flow

### Input: Kafka Topic `sandbox_layer.result`

The worker consumes events where:
- `sandbox_verdict == "suspect"` (gate-kept condition)
- Payload includes: `sandbox_score`, `triggered_hypotheses`, `iocs`, `email_content`

### Processing

1. **Fetch email context** (optional, from MinIO if available)
2. **Build prompt**: system instructions + formatted sandbox report + email content
3. **Call LLM**: POST to HuggingFace Serverless or vLLM endpoint
4. **Parse response**: extract JSON, validate schema, handle malformed responses
5. **Apply verdict logic**: LLM cannot upgrade Orange to Red (immutable rule)

### Output: Kafka Topic `llm_layer.result`

The worker publishes:
```
{
  "file_id": "uuid",
  "llm_verdict": "suspect" | "sain",
  "explanation": "user-facing text",
  "mitre_tag": "T1XXX" | null,
  "technical_detail": "for logs",
  "llm_error": null | "error_code"
}
```

---

## Constraints

| Constraint | Value | Reason |
|---|---|---|
| **Temperature range** | 0.1–0.3 | Project requirement for decision stability |
| **Max output tokens** | 512 | SLA: 3–5 s total + concise explanation |
| **Activation condition** | Orange verdicts only | Reduce LLM calls; reserve for uncertain cases |
| **Data residency** | On-premise only (prod) | GDPR + NIS2 — no sending malware to external APIs |
| **Uptime requirement** | 99.5% (degraded mode acceptable) | Circuit-breaker fallback ensures no user blocking |
| **Cost per inference** | $0 (model free) | Llama 3 Apache 2.0; infra cost only |

---

## Development vs. Production Toggle

**Single environment variable controls both**:
- If `VLLM_URL` is not set → use HuggingFace Serverless (development)
- If `VLLM_URL` is set → use on-premise vLLM (production)

**No code changes required.** The Python worker remains identical.

---

## Deployment

### Development

```
HF_TOKEN=hf_xxxxxxxxxxxx
LLM_TEMPERATURE=0.2
KAFKA_BOOTSTRAP=kafka:9092
```

Worker calls: `api-inference.huggingface.co/models/meta-llama/Meta-Llama-3-8B-Instruct/v1/chat/completions`

### Production

```
VLLM_URL=https://gpu-node.charon.internal:8000
VLLM_API_KEY=internal-secret
LLM_TEMPERATURE=0.2
KAFKA_BOOTSTRAP=kafka:9092
```

Worker calls: `https://gpu-node.charon.internal:8000/v1/chat/completions`

---

## Dependencies Summary

| Dependency | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Runtime |
| huggingface_hub | 0.20+ | HF Serverless client |
| aiokafka | 0.10+ | Async Kafka |
| httpx | 0.25+ | Async HTTP (fallback) |
| pydantic | 2.0+ | Message validation |
| minio | 7.2+ | S3-compatible storage client |

---

## Next Steps (Implementation Order)

1. **Prepare HF token** and agree to Llama 3 model terms
2. **Test HuggingFace Serverless** with sample prompts (curl or Postman)
3. **Build Kafka consumer** that filters Orange verdicts
4. **Implement prompt builder** with system + user message templates
5. **Implement response parser** with JSON error recovery
6. **Write circuit-breaker** for Mistral fallback
7. **Test end-to-end** on fictitious sandbox reports
8. **Deploy vLLM to GPU node** (production only)
9. **Integration test** with full pipeline
10. **Monitor SLA** with Prometheus metrics
