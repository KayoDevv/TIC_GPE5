.PHONY: help \
        configuration deploy launch fix-dns-fai \
        _apt-deps install-k3s install-kubectl install-helm install-docker install-k9s \
        setup-kubeconfig setup-calico setup-keda setup-minio-operator \
        bootstrap-k3s bootstrap-in-cluster deploy-kafka setup-kafka deploy-minio \
        up down install install-dev test sandbox-validate lint format \
        build-sandbox build-pdf-sandbox build-consumer build-watcher import-images \
        deploy-dev undeploy netpol-apiserver install-gvisor enforce-gvisor migrate-minio-data run-watcher run-consumer \
        clean clean-all

# IP du node K3s (première IP non-loopback). Utilisée pour exposer Bitnami Kafka
# via NodePort au validator/feeder qui tournent sur le host.
NODE_IP := $(shell hostname -I 2>/dev/null | awk '{print $$1}')

# Utilisateur courant (pour usermod groupe docker). Fallback sur `whoami`.
HOST_USER := $(shell echo $${USER:-$$(whoami)})

DEV_OVERLAY := infrastructure/k8s-manifests/overlays/dev

# Versions épinglées (modifier ici uniquement)
KAFKA_CHART_VERSION   := 31.0.0       # bitnami/kafka — Kafka 3.7.1, KRaft natif
# Calico: CNI + NetworkPolicy enforcer (tigera-operator). No inline comment here:
# Make would include the spaces before the '#' in the value and break the
# manifest URL (.../calico/<version>/manifests/...).
CALICO_VERSION        := v3.27.3
MINIO_OPERATOR_REF    := v5.0.15
KAFKA_NODEPORT        := 32092
# KUBECTL_REPO_VERSION: pkgs.k8s.io apt repo (standalone kubectl). No inline
# comment (embedded in an apt URL — same stray-space problem).
KUBECTL_REPO_VERSION  := v1.30

help:
	@echo "Commandes disponibles :"
	@echo ""
	@echo "  ============================================================"
	@echo "  PARCOURS PRINCIPAL (fresh install -> stack en marche)"
	@echo "  ============================================================"
	@echo "  1. make configuration    - Installe TOUT le nécessaire (outils + deps + kubeconfig + DNS)"
	@echo "  2. make deploy           - Déploie l'infra K3s dans le bon ordre (KEDA -> Kafka -> MinIO)"
	@echo "  3. make launch           - Lance la stack (build/import images + workers)"
	@echo ""
	@echo "  Cas particulier réseau"
	@echo "  make fix-dns-fai         - Corrige le NXDOMAIN hijacking box SFR/Numericable (resolv.conf k3s)"
	@echo ""
	@echo "  ------------------------------------------------------------"
	@echo "  Cibles unitaires (appelées par les orchestrateurs ci-dessus)"
	@echo "  ------------------------------------------------------------"
	@echo "  Installation des prérequis"
	@echo "  make install-k3s         - Installe k3s single-node (curl | sh)"
	@echo "  make install-kubectl     - kubectl standalone (dépôt apt $(KUBECTL_REPO_VERSION))"
	@echo "  make install-helm        - Helm 3 (script officiel)"
	@echo "  make install-docker      - Docker CE + ajout au groupe docker (RELOG requis)"
	@echo "  make install-k9s         - K9s TUI monitoring (optionnel)"
	@echo "  make install             - Deps Python runtime (aiokafka, minio, kubernetes, ...)"
	@echo "  make install-dev         - Runtime + dev/test (pytest, ruff)"
	@echo "  make setup-kubeconfig    - Copie /etc/rancher/k3s/k3s.yaml -> ~/.kube/config"
	@echo "  make setup-calico        - Installe Calico CNI ($(CALICO_VERSION)) — CNI + enforcement NetworkPolicy"
	@echo ""
	@echo "  Infra in-cluster"
	@echo "  make setup-keda          - Installe KEDA via Helm (autoscaling consumer)"
	@echo "  make setup-kafka         - Déploie Kafka (Bitnami chart, KRaft 1-node) + topics"
	@echo "  make deploy-minio        - Déploie MinIO StatefulSet + bucket sandbox-reports"
	@echo ""
	@echo "  Images K3s (sandbox/consumer/watcher)"
	@echo "  make import-images       - Build + import les 4 images dans containerd K3s"
	@echo ""
	@echo "  Déploiement / migration / qualité"
	@echo "  make deploy-dev          - Applique overlay dev (workers in-cluster)"
	@echo "  make install-gvisor      - Installe gVisor (runsc) + RuntimeClass (prérequis détonation)"
	@echo "  make undeploy            - Supprime le déploiement dev (workers + netpol + VAP)"
	@echo "  make clean CONFIRM=yes   - Teardown in-cluster (workers+Kafka+MinIO+KEDA), GARDE k3s+Calico"
	@echo "  make clean-all CONFIRM=yes - NUKE total : désinstalle k3s + images docker -> VM nue"
	@echo "  make migrate-minio-data  - Copie sandbox-reports docker -> MinIO in-cluster"
	@echo "  make lint / make format  - ruff check / ruff format"
	@echo "  make test                - pytest avec couverture"
	@echo ""
	@echo "  Validation à grande échelle"
	@echo "  make sandbox-validate CORPUS=<dir> RUN_ID=<id> [REPS=2 MAX_INFLIGHT=7]"
	@echo ""
	@echo "  Variables auto-détectées : NODE_IP=$(NODE_IP)  KAFKA_NODEPORT=$(KAFKA_NODEPORT)  HOST_USER=$(HOST_USER)"

