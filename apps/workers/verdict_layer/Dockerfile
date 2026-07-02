# ghcr-image: charon-verdict-layer:latest
# Verdict Layer — "The Judge". Aggregates ml_layer.result + sandbox_layer.result
# + llm_layer.result (Redis-backed Saga) into a single verdict.result.
#
# Build from the ROOT of the GPE-ETNA monorepo (COPY needs packages/ and apps/):
#   docker build -t ghcr.io/kayodevv/charon-verdict-layer:latest \
#                -f apps/workers/verdict_layer/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/workers/verdict_layer/src

# Shared contracts/Kafka helpers (pulls pydantic + aiokafka), then the Verdict
# Layer's own runtime deps (redis client for the Saga state store).
COPY packages/core /app/packages/core
RUN pip install --no-cache-dir ./packages/core \
    && pip install --no-cache-dir \
        "redis>=5.2,<6" \
        "pydantic-settings>=2.6,<3"

COPY apps/workers/verdict_layer/src /app/apps/workers/verdict_layer/src

# Non-root UID (distinct from sandbox=10001, minio-watcher=10002, llm=10003,
# core-backend=10004, ml=10005).
RUN useradd -u 10006 -m -s /bin/false verdict
USER 10006

CMD ["python", "-m", "verdict_layer.main"]
