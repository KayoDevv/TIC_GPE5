# Verdict Layer: Verdict (The Aggregation Engine)

**Tech:** Python, Redis (for state).

**Code Guidelines:** TDD (pytest-asyncio). Saga pattern implementation.

**Business Context:** "The Aggregation Engine". Consolidates the asynchronous responses and applies the decision matrix.

**Responsibility:** Handle global timeouts. If the Sandbox Layer does not respond within 125s, emit a "Suspect by default" status.

**Kafka Events (Consumed/Produced):**
- **Consumes:** `ml_layer.result`, `sandbox_layer.result`, `llm_layer.result`.
- **Produces:** the final-verdict business event `verdict.result` for the Backend/WebSockets.

## Technical Specifications
- **State Management:** Uses Redis in key-value mode with Time-To-Live (TTL) to temporarily store each Layer's asynchronous returns via the common `job_id` key.
- **Saga Pattern & Orchestration:**
  1. As soon as an intermediate event arrives (`ml_layer.result`, etc.), the microservice updates the partial state in Redis.
  2. Implements a check function (async polling or Pub/Sub) to determine whether the job's full lifecycle is complete.
  3. Strict handling of the **Sandbox Timeout (125s)**: if the Sandbox does not respond within this delay, the Verdict Engine must force the state and close the case.
- **Decision Matrix:**
  - If `ml_layer` assigns a score > 90 -> immediate `blocked` verdict (the rest is ignored or handled in "background" mode for logs).
  - If `llm_layer` concludes an anomaly (`is_malicious: true`) -> `blocked` verdict.
  - On Sandbox timeout -> `warning` or `blocked` status by default, depending on the tenant's risk-tolerance configuration.
- **Output:** Formats and emits the consolidated document to the `verdict.result` topic for Frontend consumption.