# ===========================================================================
# 1. CONFIGURATION — initialise tout le nécessaire (fresh install, une fois)
# ===========================================================================
# Hypothèse : seul `make` (build-essential) est requis manuellement au départ,
# car il sert à lancer cette cible. Tout le reste est automatisé ici.
# Ordre : paquets de base -> docker -> k3s -> kubectl/helm/k9s -> kubeconfig ->
#         fix DNS (restart k3s en dernier) -> deps Python.
configuration: _apt-deps install-docker install-k3s install-kubectl install-helm install-k9s setup-kubeconfig setup-calico fix-dns-fai install
	@echo ""
	@echo "=== Configuration terminée ==="
	@echo "Outils installés : k3s, kubectl, helm, docker, k9s + deps Python."
	@echo "kubeconfig en place, Calico CNI déployé (enforcement NetworkPolicy), DNS FAI corrigé."
	@echo ""
	@echo ">>> Si docker vient d'être ajouté au groupe : DÉCONNECTE/RECONNECTE-toi"
	@echo ">>> (ou lance 'newgrp docker') AVANT 'make deploy' / 'make launch'."
	@echo ""
	@echo "Étape suivante : make deploy"

# Paquets système de base. apt est idempotent (re-run inoffensif).
_apt-deps:
	sudo apt update
	sudo apt install -y build-essential python3-pip python-is-python3 \
		git curl gnupg ca-certificates net-tools

# k3s single-node. Idempotent (skip si déjà installé).
# flannel DISABLED + K3s embedded netpol disabled: Calico becomes the SOLE CNI
# (dataplane + NetworkPolicy enforcement), see `make setup-calico`. Without these
# flags K3s starts flannel and does NOT enforce NetworkPolicies via Calico → a
# security hole (the whole sandbox network hardening depends on it).
install-k3s:
	@if command -v k3s >/dev/null 2>&1; then \
		echo "k3s déjà installé ($$(k3s --version 2>/dev/null | head -1))."; \
	else \
		echo "Installation k3s single-node (flannel désactivé pour Calico)..."; \
		curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--flannel-backend=none --disable-network-policy" sh -; \
	fi

