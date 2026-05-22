.PHONY: help setup-kubeconfig setup-keda setup-kafka setup-minio-operator \
        bootstrap-k3s bootstrap-in-cluster deploy-kafka deploy-minio \
        up down install install-dev test sandbox-validate lint format \
        build-sandbox build-pdf-sandbox build-consumer build-watcher import-images \
        deploy-dev undeploy migrate-minio-data

# IP du node K3s (première IP non-loopback). Utilisée pour exposer Bitnami Kafka
# via NodePort au validator/feeder qui tournent sur le host.
NODE_IP := $(shell hostname -I 2>/dev/null | awk '{print $$1}')

DEV_OVERLAY := infrastructure/k8s-manifests/overlays/dev

# Versions épinglées (modifier ici uniquement)
KAFKA_CHART_VERSION   := 31.0.0       # bitnami/kafka — Kafka 3.7.1, KRaft natif
MINIO_OPERATOR_REF    := v5.0.15
KAFKA_NODEPORT        := 32092

help:
	@echo "Commandes disponibles :"
	@echo ""
	@echo "  Bootstrap K3s (à faire une fois sur une fresh install)"
	@echo "  make setup-kubeconfig    - Copie /etc/rancher/k3s/k3s.yaml -> ~/.kube/config"
	@echo "  make setup-keda          - Installe KEDA via Helm (autoscaling consumer)"
	@echo "  make setup-minio-operator- Installe MinIO Operator"
	@echo "  make bootstrap-k3s       - Tout en un (kubeconfig + KEDA + MinIO Operator)"
	@echo ""
	@echo "  Déploiement infra in-cluster (Kafka + MinIO)"
	@echo "  make setup-kafka         - Déploie Kafka (Bitnami chart, KRaft 1-node) + topics"
	@echo "  make deploy-minio        - Déploie MinIO Tenant + bucket sandbox-reports"
	@echo "  make bootstrap-in-cluster- setup-kafka + deploy-minio (séquentiel)"
	@echo ""
	@echo "  Infra dev locale (cache uniquement — Kafka/MinIO sont in-cluster)"
	@echo "  make up                  - Démarre Redis (docker compose, hors scope sandbox)"
	@echo "  make down                - Arrête l'infra docker compose locale"
	@echo ""
	@echo "  Dépendances Python"
	@echo "  make install             - Runtime (aiokafka, minio, kubernetes, ...)"
	@echo "  make install-dev         - Runtime + dev/test (pytest, ruff)"
	@echo ""
	@echo "  Images K3s (sandbox/consumer/watcher)"
	@echo "  make build-sandbox       - ubuntu-sandbox:v1 (ELF)"
	@echo "  make build-pdf-sandbox   - ubuntu-pdf-sandbox:v1 (PDF, multi-layer mutool+PDF.js)"
	@echo "  make build-consumer      - charon-sandbox-consumer:latest"
	@echo "  make build-watcher       - charon-minio-watcher:latest"
	@echo "  make import-images       - Build + import les 4 images dans containerd K3s"
	@echo ""
	@echo "  Déploiement workers"
	@echo "  make deploy-dev          - Applique overlay dev (in-cluster)"
	@echo "  make undeploy            - Supprime le déploiement dev"
	@echo ""
	@echo "  Migration data"
	@echo "  make migrate-minio-data  - Copie sandbox-reports docker → MinIO in-cluster (mc mirror)"
	@echo ""
	@echo "  Validation à grande échelle"
	@echo "  make sandbox-validate TARGET=dir DIR=<corpus> RUN_ID=<id> REPS=N MAX_INFLIGHT=N"
	@echo ""
	@echo "  Qualité"
	@echo "  make lint                - ruff check"
	@echo "  make format              - ruff format"
	@echo ""
	@echo "  Variables auto-détectées : NODE_IP=$(NODE_IP)  KAFKA_NODEPORT=$(KAFKA_NODEPORT)"

