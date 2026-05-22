# Image du minio-watcher — transformateur S3 events → FileRequestedEvent.
# Léger, sans accès API K8s, hardenisé.
#
# Build : docker build -t ghcr.io/kayodevv/charon-minio-watcher:latest \
#                      -f apps/workers/minio_watcher/Dockerfile .
# (à lancer depuis la racine du monorepo GPE-ETNA)

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir \
    aiokafka==0.10.0 \
    minio==7.2.5

COPY apps/workers/minio_watcher/watcher.py ./watcher.py

# UID matching le runAsUser du Deployment (10002).
RUN useradd -u 10002 -m -s /bin/false watcher
USER 10002

CMD ["python", "-u", "watcher.py"]