# kubectl standalone via dépôt apt officiel (évite le wrapper /usr/local/bin
# de k3s qui masque le vrai kubectl). Idempotent.
install-kubectl:
	sudo mkdir -p /etc/apt/keyrings
	@if [ ! -f /etc/apt/keyrings/kubernetes-apt-keyring.gpg ]; then \
		curl -fsSL https://pkgs.k8s.io/core:/stable:/$(KUBECTL_REPO_VERSION)/deb/Release.key | \
			sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg; \
		echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/$(KUBECTL_REPO_VERSION)/deb/ /' | \
			sudo tee /etc/apt/sources.list.d/kubernetes.list >/dev/null; \
	fi
	sudo apt update && sudo apt install -y kubectl

# Helm 3 via script officiel. Idempotent.
install-helm:
	@if command -v helm >/dev/null 2>&1; then \
		echo "helm déjà installé ($$(helm version --short 2>/dev/null))."; \
	else \
		curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash; \
	fi

# Docker CE + ajout au groupe docker. Le Makefile appelle docker sans sudo.
# ATTENTION : le groupe docker ne devient actif qu'après reconnexion.
install-docker:
	@if command -v docker >/dev/null 2>&1; then \
		echo "docker déjà installé ($$(docker --version 2>/dev/null))."; \
	else \
		sudo install -m 0755 -d /etc/apt/keyrings; \
		curl -fsSL https://download.docker.com/linux/debian/gpg | \
			sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg; \
		sudo chmod a+r /etc/apt/keyrings/docker.gpg; \
		echo "deb [arch=$$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $$(. /etc/os-release && echo $$VERSION_CODENAME) stable" | \
			sudo tee /etc/apt/sources.list.d/docker.list >/dev/null; \
		sudo apt update; \
		sudo apt install -y docker-ce docker-ce-cli containerd.io \
			docker-buildx-plugin docker-compose-plugin; \
	fi
	@sudo usermod -aG docker $(HOST_USER) 2>/dev/null || true
	@if ! id -nG "$(HOST_USER)" 2>/dev/null | grep -qw docker; then \
		echo ">>> $(HOST_USER) ajouté au groupe docker — RELOG nécessaire pour l'activer."; \
	fi

# K9s — TUI de monitoring (confort, non obligatoire). Idempotent.
install-k9s:
	@if command -v k9s >/dev/null 2>&1; then \
		echo "k9s déjà installé."; \
	else \
		curl -sL https://github.com/derailed/k9s/releases/latest/download/k9s_linux_amd64.deb -o /tmp/k9s.deb; \
		sudo apt install -y /tmp/k9s.deb && rm -f /tmp/k9s.deb; \
	fi

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
	@grep -q 'KUBECONFIG=' $(HOME)/.bashrc 2>/dev/null || \
		echo 'export KUBECONFIG=$$HOME/.kube/config' >> $(HOME)/.bashrc
	@kubectl get nodes >/dev/null 2>&1 && echo "kubectl OK." \
		|| (echo "ATTENTION: kubectl ne joint pas le cluster."; exit 1)

