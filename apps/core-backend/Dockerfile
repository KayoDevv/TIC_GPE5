# ghcr-image: charon-core-backend:v1.0.4
# Core Backend — FastAPI API gateway. Validates uploads, stores to S3/MinIO,
# produces file.requested, consumes verdict.result, streams verdicts over WS.

# ── Builder: hash-pinned deps into an isolated venv # ──
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv

# Exact versions + hashes from poetry.lock (main group, incl. the uvicorn[standard]
# extras). Regenerate with scripts/ci/gen_requirements.py when the lock changes.
COPY apps/core-backend/requirements.txt ./requirements.txt
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
    PYTHONPATH=/app/apps/core-backend/src

# A version bump busts this layer so apt patches the base OS on each release.
RUN echo "base packages for ${IMAGE_VERSION}" \
    && apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY apps/core-backend/src /app/apps/core-backend/src

# Non-root UID (distinct from sandbox=10001, llm=10003).
RUN useradd -u 10004 -m -s /bin/false backend
USER 10004

EXPOSE 8000
CMD ["uvicorn", "backend.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
