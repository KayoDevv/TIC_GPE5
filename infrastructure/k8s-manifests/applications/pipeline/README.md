# pipeline — core analysis workers

The pipeline that turns a `file.requested` into a `verdict.result` and back to the
extension. Everything here is lightweight (fits well within GPE-NYX's headroom).

| Component | Role | Image |
|---|---|---|
| `core-backend` | FastAPI gateway: upload→S3, emit `file.requested`, consume `verdict.result`, WS out. NodePort **30080**. | `ghcr.io/kayodevv/charon-core-backend` |
| `ml-layer` | static PDF features + ONNX inference → `ml_layer.result` | `ghcr.io/kayodevv/charon-ml-layer` |
| `verdict-layer` | Saga aggregator (Redis) → `verdict.result` | `ghcr.io/kayodevv/charon-verdict-layer` |
| `llm-layer` | semantic analyst, **dev profile → HF router** (no GPU here) | `ghcr.io/kayodevv/charon-llm-layer` |
| `redis` | verdict Saga state store (ephemeral) | `redis:7.4-alpine` |

**Not here:** the LLM's `vLLM + Llama-3.3-70B` (needs a GPU) — dev/HF profile is used
instead; and the extension itself (a browser artifact, never server-deployed — it is
handed out as a ZIP by `applications/website`, which does run in this namespace).

## Prerequisites (owned elsewhere / one-time)
- Namespace `pipeline` + the `kafka-allow` ingress rule for it → **Terraform**
  (`infrastructure/terraform/{namespaces,networkpolicy}.tf`).
- `llm-secrets` (HF_TOKEN) — created out-of-band, never committed:
  ```bash
  kubectl -n pipeline create secret generic llm-secrets --from-literal=HF_TOKEN=hf_xxx
  ```
- `ghcr-pull` imagePullSecret — the `ghcr.io/kayodevv/charon-*` packages are
  **private**, so the node needs a read-only credential to pull them. Create once
  with a GitHub PAT (classic) scoped `read:packages`:
  ```bash
  kubectl -n pipeline create secret docker-registry ghcr-pull \
    --docker-server=ghcr.io --docker-username=<gh-user> --docker-password=<PAT>
  ```
  (Alternative: make the packages public in GHCR → the secret becomes a no-op.)

## Deploy
```bash
kubectl apply -k infrastructure/k8s-manifests/applications/pipeline
```
Images are built + pushed to GHCR by `.github/workflows/cd-deploy.yml` on merge to
main (Dockerfiles now exist for all four workers).