# Calico CNI (tigera-operator, $(CALICO_VERSION)). K3s runs with flannel disabled
# (see install-k3s) → Calico provides BOTH the dataplane AND NetworkPolicy
# enforcement (calico-system namespace). WITHOUT this target a fresh cluster has
# no CNI (nodes NotReady) and enforces no NetworkPolicy. Idempotent.
setup-calico:
	@command -v kubectl >/dev/null 2>&1 || { echo "ERREUR: kubectl non installé (make install-kubectl)."; exit 1; }
	@if kubectl get installation default >/dev/null 2>&1; then \
		echo "Calico déjà installé (Installation 'default' présente)."; \
	else \
		echo "Installation tigera-operator $(CALICO_VERSION) (server-side apply)..."; \
		kubectl apply --server-side --force-conflicts -f https://raw.githubusercontent.com/projectcalico/calico/$(strip $(CALICO_VERSION))/manifests/tigera-operator.yaml; \
		echo "Attente du tigera-operator (Available)..."; \
		kubectl rollout status deployment/tigera-operator -n tigera-operator --timeout=180s; \
		echo "Attente que la CRD Installation soit Established..."; \
		kubectl wait --for=condition=Established crd/installations.operator.tigera.io --timeout=120s; \
		kubectl apply -f infrastructure/k8s-manifests/system/calico/installation.yaml; \
	fi
	@# The operator creates calico-system + the pods ASYNCHRONOUSLY after the
	@# Installation CR. So we do NOT wait on the pods directly (they don't exist
	@# yet -> "no matching resources"). We rely on TigeraStatus/calico, the
	@# readiness signal published by the operator — but it is also created async,
	@# so we poll for its existence before waiting on its Available condition.
	@echo "Attente que l'opérateur crée TigeraStatus/calico (asynchrone)..."
	@for i in $$(seq 1 60); do \
		kubectl get tigerastatus calico >/dev/null 2>&1 && break; \
		echo "  pas encore créé, retry ($$i/60)..."; \
		sleep 5; \
	done
	@echo "Attente que Calico soit Available (rollout dataplane, 1-2 min)..."
	kubectl wait --for=condition=Available tigerastatus/calico --timeout=300s
	@echo "Calico opérationnel : CNI + enforcement NetworkPolicy (calico-system)."

# Fix DNS FAI (box SFR/Numericable) — NXDOMAIN hijacking sur *.cluster.local.
# Le resolv.conf des pods ne se réinitialise pas au restart du cluster : on
# force un resolv.conf propre déclaré dans la config k3s. Idempotent.
# cf. DEPENDENCIES.md §7.
fix-dns-fai:
	@if [ ! -d /etc/rancher/k3s ]; then \
		echo "ERREUR: /etc/rancher/k3s introuvable — installe k3s d'abord (make install-k3s)."; \
		exit 1; \
	fi
	@printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' | sudo tee /etc/k3s-resolv.conf >/dev/null
	@if ! sudo grep -q '^resolv-conf:' /etc/rancher/k3s/config.yaml 2>/dev/null; then \
		echo 'resolv-conf: /etc/k3s-resolv.conf' | sudo tee -a /etc/rancher/k3s/config.yaml >/dev/null; \
		echo "config.yaml : 'resolv-conf' ajouté."; \
	else \
		echo "config.yaml : 'resolv-conf' déjà présent."; \
	fi
	sudo systemctl restart k3s
	@echo "DNS FAI corrigé (resolv-conf -> 1.1.1.1 / 8.8.8.8). k3s redémarré."
	@echo "Vérif : kubectl run rc --rm -i --image=busybox:1.36 --restart=Never -- cat /etc/resolv.conf"

# ===========================================================================
# 2. DEPLOY — déploie l'infra K3s dans le bon ordre
# ===========================================================================
# Ordre strict (cf. DEPENDENCIES.md §8) : KEDA -> Kafka -> MinIO.
# MinIO 2023-01 panique si Kafka est injoignable : Kafka DOIT être Ready avant.
deploy: setup-kubeconfig setup-keda setup-kafka deploy-minio
	@echo ""
	@echo "=== Déploiement infra K3s terminé ==="
	@echo "Ordre respecté : KEDA -> Kafka -> MinIO (DEPENDENCIES.md §8)."
	@echo "Kafka : kafka.kafka.svc.cluster.local:9092 (NodePort $(NODE_IP):$(KAFKA_NODEPORT))"
	@echo "MinIO : minio.minio.svc.cluster.local:9000"
	@echo ""
	@echo "Étape suivante : make launch"

# KEDA — autoscaling du consumer sur le lag Kafka. Idempotent.
setup-keda:
	@command -v helm >/dev/null 2>&1 || { echo "ERREUR: helm non installé (make install-helm)."; exit 1; }
	@if kubectl get ns keda >/dev/null 2>&1 && kubectl get deploy -n keda keda-operator >/dev/null 2>&1; then \
		echo "KEDA déjà installé."; \
	else \
		helm repo add kedacore https://kedacore.github.io/charts 2>/dev/null || true; \
		helm repo update kedacore; \
		helm upgrade --install keda kedacore/keda --namespace keda --create-namespace --wait --timeout 5m; \
	fi