# ---------------------------------------------------------------------------
# Bootstrap K3s
# ---------------------------------------------------------------------------

# Fix erreur x509 "unknown authority" sur fresh K3s. Idempotent.
setup-kubeconfig:
	@if [ ! -f /etc/rancher/k3s/k3s.yaml ]; then \
		echo "ERREUR: /etc/rancher/k3s/k3s.yaml introuvable. K3s est-il installé ?"; \
		exit 1; \
	fi
	@mkdir -p $(HOME)/.kube
	@if ! sudo cmp -s /etc/rancher/k3s/k3s.yaml $(HOME)/.kube/config 2>/dev/null; then \
		sudo cp /etc/rancher/k3s/k3s.yaml $(HOME)/.kube/config; \
		sudo chown $(shell id -u):$(shell id -g) $(HOME)/.kube/config; \
		chmod 600 $(HOME)/.kube/config; \
		echo "kubeconfig mis à jour."; \
	else \
		echo "kubeconfig déjà à jour."; \
	fi
	@kubectl get nodes >/dev/null 2>&1 && echo "kubectl OK." \
		|| (echo "ATTENTION: kubectl ne joint pas le cluster."; exit 1)

# KEDA — autoscaling du consumer sur le lag Kafka. Idempotent.
setup-keda:
	@command -v helm >/dev/null 2>&1 || { echo "ERREUR: helm non installé."; exit 1; }
	@if kubectl get ns keda >/dev/null 2>&1 && kubectl get deploy -n keda keda-operator >/dev/null 2>&1; then \
		echo "KEDA déjà installé."; \
	else \
		helm repo add kedacore https://kedacore.github.io/charts 2>/dev/null || true; \
		helm repo update kedacore; \
		helm upgrade --install keda kedacore/keda --namespace keda --create-namespace --wait --timeout 5m; \
	fi

# MinIO Operator — Tenants MinIO in-cluster. Idempotent.
setup-minio-operator:
	@kubectl get crd tenants.minio.min.io >/dev/null 2>&1 \
		&& echo "MinIO Operator déjà installé." \
		|| { \
			echo "Installation MinIO Operator $(MINIO_OPERATOR_REF)..."; \
			kubectl apply -k "github.com/minio/operator/?ref=$(MINIO_OPERATOR_REF)"; \
			kubectl wait deploy/minio-operator -n minio-operator --for=condition=Available --timeout=300s; \
		}

bootstrap-k3s: setup-kubeconfig setup-keda setup-minio-operator
	@echo ""
	@echo "Bootstrap K3s terminé. Étapes suivantes :"
	@echo "  make bootstrap-in-cluster  # Déploie Kafka (Bitnami) + MinIO Tenant in-cluster"
	@echo "  make import-images         # Build les images sandbox"
	@echo "  make deploy-dev            # Déploie les workers"

# ---------------------------------------------------------------------------
# Infra in-cluster (Kafka + MinIO)
# ---------------------------------------------------------------------------

# Kafka : Bitnami Helm chart (KRaft 1-node combined mode).
# Provisioning des 6 topics inclus dans le chart.
setup-kafka:
	@command -v helm >/dev/null 2>&1 || { echo "ERREUR: helm non installé."; exit 1; }
	kubectl apply -f infrastructure/k8s-manifests/applications/kafka/namespace.yaml
	@helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
	@helm repo update bitnami
	helm upgrade --install kafka bitnami/kafka \
		--namespace kafka --version $(KAFKA_CHART_VERSION) \
		-f infrastructure/k8s-manifests/applications/kafka/values.yaml \
		--wait --timeout 10m
	# Namespace + annexes (kustomize) — Schema Registry retiré (non utilisé en v1)
	kubectl apply -k infrastructure/k8s-manifests/applications/kafka/
	@echo "Kafka in-cluster prêt. Service : kafka.kafka.svc.cluster.local:9092"
	@echo "NodePort externe (validator host) : $(NODE_IP):$(KAFKA_NODEPORT)"

