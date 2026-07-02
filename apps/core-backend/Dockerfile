# ghcr-image: charon-core-backend:latest
# Core Backend — FastAPI API gateway. Validates uploads, stores to S3/MinIO,
# produces file.requested, consumes verdict.result, streams verdicts over WS.
#
# Build from the ROOT of the GPE-ETNA monorepo (COPY needs packages/ and apps/):
#   docker build -t ghcr.io/kayodevv/charon-core-backend:latest \
#                -f apps/core-backend/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/core-backend/src

# Shared contracts/Kafka helpers (pulls pydantic + aiokafka), then the backend's
# own runtime deps. No dev/test tooling in the runtime image.
COPY packages/core /app/packages/core
RUN pip install --no-cache-dir ./packages/core \
    && pip install --no-cache-dir \
        "fastapi>=0.115,<0.116" \
        "uvicorn[standard]>=0.32,<0.33" \
        "boto3>=1.35,<2" \
        "python-jose[cryptography]>=3.3,<4" \
        "pydantic-settings>=2.6,<3" \
        "python-multipart>=0.0.12,<0.1" \
        "httpx>=0.27,<0.28"

COPY apps/core-backend/src /app/apps/core-backend/src

# Non-root UID (distinct from sandbox=10001, llm=10003).
RUN useradd -u 10004 -m -s /bin/false backend
USER 10004

EXPOSE 8000
CMD ["uvicorn", "backend.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