# Kafka : Bitnami Helm chart (KRaft 1-node combined mode). Topics inclus.
setup-kafka:
	@command -v helm >/dev/null 2>&1 || { echo "ERREUR: helm non installé (make install-helm)."; exit 1; }
	kubectl apply -f infrastructure/k8s-manifests/applications/kafka/namespace.yaml
	@helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
	@helm repo update bitnami
	helm upgrade --install kafka bitnami/kafka \
		--namespace kafka --version $(KAFKA_CHART_VERSION) \
		-f infrastructure/k8s-manifests/applications/kafka/values.yaml \
		--wait --timeout 10m
	kubectl apply -k infrastructure/k8s-manifests/applications/kafka/
	@echo "Kafka in-cluster prêt. Service : kafka.kafka.svc.cluster.local:9092"
	@echo "NodePort externe (validator host) : $(NODE_IP):$(KAFKA_NODEPORT)"

# Alias rétro-compatible (anciens scripts/docs peuvent appeler deploy-kafka).
deploy-kafka: setup-kafka

# MinIO standalone StatefulSet — plus de MinIO Operator (pivot 2026-05-13).
# Raison : CPU VM GPE-NYX = x86-64-v1, oblige MinIO 2023-01 (dernière build v1),
# que l'Operator v5 ne supporte plus. StatefulSet standard plus simple.
deploy-minio:
	kubectl apply -k infrastructure/k8s-manifests/applications/minio/
	@echo "Attente MinIO Ready..."
	kubectl rollout status statefulset/minio -n minio --timeout=300s
	@echo "MinIO in-cluster prêt. Service interne : minio.minio.svc.cluster.local:9000"

# ===========================================================================
# 3. LAUNCH — lance la stack (images + workers)
# ===========================================================================
launch: import-images deploy-dev
	@echo ""
	@echo "=== Stack sandbox lancée ==="
	@echo "Images importées dans containerd, workers déployés (overlay dev)."
	@echo "Suivi : k9s   ou   kubectl get pods -A"

# ---------------------------------------------------------------------------
# Alias rétro-compatibilité (docs apps/workers/sandbox_layer/README.md, etc.)
# ---------------------------------------------------------------------------
# bootstrap-k3s : préparation cluster (kubeconfig + KEDA). setup-minio-operator
# RETIRÉ du flow (code mort depuis le pivot StatefulSet 2026-05-13).
bootstrap-k3s: setup-kubeconfig setup-keda
	@echo ""
	@echo "Bootstrap K3s terminé (kubeconfig + KEDA). Suite : make deploy puis make launch."

# bootstrap-in-cluster : déploie Kafka + MinIO (équivalent de la 2e moitié de deploy).
bootstrap-in-cluster: setup-kafka deploy-minio
	@echo "Kafka (Bitnami) + MinIO (StatefulSet) déployés in-cluster."

# MinIO Operator — DÉPRÉCIÉ (pivot StatefulSet 2026-05-13). Conservé pour
# compatibilité docs uniquement ; n'est plus appelé par aucun orchestrateur.
setup-minio-operator:
	@echo "DÉPRÉCIÉ : MinIO tourne en StatefulSet standalone (voir make deploy-minio)."
	@kubectl get crd tenants.minio.min.io >/dev/null 2>&1 \
		&& echo "MinIO Operator déjà installé." \
		|| { \
			echo "Installation MinIO Operator $(MINIO_OPERATOR_REF)..."; \
			kubectl apply -k "github.com/minio/operator/?ref=$(MINIO_OPERATOR_REF)"; \
			kubectl wait deploy/minio-operator -n minio-operator --for=condition=Available --timeout=300s; \
		}

