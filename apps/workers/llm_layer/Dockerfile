# ghcr-image: charon-llm-layer:v1.0.0
# LLM Layer image — "The Semantic Analyst".
# Consumes sandbox_layer.result, produces llm_layer.result (binary verdict + text).
#
# Build from the ROOT of the GPE-ETNA monorepo (COPY needs packages/ and apps/):
#   docker build -t ghcr.io/kayodevv/charon-llm-layer:latest \
#                -f apps/workers/llm_layer/Dockerfile .

FROM python:3.14-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/workers/llm_layer/src

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
