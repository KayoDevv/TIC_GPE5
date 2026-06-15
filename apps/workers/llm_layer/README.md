# LLM Layer — The Semantic Analyst

Correlates the **email context** with the **sandbox detonation report** to decide
whether an attached file is malicious, and produces a **plain-language
explanation** for a non-technical user (e.g. an SME IT manager).

- **Consumes:** `sandbox_layer.result` (`SandboxLayerResultEvent`)
- **Produces:** `llm_layer.result` (`LlmLayerResultEvent`) — binary
  `is_malicious` + `explanation_text` (+ optional `confidence_score`)

The wire contracts are the canonical Pydantic models in
`packages/core` (`zt_shared.models.events`); this worker reuses them and the
shared Kafka helpers (`zt_shared.kafka`) rather than redefining anything.

## Architecture (functional core / imperative shell)

```
sandbox_layer.result
        │  KafkaSubscriber[SandboxResultIn]   (zt_shared)
        ▼
   guard ──► prompt_builder ──► circuit_breaker ──► llm_client ──► response_parser ──► decision
   (D4)        (D4 envelope)     (Llama3 ▸retry▸Mistral)            (strict/lenient)    (rules)
        │                                                                                 │
        └────────────────── pipeline.analyse() ───────────────────────────────────────► │
                                                                                          ▼
                                                                         llm_layer.result (KafkaPublisher)
```

- **functional core** (`guard`, `prompt_builder`, `response_parser`, `decision`,
  `circuit_breaker`, `pipeline`) is pure/deterministic and fully unit-tested;
- **imperative shell** (`worker`) only wires Kafka + the async LLM client.

## Dev vs prod — one environment variable

A single switch, `VLLM_URL`, selects the profile; the code path is identical.

| | `VLLM_URL` unset (dev) | `VLLM_URL` set (prod) |
|---|---|---|
| Endpoint | HuggingFace router (OpenAI-compatible) | on-prem vLLM |
| Guided decoding | off → lenient JSON parser | `guided_json` enforced |
| Timeout | 30 s (cold start) | 8 s (SLA 3–5 s) |
| Fallback | Mistral-7B | Mistral-7B |

### Key environment variables

| Var | Default | Meaning |
|---|---|---|
| `VLLM_URL` | _unset_ | set → production profile (vLLM base URL) |
| `VLLM_API_KEY` / `HF_TOKEN` | _unset_ | bearer token for prod / dev |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | broker |
| `TOPIC_IN` / `TOPIC_OUT` | `sandbox_layer.result` / `llm_layer.result` | topics |
| `KAFKA_GROUP` | `llm-layer` | consumer group |
| `LLM_TEMPERATURE` | `0.2` | must stay within 0.1–0.3 |
| `LLM_TIMEOUT_S` | `8` (prod) / `30` (dev) | per-request timeout |

See `.env.example`.

## Prompt-injection defence (Cahier D4 / note.txt)

The attachment is hostile input, so every untrusted field (email sender/subject/
body, behaviour summary, IOC values) is:

1. **Re-scanned** for raw chat-template control tokens (`scan_control_tokens`).
   The sandbox is responsible for stripping them; if one survived we **fail loud**
   (error log + a cautious degraded result) instead of silently working around a
   sandbox regression. The same check is enforced at build time by
   `contract/validate_sandbox_input.py` in the `sandbox-llm-contract` CI workflow.
2. **Encapsulated** inside `<untrusted_sample_data>` delimiters, with delimiter
   spoofing neutralised, and the system prompt instructs the model to treat the
   content strictly as data — never as instructions.

The model never sees a verdict it can be argued out of: hard security gating
(ML/Sandbox criticals override the LLM) is the **Verdict Engine's** job; this
layer is advisory.

## Resilience

`primary (Llama 3) → 1 retry on transient error → fallback (Mistral) → degraded`.
If inference or parsing fails, the pipeline emits a cautious degraded result
(`is_malicious=true`, `confidence_score=0`, explanatory text) so the Saga always
completes and the user is never silently allowed through.

## Develop

```bash
poetry install
poetry run pytest          # 62 tests, 100% branch coverage enforced
poetry run ruff check src tests
poetry run mypy src/llm_layer
python -m llm_layer        # run the worker (reads env)
```

## Contract

`contract/CONTRACT_VERSION` (= `1`) must equal the sandbox side; the CI workflow
`sandbox-llm-contract.yml` fails the PR on any mismatch or if a golden sandbox
fixture stops satisfying `validate_sandbox_input.py`. This worker reads only the
canonical fields plus the optional `_meta.prompt_injection_filtered`, so no
version bump was required.
