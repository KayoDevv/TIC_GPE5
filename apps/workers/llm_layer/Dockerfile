# ghcr-image: charon-llm-layer:v1.0.1
# LLM Layer image — "The Semantic Analyst".
# Consumes sandbox_layer.result, produces llm_layer.result (binary verdict + text).
# Build context = monorepo root: make build-<service>

FROM python:3.14-slim

# A version bump busts this layer so apt runs against a fresh index.
ARG IMAGE_VERSION=dev

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/workers/llm_layer/src

RUN echo "base packages for ${IMAGE_VERSION}" \
    && apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Shared contracts/Kafka helpers (pulls pydantic[email] + aiokafka), then the
# LLM Layer's own runtime deps. No dev/test tooling in the runtime image.
COPY packages/core /app/packages/core
RUN pip install --no-cache-dir ./packages/core \
    && pip install --no-cache-dir "httpx>=0.28,<0.29"

COPY apps/workers/llm_layer/src /app/apps/workers/llm_layer/src

# Non-root UID (distinct from sandbox=10001), matching the K8s runAsUser.
RUN useradd -u 10003 -m -s /bin/false llm
USER 10003

CMD ["python", "-m", "llm_layer"]
