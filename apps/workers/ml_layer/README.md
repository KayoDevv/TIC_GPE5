# ML Layer — Static ML (The Fast Filter)

**Role:** First line of defense. Performs static analysis on every file without executing it, producing a risk score in under 500ms. Fast-tracks obviously clean files and instantly blocks known threats.

**Stack:** Python · LightGBM or Random Forest → exported to **ONNX Runtime** · `aiokafka` · `pefile`

---

## Kafka

| Direction | Topic | Model |
|---|---|---|
| Consumes | `file.requested` | `FileRequestedEvent` |
| Produces | `ml_layer.result` | `MlLayerResultEvent` |

**Output fields:** `risk_score` (int 0–100) · `static_tags` (e.g. `packer_detected`, `high_entropy`, `known_malware`) · `processing_time_ms`

> `risk_score > 90` triggers an immediate `blocked` verdict in the Verdict Layer — the remaining workers still run for audit logs.

---

## Processing Pipeline

```
file.requested
    │
    ▼
Async S3/MinIO download
    │
    ▼
Static feature extraction
    ├── Global Shannon entropy
    ├── PE sections (entropy per section, count)
    ├── Import table (suspicious DLLs: ws2_32, crypt32, wininet)
    ├── Plaintext string extraction (URLs, IPs, registry keys)
    └── File size, compile timestamp
    │
    ▼
ONNX Runtime inference  ──► asyncio.to_thread() (never blocks the event loop)
    │
    ▼
ml_layer.result  (risk_score + static_tags)
```

**SLA:** < **500 ms** from feature extraction to Kafka publish (S3 download time excluded).

---

## Feature Engineering

| Feature | How | Why |
|---|---|---|
| `entropy` | Shannon entropy on all bytes | Packed/encrypted payloads have entropy > 7.0 |
| `max_section_entropy` | Per PE section | High-entropy `.text` section = packer |
| `num_sections` | PE header | Unusual section count is suspicious |
| `has_network_imports` | `ws2_32.dll`, `wininet.dll` in import table | Network capability indicator |
| `has_crypto_imports` | `crypt32.dll` in import table | Encryption capability |
| `num_imported_dlls` | Import directory | Very few or very many DLLs are anomalous |
| `has_url` / `has_ip` | Regex on extracted strings | C2 infrastructure artifacts |
| `file_size` | Raw | Unusually small PE = hollow/dropper |

Non-PE files (PDFs, Office docs, archives) get 0 for all PE-specific features.

---

## Model Training

### Datasets

| Dataset | Size | Notes |
|---|---|---|
| [EMBER](https://github.com/elastic/ember) | 1M PE files | Pre-extracted features, fastest start |
| [SOREL-20M](https://github.com/sophos/SOREL-20M) | 20M PE files | Sophos + ReversingLabs labels |
| [MalwareBazaar](https://bazaar.abuse.ch) | Live samples | Tagged by family, free |
| Clean Windows install | — | Benign baseline (system32, Program Files) |

Labeling convention: VirusTotal consensus >= 5 detections = malicious (`1`), else benign (`0`).

### Training

```bash
pip install lightgbm scikit-learn pandas numpy pefile onnxmltools skl2onnx
```

```python
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_curve

X, y = load_feature_dataset()
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y)

model = lgb.LGBMClassifier(
    n_estimators=500,
    learning_rate=0.05,
    num_leaves=63,
    class_weight="balanced",  # malware samples are rare vs benign
)
model.fit(X_train, y_train)

# Tune threshold to enforce FPR < 0.5%
proba = model.predict_proba(X_test)[:, 1]
fpr, tpr, thresholds = roc_curve(y_test, proba)
threshold = thresholds[fpr <= 0.005][-1]
```

### Export to ONNX

```python
from onnxmltools.convert import convert_lightgbm
from skl2onnx.common.data_types import FloatTensorType

initial_type = [("float_input", FloatTensorType([None, X_train.shape[1]]))]
onnx_model = convert_lightgbm(model, initial_types=initial_type)

with open("ml_model.onnx", "wb") as f:
    f.write(onnx_model.SerializeToString())
```

---

## Production Inference

ONNX Runtime is synchronous — wrap it in `asyncio.to_thread()` to avoid blocking the event loop:

```python
import onnxruntime as ort
import asyncio
import numpy as np

class StaticAnalyzer:
    def __init__(self, model_path: str):
        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name

    async def predict(self, features: dict) -> tuple[int, list[str]]:
        X = np.array([[features[k] for k in FEATURE_ORDER]], dtype=np.float32)
        result = await asyncio.to_thread(
            self.session.run, None, {self.input_name: X}
        )
        proba = result[1][0][1]
        risk_score = int(proba * 100)

        tags = []
        if features["entropy"] > 7.0:
            tags.append("high_entropy")
        if features.get("has_network_imports"):
            tags.append("network_activity")
        if risk_score > 90:
            tags.append("known_malware")

        return risk_score, tags
```

---

## Code Standards

- TDD with `pytest-asyncio` — 100% coverage enforced
- Ruff (line length 100, rules E/F/B/I) + MyPy strict
- All Kafka I/O and S3 downloads must be `async` — no blocking calls in the hot path
- Use a dedicated Kafka Consumer Group for this worker
- Expose Prometheus metrics for Consumer Lag (used by Kubernetes HPA to scale sandbox pods)