# Migre les données depuis l'ancien MinIO (docker compose host) vers le nouveau
# StatefulSet in-cluster via mc mirror. Lit la NodePort MinIO depuis le service.
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
	@echo "Redis démarré. Kafka et MinIO sont in-cluster — voir make deploy."

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

deploy-dev: setup-kubeconfig setup-keda
	kubectl apply -k $(DEV_OVERLAY)/
	$(MAKE) netpol-apiserver
	$(MAKE) install-gvisor
	$(MAKE) enforce-gvisor
	@echo "Stack sandbox déployée (overlay dev, in-cluster)."

# gVisor (runsc) — runtime d'isolation kernel OBLIGATOIRE pour les Jobs de
# détonation (cf. enforce-gvisor). Sans lui, tout pod charon.io/role=analysis est
# rejeté ("RuntimeClass gvisor not found") et les Jobs échouent en boucle.
# install-gvisor pose le binaire runsc + le shim containerd, déclare le runtime
# dans le containerd de K3s, redémarre k3s si la config a changé, puis crée la
# RuntimeClass gvisor. DOIT précéder enforce-gvisor (fail-closed). Idempotent.
GVISOR_ARCH         := $(shell uname -m)
GVISOR_URL          := https://storage.googleapis.com/gvisor/releases/release/latest/$(GVISOR_ARCH)
K3S_CONTAINERD_TMPL := /var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl

install-gvisor:
	@if command -v runsc >/dev/null 2>&1; then \
		echo "runsc déjà installé ($$(runsc --version 2>/dev/null | head -1))."; \
	else \
		echo "Installation gVisor (runsc + shim containerd) pour $(GVISOR_ARCH)..."; \
		cd /tmp && \
		curl -fsSL -O $(GVISOR_URL)/runsc -O $(GVISOR_URL)/runsc.sha512 \
		           -O $(GVISOR_URL)/containerd-shim-runsc-v1 -O $(GVISOR_URL)/containerd-shim-runsc-v1.sha512 && \
		sha512sum -c runsc.sha512 && sha512sum -c containerd-shim-runsc-v1.sha512 && \
		chmod a+rx runsc containerd-shim-runsc-v1 && \
		sudo mv runsc containerd-shim-runsc-v1 /usr/local/bin/; \
	fi
	@if ! sudo grep -q 'runtimes.runsc' $(K3S_CONTAINERD_TMPL) 2>/dev/null; then \
		echo "Déclaration du runtime runsc dans containerd K3s ($(K3S_CONTAINERD_TMPL))..."; \
		[ -f $(K3S_CONTAINERD_TMPL) ] || printf '{{ template "base" . }}\n' | sudo tee $(K3S_CONTAINERD_TMPL) >/dev/null; \
		printf '\n[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]\n  runtime_type = "io.containerd.runsc.v1"\n' \
			| sudo tee -a $(K3S_CONTAINERD_TMPL) >/dev/null; \
		echo "Redémarrage k3s (régénération config containerd)..."; \
		sudo systemctl restart k3s; \
		echo "Attente API K3s..."; \
		for i in $$(seq 1 30); do kubectl get nodes >/dev/null 2>&1 && break; sleep 2; done; \
	else \
		echo "Runtime runsc déjà déclaré dans containerd K3s."; \
	fi
	@printf 'apiVersion: node.k8s.io/v1\nkind: RuntimeClass\nmetadata:\n  name: gvisor\nhandler: runsc\n' \
		| kubectl apply -f -
	@echo "gVisor opérationnel : RuntimeClass 'gvisor' (handler runsc)."

# ValidatingAdmissionPolicy native (K8s >= 1.30) rendant gVisor OBLIGATOIRE pour
# les Jobs de détonation (refuse tout pod charon.io/role=analysis sans
# runtimeClassName=gvisor). Suppose gVisor installé (cf. install-gvisor, appelé
# avant dans deploy-dev). Idempotent.
enforce-gvisor:
	kubectl apply -f infrastructure/k8s-manifests/applications/sandbox/require-gvisor-vap.yaml