# Alias rétro-compatible (anciens scripts/docs peuvent appeler deploy-kafka)
deploy-kafka: setup-kafka

# MinIO standalone StatefulSet — plus de MinIO Operator (pivot 2026-05-13).
# Raison : CPU VM GPE-NYX = x86-64-v1, oblige MinIO 2023-01 (dernière build v1),
# que l'Operator v5 ne supporte plus. StatefulSet standard plus simple.
deploy-minio:
	kubectl apply -k infrastructure/k8s-manifests/applications/minio/
	@echo "Attente MinIO Ready..."
	kubectl rollout status statefulset/minio -n minio --timeout=300s
	@echo "MinIO in-cluster prêt. Service interne : minio.minio.svc.cluster.local:9000"

bootstrap-in-cluster: setup-kafka deploy-minio
	@echo "Kafka (Bitnami) + MinIO (standalone StatefulSet) déployés in-cluster. NetworkPolicies peuvent maintenant utiliser namespaceSelector."

# Migre les données depuis l'ancien MinIO (docker compose host) vers le nouveau
# Tenant in-cluster via mc mirror. Lit la NodePort MinIO depuis le service.
migrate-minio-data:
	@MINIO_NODEPORT=$$(kubectl get svc minio -n minio -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null); \
	if [ -z "$$MINIO_NODEPORT" ]; then \
		echo "Service MinIO sans NodePort — création temporaire pour migration..."; \
		kubectl patch svc minio -n minio -p '{"spec":{"type":"NodePort"}}'; \
		MINIO_NODEPORT=$$(kubectl get svc minio -n minio -o jsonpath='{.spec.ports[0].nodePort}'); \
	fi; \
	echo "Migration depuis 172.16.249.133:9000 (docker compose) vers $(NODE_IP):$$MINIO_NODEPORT (in-cluster)..."; \
	docker run --rm --network host quay.io/minio/mc:RELEASE.2024-09-09T17-00-14Z sh -c "\
		mc alias set old http://172.16.249.133:9000 minioadmin minioadmin && \
		mc alias set new http://$(NODE_IP):$$MINIO_NODEPORT minioadmin minioadmin && \
		mc mb -p new/sandbox-reports || true && \
		mc mirror --overwrite old/sandbox-reports new/sandbox-reports && \
		echo 'Migration terminée.'"

# ---------------------------------------------------------------------------
# Infra dev locale (cache uniquement — Kafka/MinIO sont in-cluster désormais)
# ---------------------------------------------------------------------------

up:
	docker compose up -d redis
	@echo "Redis démarré. Kafka et MinIO sont in-cluster — voir make deploy-kafka / deploy-minio."

down:
	docker compose down

# ---------------------------------------------------------------------------
# Dépendances Python
# ---------------------------------------------------------------------------

install:
	pip install --break-system-packages \
		aiokafka==0.10.0 \
		kafka-python \
		minio \
		kubernetes==29.0.0 \
		pydantic==2.7.1 \
		structlog==24.1.0 \
		duckdb

install-dev: install
	pip install --break-system-packages \
		pytest \
		pytest-asyncio \
		pytest-cov \
		ruff

# ---------------------------------------------------------------------------
# Images K3s
# ---------------------------------------------------------------------------

build-consumer:
	docker build -t ghcr.io/kayodevv/charon-sandbox-consumer:latest \
	             -f apps/workers/sandbox_layer/Dockerfile.consumer .

build-sandbox:
	docker build -t ghcr.io/kayodevv/ubuntu-sandbox:v1 \
	             -f apps/workers/sandbox_layer/Dockerfile.agent .

build-pdf-sandbox:
	docker build -t ghcr.io/kayodevv/ubuntu-pdf-sandbox:v1 \
	             -f apps/workers/sandbox_layer/Dockerfile.pdf-agent .

build-watcher:
	docker build -t ghcr.io/kayodevv/charon-minio-watcher:latest \
	             -f apps/workers/minio_watcher/Dockerfile .

