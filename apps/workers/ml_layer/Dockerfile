# ghcr-image: charon-ml-layer:v1.1.1
# ML Layer — "The Static Analyst". Consumes file.requested, extracts 30 static
# PDF features (pikepdf) and scores them with a LightGBM->ONNX model, producing
# ml_layer.result. SLA < 500 ms.

# ── Builder: hash-pinned deps into an isolated venv # ──
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv

# Exact versions + hashes from poetry.lock (main group). numpy is locked to the
# 1.26 line because NumPy 2.x manylinux wheels use an x86-64-v2 baseline and crash
# at import on the GPE-NYX VM (x86-64-v1 CPU); the pyproject caps numpy<2 so the
# lock and this image agree. Regenerate with scripts/ci/gen_requirements.py.
COPY apps/workers/ml_layer/requirements.txt ./requirements.txt
RUN pip install --require-hashes -r requirements.txt

# zt-shared is local source (unhashable); its deps are already pinned above.
COPY packages/core /app/packages/core
RUN pip install --no-deps ./packages/core

RUN find /opt/venv -depth -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; \
    find /opt/venv -type f -name '*.py[co]' -delete 2>/dev/null || true; \
    rm -rf /root/.cache

# ── Final # ──
FROM python:3.12-slim

ARG IMAGE_VERSION=dev

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/apps/workers/ml_layer/src \
    MODEL_PATH=/app/apps/workers/ml_layer/models/ml_model_pdf.onnx

# A version bump busts this layer so apt patches the base OS on each release.
RUN echo "base packages for ${IMAGE_VERSION}" \
    && apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY apps/workers/ml_layer/src /app/apps/workers/ml_layer/src
# The trained model ships inside the image (read at startup; MODEL_PATH above),
# with its sidecar: without it the tuned threshold is lost and scores are raw.
COPY apps/workers/ml_layer/models/ml_model_pdf.onnx \
     apps/workers/ml_layer/models/ml_model_pdf.metadata.json \
     /app/apps/workers/ml_layer/models/

# Non-root UID (distinct from sandbox=10001, llm=10003, core-backend=10004).
RUN useradd -u 10005 -m -s /bin/false ml
USER 10005

CMD ["python", "-m", "ml_layer.worker"]
