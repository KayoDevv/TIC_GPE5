# Core Backend — API Gateway

Secure entry point for the GPE-ETNA platform. Handles file upload, authentication, async analysis dispatch, and real-time verdict delivery.

**Stack:** Python · FastAPI · aiokafka · boto3 (S3/MinIO) · python-jose (JWT)

---

## User Flow

```
1. User opens a webmail in the browser
       │
       ▼
2. Browser extension detects a download link (content script)
       │
       ▼
3. Extension sends the file + email context to POST /api/v1/analyze
   with Bearer JWT in Authorization header
       │
       ├── [400] File exceeds 35 MB → reject immediately, no S3 upload
       ├── [401] Invalid / expired JWT → reject
       │
       ▼
4. Backend computes SHA-256, uploads file to S3/MinIO
       │
       ▼
5. Backend creates a job_id (UUID), publishes file.requested to Kafka
       │
       ▼
6. Backend returns 202 Accepted { job_id }
       │
       ▼
7. Extension opens WebSocket connection: WS /api/v1/ws/{job_id}
       │
       ▼
8. Verdict Layer emits verdict.result to Kafka
   Backend consumes it → pushes JSON payload over WebSocket
       │
       ▼
9. Extension receives verdict, updates UI:
   allowed → green | blocked → red | warning → orange + side panel
       │
       ▼
10. WebSocket closed by server after verdict is delivered
```

---

## Routes

### `POST /api/v1/analyze`

Submit a file for analysis.

**Auth:** `Authorization: Bearer <JWT>` (SSO-issued token)

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | binary | yes | The attachment to analyze (max 35 MB) |
| `sender` | string (email) | yes | Email address of the sender |
| `subject` | string | yes | Subject line of the email |
| `body_text` | string | yes | Plain-text body of the email (used by LLM Layer) |

**Responses:**

| Status | Body | Condition |
|---|---|---|
| `202 Accepted` | `AnalyzeResponseDTO` | File accepted, analysis started |
| `400 Bad Request` | `ErrorDTO` | File exceeds 35 MB or missing fields |
| `401 Unauthorized` | `ErrorDTO` | Missing, invalid, or expired JWT |
| `413 Payload Too Large` | `ErrorDTO` | Enforced at reverse-proxy level before FastAPI |
| `500 Internal Server Error` | `ErrorDTO` | S3 upload or Kafka publish failure |

---

### `WebSocket /api/v1/ws/{job_id}`

Real-time verdict delivery channel.

**Auth:** JWT passed as query parameter `?token=<JWT>` (WebSocket does not support headers).

**Lifecycle:**
1. Client connects → server validates JWT and `job_id` format
2. Server holds the connection open, subscribed to the `verdict.result` Kafka topic
3. On receipt of matching `job_id` verdict → server sends `VerdictMessageDTO` as JSON text frame
4. Server closes the connection (code `1000`)

**Error cases:**

| Condition | Behavior |
|---|---|
| Invalid JWT | Close with code `4001` |
| Invalid `job_id` format | Close with code `4003` |
| No verdict after 130 s | Close with code `4008` (timeout — slightly above Sandbox 125 s limit) |

---

### `GET /api/v1/health`

Liveness probe for Kubernetes.

**Auth:** None

**Response `200`:**
```json
{ "status": "ok" }
```

---

## DTOs

### Request

#### `AnalyzeRequestDTO`
Parsed from `multipart/form-data` fields.

```python
class EmailContextDTO(BaseModel):
    sender: EmailStr
    subject: str
    body_text: str
```

> `file` is handled as `UploadFile` by FastAPI directly — not part of the Pydantic model.

---

### Response

#### `AnalyzeResponseDTO`
Returned on `202 Accepted`.

```python
class AnalyzeResponseDTO(BaseModel):
    job_id: UUID
    message: str = "Analysis started. Connect to WebSocket for the verdict."
```

#### `VerdictMessageDTO`
Pushed over WebSocket as a JSON text frame.

```python
class TechnicalSummaryDTO(BaseModel):
    ml_layer_score: int | None = None
    sandbox_layer_iocs: list[dict] | None = None
    sandbox_layer_timeout: bool | None = None
    llm_layer_malicious: bool | None = None

class VerdictMessageDTO(BaseModel):
    job_id: UUID
    final_decision: Literal["allowed", "blocked", "warning"]
    user_explanation: str | None = None
    technical_summary: TechnicalSummaryDTO | None = None
    timestamp: datetime
```

#### `ErrorDTO`
Returned on all 4xx / 5xx responses.

```python
class ErrorDTO(BaseModel):
    error: str        # machine-readable code, e.g. "FILE_TOO_LARGE"
    message: str      # human-readable description
```

**Error codes:**

| `error` | HTTP | Meaning |
|---|---|---|
| `FILE_TOO_LARGE` | 400 | File exceeds 35 MB |
| `MISSING_FIELDS` | 400 | Required form fields absent |
| `INVALID_TOKEN` | 401 | JWT missing, malformed, or expired |
| `UPLOAD_FAILED` | 500 | S3/MinIO upload error |
| `KAFKA_PUBLISH_FAILED` | 500 | Kafka emit error |

---

## Kafka

| Direction | Topic | Event model (from `zt_shared`) |
|---|---|---|
| Produces | `file.requested` | `FileRequestedEvent` |
| Consumes | `verdict.result` | `VerdictResultEvent` |

**Publish flow:**
1. Compute `sha256` from file bytes before upload
2. Upload to S3/MinIO → get `s3_url`
3. Build `FileRequestedEvent(job_id, s3_url, sha256, email_context, timestamp)`
4. `await publisher.publish("file.requested", event)` — key = `str(job_id)`

**Consume flow:**
- One Kafka consumer per application instance, subscribed to `verdict.result`
- On receipt: look up the open WebSocket by `job_id` → push `VerdictMessageDTO` → close socket

---

## Authentication

JWTs are issued by an external SSO. The backend only **verifies** them — it never issues them.

Validation checks:
- Signature (RS256, public key fetched from SSO JWKS endpoint at startup)
- `exp` claim not in the past
- `aud` claim matches the configured API audience

The decoded JWT payload must expose at minimum:
- `sub` — user identifier
- `tenant_id` — used to apply per-tenant risk tolerance in the Verdict Layer

---

## Key Technical Rules

- The backend must return `202` and `job_id` before the analysis completes — **never await the verdict in the POST handler**
- SHA-256 is computed from the raw file bytes in-memory before the S3 upload
- `KafkaPublisher` lifecycle is tied to the FastAPI lifespan context (`startup` / `shutdown`)
- TDD with `pytest-asyncio`, 100% coverage enforced
- Ruff (line length 100, rules E/F/B/I) + MyPy strict