# NetworkPolicy autorisant le consumer -> kube-apiserver. L'apiserver K3s est
# host-networked, donc non matchable par namespaceSelector ; on autorise l'IP du
# nœud, AUTO-DÉCOUVERTE (NODE_IP) pour ne rien figer dans git. Additive à
# consumer-egress. Idempotent.
netpol-apiserver:
	@test -n "$(NODE_IP)" || { echo "ERREUR: NODE_IP introuvable (hostname -I)."; exit 1; }
	@echo "NetworkPolicy apiserver egress -> NODE_IP=$(NODE_IP)"
	@sed 's|__NODE_IP__|$(NODE_IP)|g' \
		infrastructure/k8s-manifests/applications/sandbox/consumer-apiserver-egress.yaml.tmpl \
		| kubectl apply -f -

undeploy:
	kubectl delete -k $(DEV_OVERLAY)/ --ignore-not-found
	kubectl delete networkpolicy consumer-apiserver-egress -n sandbox --ignore-not-found
	kubectl delete -f infrastructure/k8s-manifests/applications/sandbox/require-gvisor-vap.yaml --ignore-not-found

# ---------------------------------------------------------------------------
# Cleanup / teardown — DESTRUCTIVE (CONFIRM=yes guard required)
# ---------------------------------------------------------------------------

# clean: tear down everything in-cluster (sandbox workers + Kafka + MinIO + KEDA).
# KEEPS k3s AND Calico (the CNI) → direct re-deploy via make deploy && launch.
# DESTRUCTIVE: deletes the PVs (MinIO sandbox-reports + Kafka data). Idempotent.
clean:
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "DESTRUCTIF — supprime : workers sandbox + Kafka + MinIO (DONNÉES incluses) + KEDA."; \
		echo "k3s + Calico CONSERVÉS → re-déploiement : make deploy && make launch."; \
		echo ">>> Confirme avec : make clean CONFIRM=yes"; \
		exit 1; \
	fi
	-$(MAKE) undeploy
	-helm uninstall keda -n keda 2>/dev/null || true
	-kubectl delete namespace kafka minio keda --ignore-not-found
	@echo "Teardown in-cluster terminé (k3s + Calico conservés)."

# clean-all: full NUKE. Uninstalls k3s ENTIRELY (cluster, Calico, ALL data),
# removes the redis container and ONLY the project's docker images (no global
# prune — we don't touch other projects' images). Back to a bare VM → rebuild
# with make configuration && make deploy && make launch.
clean-all:
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "TRÈS DESTRUCTIF — désinstalle k3s ENTIÈREMENT (cluster + Calico + TOUTES les données),"; \
		echo "supprime le conteneur redis et les 4 images docker du projet. Retour VM nue."; \
		echo "Reconstruction : make configuration && make deploy && make launch."; \
		echo ">>> Confirme avec : make clean-all CONFIRM=yes"; \
		exit 1; \
	fi
	-docker compose down 2>/dev/null || true
	-docker rm -f redis 2>/dev/null || true
	-docker rmi ghcr.io/kayodevv/charon-sandbox-consumer:latest \
		ghcr.io/kayodevv/ubuntu-sandbox:v1 \
		ghcr.io/kayodevv/ubuntu-pdf-sandbox:v1 \
		ghcr.io/kayodevv/charon-minio-watcher:latest 2>/dev/null || true
	@if [ -x /usr/local/bin/k3s-uninstall.sh ]; then \
		echo "Désinstallation k3s (cluster + données)..."; \
		sudo /usr/local/bin/k3s-uninstall.sh; \
	else \
		echo "k3s-uninstall.sh introuvable — k3s déjà désinstallé ?"; \
	fi
	@echo "VM nettoyée. Reconstruire : make configuration && make deploy && make launch."

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
