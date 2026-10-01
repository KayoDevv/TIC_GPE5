# ghcr-image: charon-ml-layer:v1.1.0
# ML Layer — "The Static Analyst". Consumes file.requested, extracts 30 static
# PDF features (pikepdf) and scores them with a LightGBM->ONNX model, producing
# ml_layer.result. SLA < 500 ms.
# Build context = monorepo root: make build-<service>

FROM python:3.12-slim

# A version bump busts this layer so apt runs against a fresh index.
ARG IMAGE_VERSION=dev

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/workers/ml_layer/src \
    MODEL_PATH=/app/apps/workers/ml_layer/models/ml_model_pdf.onnx

RUN echo "base packages for ${IMAGE_VERSION}" \
    && apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Shared contracts/Kafka helpers, then the ML Layer's own runtime deps. pikepdf
# wheels bundle libqpdf, so no system qpdf is needed.
#
# numpy is pinned to the 1.26 line: NumPy 2.x manylinux wheels are built with an
# x86-64-v2 baseline (SSE4.2/POPCNT) and crash at import on the GPE-NYX VM, whose
# CPU is x86-64-v1 (same limitation MinIO documents; Phase 9: host-passthrough
# CPU). 1.26 wheels use the generic x86-64 baseline and run everywhere. The
# feature vector uses only basic ops (frombuffer/bincount/log2/sum) — identical
# behaviour on 1.26 vs 2.x.
COPY packages/core /app/packages/core
RUN pip install --no-cache-dir ./packages/core \
    && pip install --no-cache-dir \
        "pikepdf>=10.8,<11" \
        "onnxruntime>=1.20,<2" \
        "numpy>=1.26,<2" \
        "boto3>=1.35,<2" \
        "httpx>=0.27,<0.28" \
        "pydantic-settings>=2.5,<3"

COPY apps/workers/ml_layer/src /app/apps/workers/ml_layer/src
# The trained model ships inside the image (read at startup; MODEL_PATH above),
# with its sidecar: without it the tuned threshold is lost and scores are raw.
COPY apps/workers/ml_layer/models/ml_model_pdf.onnx \
     apps/workers/ml_layer/models/ml_model_pdf.metadata.json \
     /app/apps/workers/ml_layer/models/

# Non-root UID (distinct from sandbox=10001, llm=10003,
# core-backend=10004).
RUN useradd -u 10005 -m -s /bin/false ml
USER 10005

CMD ["python", "-m", "ml_layer.worker"]
