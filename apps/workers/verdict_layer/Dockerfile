# ghcr-image: charon-verdict-layer:v1.0.3

# ── Builder: hash-pinned deps into an isolated venv # ──
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv

COPY apps/workers/verdict_layer/requirements.txt ./requirements.txt
RUN pip install --require-hashes -r requirements.txt

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
    PYTHONPATH=/app/apps/workers/verdict_layer/src

RUN echo "base packages for ${IMAGE_VERSION}" \
    && apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY apps/workers/verdict_layer/src /app/apps/workers/verdict_layer/src

RUN useradd -u 10006 -m -s /bin/false verdict
USER 10006

CMD ["python", "-m", "verdict_layer.main"]