import-images: build-consumer build-sandbox build-pdf-sandbox build-watcher
	docker save ghcr.io/kayodevv/charon-sandbox-consumer:latest | sudo k3s ctr images import -
	docker save ghcr.io/kayodevv/ubuntu-sandbox:v1              | sudo k3s ctr images import -
	docker save ghcr.io/kayodevv/ubuntu-pdf-sandbox:v1          | sudo k3s ctr images import -
	docker save ghcr.io/kayodevv/charon-minio-watcher:latest    | sudo k3s ctr images import -
	@echo "Images importées dans K3s."

# ---------------------------------------------------------------------------
# Déploiement workers
# ---------------------------------------------------------------------------

deploy-dev: setup-kubeconfig setup-keda import-images
	kubectl apply -k $(DEV_OVERLAY)/
	@echo "Stack sandbox déployée (overlay dev, in-cluster)."

undeploy:
	kubectl delete -k $(DEV_OVERLAY)/ --ignore-not-found

# ---------------------------------------------------------------------------
# Tests / dev hors K8s — port-forward vers Kafka/MinIO in-cluster
# ---------------------------------------------------------------------------

test:
	pytest apps/ -v --cov=apps --cov-report=term-missing

# Pour run-watcher/run-consumer en local, port-forward Kafka et MinIO depuis K3s :
#   kubectl port-forward -n kafka svc/kafka-kafka-bootstrap 9092:9092 &
#   kubectl port-forward -n minio svc/minio 9000:9000 &
run-watcher:
	@echo "Prérequis : port-forward Kafka (9092) et MinIO (9000) depuis K3s."
	KAFKA_BOOTSTRAP=localhost:9092 \
	MINIO_ENDPOINT=localhost:9000 \
	MINIO_PRESIGN_ENDPOINT=localhost:9000 \
	MINIO_ACCESS_KEY=minioadmin \
	MINIO_SECRET_KEY=minioadmin \
	MINIO_BUCKET=sandbox-reports \
	python3 apps/workers/minio_watcher/watcher.py

run-consumer:
	@echo "Prérequis : port-forward Kafka (9092) depuis K3s."
	KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
	KAFKA_TOPIC_IN=file.requested \
	KAFKA_TOPIC_OUT=sandbox_layer.result \
	KAFKA_GROUP_ID=charon-sandbox-v1 \
	MINIO_ENDPOINT=localhost:9000 \
	AGENT_KAFKA_BOOTSTRAP_SERVERS=kafka-kafka-bootstrap.kafka.svc.cluster.local:9092 \
	AGENT_MINIO_ENDPOINT=minio.minio.svc.cluster.local:9000 \
	K8S_NAMESPACE=sandbox \
	SANDBOX_JOB_IMAGE=ghcr.io/kayodevv/ubuntu-sandbox:v1 \
	SANDBOX_TIMEOUT_S=180 \
	python3 apps/workers/sandbox_layer/consumer.py

# ---------------------------------------------------------------------------
# Validation sandbox — point d'entrée unique
# Usage : make sandbox-validate CORPUS=<dir> RUN_ID=<id> [REPS=2 MAX_INFLIGHT=7]
#
# Le corpus doit contenir des sous-dossiers benign/, malicious/, unknown/.
# Le validator joint Kafka via NodePort 32092 et MinIO via NodePort dynamique
# (les Jobs in-cluster utilisent le DNS K8s minio.minio.svc.cluster.local:9000).
sandbox-validate:
	KAFKA_BOOTSTRAP=$(NODE_IP):$(KAFKA_NODEPORT) \
	$(MAKE) -f scripts/validation/Makefile run \
		RUN_ID=$(RUN_ID) CORPUS=$(CORPUS) \
		REPS=$(REPS) MAX_INFLIGHT=$(MAX_INFLIGHT)

# ---------------------------------------------------------------------------
# Qualité
# ---------------------------------------------------------------------------

lint:
	ruff check apps/ scripts/

format:
	ruff format apps/ scripts/
