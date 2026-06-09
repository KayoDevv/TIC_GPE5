# ghcr-image: charon-minio-watcher:v1.0.0
# minio-watcher image — S3 events → FileRequestedEvent transformer.
# Lightweight, no K8s API access, hardened.
#
# Build: docker build -t ghcr.io/kayodevv/charon-minio-watcher:latest \
#                     -f apps/workers/minio_watcher/Dockerfile .
# (run from the root of the GPE-ETNA monorepo)

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir \
    aiokafka==0.10.0 \
    minio==7.2.5

COPY apps/workers/minio_watcher/watcher.py ./watcher.py

# UID matching the Deployment's runAsUser (10002).
RUN useradd -u 10002 -m -s /bin/false watcher
USER 10002

CMD ["python", "-u", "watcher.py"]
