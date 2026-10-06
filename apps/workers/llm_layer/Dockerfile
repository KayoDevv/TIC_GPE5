# ghcr-image: charon-llm-layer:v1.0.3
# LLM Layer — "The Semantic Analyst".
# Consumes sandbox_layer.result, produces llm_layer.result (binary verdict + text).

# ── Builder: hash-pinned deps into an isolated venv # ──
FROM python:3.14-slim AS builder

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv

# Exact versions + hashes from poetry.lock (main group).
# Regenerate with scripts/ci/gen_requirements.py when the lock changes.
COPY apps/workers/llm_layer/requirements.txt ./requirements.txt
RUN pip install --require-hashes -r requirements.txt

# zt-shared is local source (unhashable); its deps are already pinned above.
COPY packages/core /app/packages/core
RUN pip install --no-deps ./packages/core

RUN find /opt/venv -depth -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; \
    find /opt/venv -type f -name '*.py[co]' -delete 2>/dev/null || true; \
    rm -rf /root/.cache

# ── Final # ──
FROM python:3.14-slim

ARG IMAGE_VERSION=dev

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/apps/workers/llm_layer/src

# A version bump busts this layer so apt patches the base OS on each release.
RUN echo "base packages for ${IMAGE_VERSION}" \
    && apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY apps/workers/llm_layer/src /app/apps/workers/llm_layer/src

# Non-root UID (distinct from sandbox=10001), matching the K8s runAsUser.
RUN useradd -u 10003 -m -s /bin/false llm
USER 10003

CMD ["python", "-m", "llm_layer"]
