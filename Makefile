# ══════════════════════════════════════════════════════════════════════════════
# CHARON — Zero-Trust Endpoint Analysis Platform
# Root Makefile — parent-child orchestrator + K3s operations
#
# Service usage : make <action> [SERVICE...]
# Infra usage   : make configuration / make deploy-infra / make launch
# ══════════════════════════════════════════════════════════════════════════════

.DEFAULT_GOAL := help

# ── Service registry ──────────────────────────────────────────────────────────
BACKEND_DIR  := apps/core-backend
FRONTEND_DIR := apps/frontend
ML_DIR       := apps/workers/ml_layer
SANDBOX_DIR  := apps/workers/sandbox_layer
LLM_DIR      := apps/workers/llm_layer
VERDICT_DIR  := apps/workers/verdict_layer
MINIO_DIR    := apps/workers/minio_watcher
SINKHOLE_DIR := apps/sinkhole
SHARED_DIR   := packages/core
SCHEMAS_DIR  := packages/kafka-schemas

SERVICE_NAMES := BACKEND FRONTEND ML SANDBOX LLM VERDICT MINIO SINKHOLE SHARED SCHEMAS
ALL_SVC_DIRS  := $(BACKEND_DIR) $(FRONTEND_DIR) $(ML_DIR) $(SANDBOX_DIR) \
                 $(LLM_DIR) $(VERDICT_DIR) $(MINIO_DIR) $(SINKHOLE_DIR) $(SHARED_DIR) $(SCHEMAS_DIR)

# ── Service dispatch ──────────────────────────────────────────────────────────
# make build LLM  ->  _SVC = LLM  ->  delegates to apps/workers/llm_layer
_SVC := $(filter $(SERVICE_NAMES),$(MAKECMDGOALS))
_TARGET_DIRS = $(if $(_SVC),$(foreach s,$(_SVC),$($(s)_DIR)),$(ALL_SVC_DIRS))

# Catch service names so Make doesn't error on "No rule to make target 'LLM'"
.PHONY: $(SERVICE_NAMES)
$(SERVICE_NAMES):
	@:

# ── K3s / infra variables ────────────────────────────────────────────────────
NODE_IP := $(shell hostname -I 2>/dev/null | awk '{print $$1}')
HOST_USER := $(shell echo $${USER:-$$(whoami)})
DEV_OVERLAY := infrastructure/k8s-manifests/overlays/dev

KAFKA_CHART_VERSION   := 31.0.0
CALICO_VERSION        := v3.27.3
MINIO_OPERATOR_REF    := v5.0.15
KAFKA_NODEPORT        := 32092
# Validation tunables — mirror scripts/validation/Makefile. Defaults live here so
# omitting them on sandbox-validate/-benchmark never passes an empty value down
# (an empty MAX_INFLIGHT= would override the sub-make default and break the feeder).
REPS                  ?= 1
MAX_INFLIGHT          ?= 7
LABEL_SOURCE          ?= unspecified
KUBECTL_REPO_VERSION  := v1.30

# ── Colors ────────────────────────────────────────────────────────────────────
_RST  := \033[0m
_BOLD := \033[1m
_DIM  := \033[2m
_CYN  := \033[36m
_YLW  := \033[33m
_GRN  := \033[32m
_RED  := \033[31m

# ── Tools ─────────────────────────────────────────────────────────────────────
DOCKER_COMPOSE := $(shell command -v docker-compose 2>/dev/null || echo "docker compose")

# ══════════════════════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: help
help:
	@printf "\n"
	@printf "$(_BOLD)$(_CYN)  ░█████╗░██╗░░██╗░█████╗░██████╗░░█████╗░███╗░░██╗$(_RST)\n"
	@printf "$(_BOLD)$(_CYN)  ██╔══██╗██║░░██║██╔══██╗██╔══██╗██╔══██╗████╗░██║$(_RST)\n"
	@printf "$(_BOLD)$(_CYN)  ██║░░╚═╝███████║███████║██████╔╝██║░░██║██╔██╗██║$(_RST)\n"
	@printf "$(_BOLD)$(_CYN)  ██║░░██╗██╔══██║██╔══██║██╔══██╗██║░░██║██║╚████║$(_RST)\n"
	@printf "$(_BOLD)$(_CYN)  ╚█████╔╝██║░░██║██║░░██║██║░░██║╚█████╔╝██║░╚███║$(_RST)\n"
	@printf "$(_BOLD)$(_CYN)  ░╚════╝░╚═╝░░╚═╝╚═╝░░╚═╝╚═╝░░╚═╝░╚════╝░╚═╝░░╚══╝$(_RST)\n"
	@printf "$(_DIM)  Zero-Trust Endpoint Analysis Platform$(_RST)\n"
	@printf "\n"
	@printf "$(_BOLD)$(_YLW)  SERVICES$(_RST)  $(_CYN)BACKEND$(_RST) · $(_CYN)FRONTEND$(_RST) · $(_CYN)ML$(_RST) · $(_CYN)SANDBOX$(_RST) · $(_CYN)LLM$(_RST) · $(_CYN)VERDICT$(_RST) · $(_CYN)MINIO$(_RST) · $(_CYN)SINKHOLE$(_RST) · $(_CYN)SHARED$(_RST) · $(_CYN)SCHEMAS$(_RST)\n"
	@printf "\n"
	@printf "$(_BOLD)$(_YLW)  USAGE$(_RST)     make <action> [SERVICE...]\n"
	@printf "\n"
	@printf "$(_BOLD)$(_YLW)  ACTIONS$(_RST)\n"
	@printf "    install     Install dependencies\n"
	@printf "    build       Build service\n"
	@printf "    test        Run tests\n"
	@printf "    lint        Check code\n"
	@printf "    format      Format code\n"
	@printf "    typecheck   Type check\n"
	@printf "    run         Start dev server (+ infra)\n"
	@printf "    deploy      Build + push Docker image\n"
	@printf "    clean       Remove artifacts\n"
	@printf "    ci          Full CI pipeline (lint + typecheck + test)\n"
	@printf "\n"
	@printf "$(_BOLD)$(_YLW)  INFRA (local)$(_RST)\n"
	@printf "    up            Start the local Redis (compose)\n"
	@printf "    down          Stop local infrastructure\n"
	@printf "    status        Container status\n"
	@printf "\n"
	@printf "$(_BOLD)$(_YLW)  K3s (cluster)$(_RST)\n"
	@printf "    configuration Fresh install (tools + deps + kubeconfig + DNS)\n"
	@printf "    deploy-infra  Bring up MinIO, then run the Terraform flow below\n"
	@printf "    launch        Build images + deploy workers\n"
	@printf "    import-images Build + import images into K3s containerd\n"
	@printf "\n"
	@printf "$(_BOLD)$(_YLW)  Terraform (infra: ns, RBAC, netpol, RuntimeClass, KEDA, Kafka)$(_RST)\n"
	@printf "    tf-bootstrap-state  Create the state bucket in MinIO (once)\n"
	@printf "    tf-init             terraform init (s3 backend)\n"
	@printf "    tf-import-*         Import existing objects before the first apply\n"
	@printf "    tf-plan / tf-apply  Plan (must be empty after import) / apply\n"
	@printf "\n"
	@printf "$(_BOLD)$(_YLW)  EXAMPLES$(_RST)\n"
	@printf "    make test              Test all services\n"
	@printf "    make build LLM         Build the LLM Layer\n"
	@printf "    make run BACKEND       Start the API (+ infra)\n"
	@printf "    make lint ML SHARED    Lint ML Layer and zt-shared\n"
	@printf "\n"
	@printf "  Variables: NODE_IP=$(NODE_IP)  KAFKA_NODEPORT=$(KAFKA_NODEPORT)  HOST_USER=$(HOST_USER)\n"
	@printf "\n"

# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE ACTIONS — delegated to child Makefiles
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: svc-install svc-build svc-test svc-lint svc-format svc-typecheck svc-deploy svc-clean

install:
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir install || exit 1; \
	done

build:
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir build || exit 1; \
	done

test:
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir test || exit 1; \
	done

lint:
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir lint || exit 1; \
	done

format:
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir format || exit 1; \
	done

typecheck:
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir typecheck || exit 1; \
	done

deploy:
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir deploy || exit 1; \
	done

.PHONY: run
run:
	@$(MAKE) --no-print-directory up
ifneq ($(_SVC),)
	@for dir in $(_TARGET_DIRS); do \
		$(MAKE) --no-print-directory -C $$dir run; \
	done
else
	@printf "\n$(_BOLD)Usage: make run <SERVICE>$(_RST)\n"
	@printf "  e.g. make run BACKEND, make run FRONTEND\n\n"
endif

.PHONY: ci
ci:
	@printf "$(_BOLD)$(_CYN)══ CI Pipeline$(_RST)\n"
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory typecheck
	@$(MAKE) --no-print-directory test
	@printf "\n$(_GRN)$(_BOLD)  ✓ CI pipeline complete$(_RST)\n\n"

# ══════════════════════════════════════════════════════════════════════════════
#  LOCAL INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: up down kafka-logs status

up:
	docker compose up -d redis
	@printf "$(_GRN)  Redis started. Kafka and MinIO are in-cluster — see make deploy-infra.$(_RST)\n"

down:
	docker compose down

kafka-logs:
	docker compose logs -f kafka-init

status:
	docker compose ps

# ══════════════════════════════════════════════════════════════════════════════
#  K3s — CONFIGURATION (fresh install, run once)
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: configuration _apt-deps install-k3s install-kubectl install-helm install-docker install-k9s \
        setup-kubeconfig setup-calico fix-dns-fai

configuration: _apt-deps install-docker install-k3s install-kubectl install-helm install-k9s setup-kubeconfig setup-calico fix-dns-fai install
	@echo ""
	@echo "=== Configuration complete ==="
	@echo "Tools installed: k3s, kubectl, helm, docker, k9s + Python deps."
	@echo "kubeconfig in place, Calico CNI deployed (NetworkPolicy enforcement), ISP DNS fixed."
	@echo ""
	@echo ">>> If docker was just added to your group: LOG OUT/LOG BACK IN"
	@echo ">>> (or run 'newgrp docker') BEFORE 'make deploy-infra' / 'make launch'."
	@echo ""
	@echo "Next step: make deploy-infra"

_apt-deps:
	sudo apt update
	sudo apt install -y build-essential python3-pip python-is-python3 \
		git curl gnupg ca-certificates net-tools

install-k3s:
	@if command -v k3s >/dev/null 2>&1; then \
		echo "k3s already installed ($$(k3s --version 2>/dev/null | head -1))."; \
	else \
		echo "Installing k3s single-node (flannel disabled for Calico)..."; \
		curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--flannel-backend=none --disable-network-policy" sh -; \
	fi

install-kubectl:
	sudo mkdir -p /etc/apt/keyrings
	@if [ ! -f /etc/apt/keyrings/kubernetes-apt-keyring.gpg ]; then \
		curl -fsSL https://pkgs.k8s.io/core:/stable:/$(KUBECTL_REPO_VERSION)/deb/Release.key | \
			sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg; \
		echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/$(KUBECTL_REPO_VERSION)/deb/ /' | \
			sudo tee /etc/apt/sources.list.d/kubernetes.list >/dev/null; \
	fi
	sudo apt update && sudo apt install -y kubectl

install-helm:
	@if command -v helm >/dev/null 2>&1; then \
		echo "helm already installed ($$(helm version --short 2>/dev/null))."; \
	else \
		curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash; \
	fi

install-docker:
	@if command -v docker >/dev/null 2>&1; then \
		echo "docker already installed ($$(docker --version 2>/dev/null))."; \
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
		echo ">>> $(HOST_USER) added to docker group — RELOG required to activate."; \
	fi

install-k9s:
	@if command -v k9s >/dev/null 2>&1; then \
		echo "k9s already installed."; \
	else \
		curl -sL https://github.com/derailed/k9s/releases/latest/download/k9s_linux_amd64.deb -o /tmp/k9s.deb; \
		sudo apt install -y /tmp/k9s.deb && rm -f /tmp/k9s.deb; \
	fi

setup-kubeconfig:
	@if [ ! -f /etc/rancher/k3s/k3s.yaml ]; then \
		echo "ERROR: /etc/rancher/k3s/k3s.yaml not found. Is k3s installed?"; \
		exit 1; \
	fi
	@mkdir -p $(HOME)/.kube
	@if ! sudo cmp -s /etc/rancher/k3s/k3s.yaml $(HOME)/.kube/config 2>/dev/null; then \
		sudo cp /etc/rancher/k3s/k3s.yaml $(HOME)/.kube/config; \
		sudo chown $(shell id -u):$(shell id -g) $(HOME)/.kube/config; \
		chmod 600 $(HOME)/.kube/config; \
		echo "kubeconfig updated."; \
	else \
		echo "kubeconfig already up to date."; \
	fi
	@grep -q 'KUBECONFIG=' $(HOME)/.bashrc 2>/dev/null || \
		echo 'export KUBECONFIG=$$HOME/.kube/config' >> $(HOME)/.bashrc
	@kubectl get nodes >/dev/null 2>&1 && echo "kubectl OK." \
		|| (echo "WARNING: kubectl cannot reach the cluster."; exit 1)

# Calico CNI (tigera-operator). K3s runs with flannel disabled — Calico provides
# BOTH the dataplane AND NetworkPolicy enforcement. Without this the cluster has
# no CNI (nodes NotReady) and enforces no NetworkPolicy. Idempotent.
setup-calico:
	@command -v kubectl >/dev/null 2>&1 || { echo "ERROR: kubectl not installed (make install-kubectl)."; exit 1; }
	@if kubectl get installation default >/dev/null 2>&1; then \
		echo "Calico already installed (Installation 'default' present)."; \
	else \
		echo "Installing tigera-operator $(CALICO_VERSION) (server-side apply)..."; \
		kubectl apply --server-side --force-conflicts -f https://raw.githubusercontent.com/projectcalico/calico/$(strip $(CALICO_VERSION))/manifests/tigera-operator.yaml; \
		echo "Waiting for tigera-operator (Available)..."; \
		kubectl rollout status deployment/tigera-operator -n tigera-operator --timeout=180s; \
		echo "Waiting for Installation CRD to be Established..."; \
		kubectl wait --for=condition=Established crd/installations.operator.tigera.io --timeout=120s; \
		kubectl apply -f infrastructure/k8s-manifests/system/calico/installation.yaml; \
	fi
	@echo "Waiting for operator to create TigeraStatus/calico (async)..."
	@for i in $$(seq 1 60); do \
		kubectl get tigerastatus calico >/dev/null 2>&1 && break; \
		echo "  not yet created, retry ($$i/60)..."; \
		sleep 5; \
	done
	@echo "Waiting for Calico to be Available (dataplane rollout, 1-2 min)..."
	kubectl wait --for=condition=Available tigerastatus/calico --timeout=300s
	@echo "Calico operational: CNI + NetworkPolicy enforcement (calico-system)."

# Fix ISP DNS hijacking (e.g. SFR/Numericable NXDOMAIN hijack on *.cluster.local).
# Forces a clean resolv.conf declared in k3s config. Idempotent.
fix-dns-fai:
	@if [ ! -d /etc/rancher/k3s ]; then \
		echo "ERROR: /etc/rancher/k3s not found — install k3s first (make install-k3s)."; \
		exit 1; \
	fi
	@printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' | sudo tee /etc/k3s-resolv.conf >/dev/null
	@if ! sudo grep -q '^resolv-conf:' /etc/rancher/k3s/config.yaml 2>/dev/null; then \
		echo 'resolv-conf: /etc/k3s-resolv.conf' | sudo tee -a /etc/rancher/k3s/config.yaml >/dev/null; \
		echo "config.yaml: 'resolv-conf' added."; \
	else \
		echo "config.yaml: 'resolv-conf' already present."; \
	fi
	sudo systemctl restart k3s
	@echo "ISP DNS fixed (resolv-conf -> 1.1.1.1 / 8.8.8.8). k3s restarted."

# ══════════════════════════════════════════════════════════════════════════════
#  K3s — DEPLOY (in-cluster infra)
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: deploy-infra setup-keda setup-kafka deploy-kafka deploy-minio

deploy-infra: setup-kubeconfig deploy-minio
	@echo ""
	@echo "=== MinIO ready (kustomize/Make-owned) ==="
	@echo "The engine (KEDA + Kafka) is now Terraform-owned. Bring it up with:"
	@echo "  make tf-bootstrap-state && make tf-init"
	@echo "  make tf-import-namespaces tf-import-compartments tf-import-engine  # existing cluster"
	@echo "  make tf-plan   # MUST be empty, then: make tf-apply"
	@echo "MinIO: minio.minio.svc.cluster.local:9000"
	@echo ""
	@echo "Next step: make launch"

# DEPRECATED — KEDA + Kafka are now Terraform-owned (helm_release in helm.tf).
# Kept as no-op shims so existing scripts/docs do not break. Use the tf-* flow.
setup-keda:
	@echo "DEPRECATED: KEDA is Terraform-owned (helm.tf). Use 'make tf-apply' (see deploy-infra)."

setup-kafka:
	@echo "DEPRECATED: Kafka is Terraform-owned (helm.tf). Use 'make tf-apply' (see deploy-infra)."

deploy-kafka: setup-kafka

deploy-minio:
	kubectl apply -k infrastructure/k8s-manifests/applications/minio/
	@echo "Waiting for MinIO Ready..."
	kubectl rollout status statefulset/minio -n minio --timeout=300s
	@echo "MinIO in-cluster ready. Internal service: minio.minio.svc.cluster.local:9000"

# ══════════════════════════════════════════════════════════════════════════════
#  Terraform — driver (T1: state backend + namespaces)
#  Make/TF boundary: see docs/terraform-frontier.md. TF owns the compartments +
#  the engine; Make stays the DRIVER (init/plan/apply) + the one-shot bootstrap
#  of the state bucket (chicken/egg: the state lives in MinIO).
# ══════════════════════════════════════════════════════════════════════════════

TERRAFORM_DIR    := infrastructure/terraform
MINIO_NODEPORT   ?= 32090
TF_STATE_BUCKET  ?= terraform-state

.PHONY: tf-bootstrap-state tf-init tf-plan tf-apply tf-import-namespaces tf-import-compartments tf-import-engine

# One-shot: create the state bucket in MinIO (already running) BEFORE any
# tf-init. Idempotent (mc mb -p ... || true). MinIO must be up (make deploy-minio).
tf-bootstrap-state:
	@command -v mc >/dev/null 2>&1 || { echo "ERROR: mc (MinIO client) not installed."; exit 1; }
	@test -n "$(NODE_IP)" || { echo "ERROR: NODE_IP not found (hostname -I)."; exit 1; }
	mc alias set charon-tf http://$(NODE_IP):$(MINIO_NODEPORT) minioadmin minioadmin
	mc mb -p charon-tf/$(TF_STATE_BUCKET) || true
	@echo "State bucket '$(TF_STATE_BUCKET)' ready on MinIO ($(NODE_IP):$(MINIO_NODEPORT))."

tf-init:
	cd $(TERRAFORM_DIR) && terraform init

tf-plan:
	cd $(TERRAFORM_DIR) && terraform plan

tf-apply:
	cd $(TERRAFORM_DIR) && terraform apply

# Import BEFORE the first apply (otherwise "already exists"). The 4 namespaces
# already exist (historically created by kustomize). Idempotent: a namespace
# already in state is skipped ("Resource already managed").
tf-import-namespaces:
	cd $(TERRAFORM_DIR) && for ns in kafka minio sandbox sinkhole; do \
		terraform import "kubernetes_namespace.charon[\"$$ns\"]" "$$ns" || true; \
	done
	@echo "Namespaces imported. Verify: make tf-plan MUST show 0 changes."

# T2 compartments: import the existing RBAC / NetworkPolicy / RuntimeClass
# objects BEFORE the first apply. Namespaced ids = "<ns>/<name>"; the
# cluster-scoped RuntimeClass id = "<name>". Idempotent (|| true).
# NOTE: the gvisor VAP stays Make-owned (make enforce-gvisor) — no typed
# provider resource. consumer-apiserver-egress stays Make-owned (host node IP).
tf-import-compartments:
	cd $(TERRAFORM_DIR) && printf '%s\n' \
		'kubernetes_service_account_v1.consumer sandbox/sandbox-consumer' \
		'kubernetes_service_account_v1.analysis sandbox/sandbox-analysis' \
		'kubernetes_service_account_v1.watcher sandbox/sandbox-watcher' \
		'kubernetes_role_v1.job_dispatcher sandbox/sandbox-job-dispatcher' \
		'kubernetes_role_binding_v1.consumer_can_dispatch sandbox/sandbox-consumer-can-dispatch' \
		'kubernetes_network_policy_v1.sandbox_deny_all sandbox/deny-all-default' \
		'kubernetes_network_policy_v1.consumer_egress sandbox/consumer-egress' \
		'kubernetes_network_policy_v1.watcher_egress sandbox/watcher-egress' \
		'kubernetes_network_policy_v1.analysis_egress sandbox/analysis-egress' \
		'kubernetes_network_policy_v1.kafka_deny_all kafka/deny-all-default' \
		'kubernetes_network_policy_v1.kafka_allow kafka/kafka-allow' \
		'kubernetes_network_policy_v1.sinkhole_deny_egress sinkhole/sinkhole-deny-egress' \
		'kubernetes_runtime_class_v1.gvisor gvisor' \
		| while read -r addr id; do terraform import "$$addr" "$$id" || true; done
	@echo "Compartments imported. Verify: make tf-plan MUST show 0 changes."

# T3 engine: import the existing Helm releases (id = "<namespace>/<release>").
# BEFORE importing KEDA, set keda_chart_version to the deployed version
# (helm list -n keda) so the first plan is empty. Idempotent (|| true).
tf-import-engine:
	cd $(TERRAFORM_DIR) && printf '%s\n' \
		'helm_release.keda keda/keda' \
		'helm_release.kafka kafka/kafka' \
		| while read -r addr id; do terraform import "$$addr" "$$id" || true; done
	@echo "Engine imported. Verify: make tf-plan MUST show 0 changes (align chart versions/values if not)."

# ══════════════════════════════════════════════════════════════════════════════
#  K3s — LAUNCH (images + workers)
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: launch import-images deploy-dev

launch: import-images deploy-dev
	@echo ""
	@echo "=== Sandbox stack launched ==="
	@echo "Images imported into containerd, workers deployed (dev overlay)."
	@echo "Monitor: k9s   or   kubectl get pods -A"

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

# Sinkhole image build is owned by its child Makefile (apps/sinkhole), per the
# parent-child build contract; root only orchestrates the K3s import.
build-sinkhole:
	$(MAKE) -C $(SINKHOLE_DIR) build

import-images: build-consumer build-sandbox build-pdf-sandbox build-watcher build-sinkhole
	docker save ghcr.io/kayodevv/charon-sandbox-consumer:latest | sudo k3s ctr images import -
	docker save ghcr.io/kayodevv/ubuntu-sandbox:v1              | sudo k3s ctr images import -
	docker save ghcr.io/kayodevv/ubuntu-pdf-sandbox:v1          | sudo k3s ctr images import -
	docker save ghcr.io/kayodevv/charon-minio-watcher:latest    | sudo k3s ctr images import -
	docker save ghcr.io/kayodevv/inetsim-sinkhole:v1.0.0        | sudo k3s ctr images import -
	@echo "Images imported into K3s."

deploy-dev: setup-kubeconfig
	@# KEDA is Terraform-owned (helm.tf, make tf-apply) — no longer installed here.
	kubectl apply -k $(DEV_OVERLAY)/
	$(MAKE) netpol-apiserver
	$(MAKE) install-gvisor
	$(MAKE) enforce-gvisor
	@echo "Sandbox stack deployed (dev overlay, in-cluster)."

# DEV-only host exposure: NodePorts so the host-side validator/feeder can reach
# Kafka (32092) + MinIO (32090). NOT for prod (prod = ClusterIP only).
.PHONY: dev-expose dev-teardown
# Kafka is Terraform-owned (helm.tf): flip the dev externalAccess via a TF
# variable, NOT a parallel `helm upgrade` (single owner). MinIO stays Make-owned,
# so its dev NodePort remains a direct kubectl apply.
dev-expose:
	cd $(TERRAFORM_DIR) && terraform apply -auto-approve -var kafka_dev_external_access=true
	kubectl apply -f infrastructure/k8s-manifests/applications/minio/dev/minio-nodeport.yaml
	@echo "DEV exposed — Kafka $(NODE_IP):$(KAFKA_NODEPORT) + MinIO $(NODE_IP):32090 (host validator/feeder)."

dev-teardown:
	cd $(TERRAFORM_DIR) && terraform apply -auto-approve -var kafka_dev_external_access=false
	kubectl delete -f infrastructure/k8s-manifests/applications/minio/dev/minio-nodeport.yaml --ignore-not-found
	@echo "DEV NodePorts removed (prod-safe ClusterIP only)."

# ══════════════════════════════════════════════════════════════════════════════
#  K3s — gVisor + NetworkPolicy + Validation
# ══════════════════════════════════════════════════════════════════════════════

GVISOR_ARCH         := $(shell uname -m)
GVISOR_URL          := https://storage.googleapis.com/gvisor/releases/release/latest/$(GVISOR_ARCH)
K3S_CONTAINERD_TMPL := /var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl

.PHONY: install-gvisor enforce-gvisor netpol-apiserver undeploy

install-gvisor:
	@if command -v runsc >/dev/null 2>&1; then \
		echo "runsc already installed ($$(runsc --version 2>/dev/null | head -1))."; \
	else \
		echo "Installing gVisor (runsc + containerd shim) for $(GVISOR_ARCH)..."; \
		cd /tmp && \
		curl -fsSL -O $(GVISOR_URL)/runsc -O $(GVISOR_URL)/runsc.sha512 \
		           -O $(GVISOR_URL)/containerd-shim-runsc-v1 -O $(GVISOR_URL)/containerd-shim-runsc-v1.sha512 && \
		sha512sum -c runsc.sha512 && sha512sum -c containerd-shim-runsc-v1.sha512 && \
		chmod a+rx runsc containerd-shim-runsc-v1 && \
		sudo mv runsc containerd-shim-runsc-v1 /usr/local/bin/; \
	fi
	@if ! sudo grep -q 'runtimes.runsc' $(K3S_CONTAINERD_TMPL) 2>/dev/null; then \
		echo "Declaring runsc runtime in K3s containerd ($(K3S_CONTAINERD_TMPL))..."; \
		[ -f $(K3S_CONTAINERD_TMPL) ] || printf '{{ template "base" . }}\n' | sudo tee $(K3S_CONTAINERD_TMPL) >/dev/null; \
		printf '\n[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]\n  runtime_type = "io.containerd.runsc.v1"\n' \
			| sudo tee -a $(K3S_CONTAINERD_TMPL) >/dev/null; \
		echo "Restarting k3s (containerd config regeneration)..."; \
		sudo systemctl restart k3s; \
		echo "Waiting for K3s API..."; \
		for i in $$(seq 1 30); do kubectl get nodes >/dev/null 2>&1 && break; sleep 2; done; \
	else \
		echo "runsc runtime already declared in K3s containerd."; \
	fi
	@echo "gVisor host layer ready (runsc binary + containerd runtime)."
	@echo "The RuntimeClass 'gvisor' K8s object is owned by Terraform (make tf-apply)."

enforce-gvisor:
	kubectl apply -f infrastructure/k8s-manifests/applications/sandbox/require-gvisor-vap.yaml

netpol-apiserver:
	@test -n "$(NODE_IP)" || { echo "ERROR: NODE_IP not found (hostname -I)."; exit 1; }
	@echo "NetworkPolicy apiserver egress -> NODE_IP=$(NODE_IP)"
	@sed 's|__NODE_IP__|$(NODE_IP)|g' \
		infrastructure/k8s-manifests/applications/sandbox/consumer-apiserver-egress.yaml.tmpl \
		| kubectl apply -f -

undeploy:
	kubectl delete -k $(DEV_OVERLAY)/ --ignore-not-found
	kubectl delete networkpolicy consumer-apiserver-egress -n sandbox --ignore-not-found
	kubectl delete -f infrastructure/k8s-manifests/applications/sandbox/require-gvisor-vap.yaml --ignore-not-found

# ══════════════════════════════════════════════════════════════════════════════
#  K3s — LOCAL RUN (port-forward to in-cluster)
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: run-watcher run-consumer

run-watcher:
	@echo "Prerequisite: port-forward Kafka (9092) and MinIO (9000) from K3s."
	KAFKA_BOOTSTRAP=localhost:9092 \
	MINIO_ENDPOINT=localhost:9000 \
	MINIO_PRESIGN_ENDPOINT=localhost:9000 \
	MINIO_ACCESS_KEY=minioadmin \
	MINIO_SECRET_KEY=minioadmin \
	MINIO_BUCKET=sandbox-reports \
	python3 apps/workers/minio_watcher/watcher.py

run-consumer:
	@echo "Prerequisite: port-forward Kafka (9092) from K3s."
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

# ══════════════════════════════════════════════════════════════════════════════
#  SANDBOX VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: sandbox-validate sandbox-benchmark
sandbox-validate:
	KAFKA_BOOTSTRAP=$(NODE_IP):$(KAFKA_NODEPORT) \
	$(MAKE) -f scripts/validation/Makefile run \
		RUN_ID=$(RUN_ID) CORPUS=$(CORPUS) \
		REPS=$(REPS) MAX_INFLIGHT=$(MAX_INFLIGHT) \
		LABEL_SOURCE=$(LABEL_SOURCE)

# Large-N accuracy benchmark (on-demand, NOT a CI gate) — delegates to the
# validation tool Makefile, same as sandbox-validate.
sandbox-benchmark:
	KAFKA_BOOTSTRAP=$(NODE_IP):$(KAFKA_NODEPORT) \
	$(MAKE) -f scripts/validation/Makefile benchmark \
		CORPUS=$(CORPUS) RUN_ID=$(RUN_ID) \
		REPS=$(REPS) MAX_INFLIGHT=$(MAX_INFLIGHT) \
		LABEL_SOURCE=$(LABEL_SOURCE)

# ══════════════════════════════════════════════════════════════════════════════
#  MIGRATION / LEGACY
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: bootstrap-k3s bootstrap-in-cluster setup-minio-operator migrate-minio-data

bootstrap-k3s: setup-kubeconfig setup-keda
	@echo "K3s bootstrap complete (kubeconfig + KEDA). Next: make deploy-infra then make launch."

bootstrap-in-cluster: setup-kafka deploy-minio
	@echo "Kafka (Bitnami) + MinIO (StatefulSet) deployed in-cluster."

# DEPRECATED: MinIO now runs as a standalone StatefulSet (see make deploy-minio).
setup-minio-operator:
	@echo "DEPRECATED: MinIO runs as standalone StatefulSet (see make deploy-minio)."
	@kubectl get crd tenants.minio.min.io >/dev/null 2>&1 \
		&& echo "MinIO Operator already installed." \
		|| { \
			echo "Installing MinIO Operator $(MINIO_OPERATOR_REF)..."; \
			kubectl apply -k "github.com/minio/operator/?ref=$(MINIO_OPERATOR_REF)"; \
			kubectl wait deploy/minio-operator -n minio-operator --for=condition=Available --timeout=300s; \
		}

migrate-minio-data:
	@MINIO_NODEPORT=$$(kubectl get svc minio -n minio -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null); \
	if [ -z "$$MINIO_NODEPORT" ]; then \
		echo "MinIO service has no NodePort — creating temporary one for migration..."; \
		kubectl patch svc minio -n minio -p '{"spec":{"type":"NodePort"}}'; \
		MINIO_NODEPORT=$$(kubectl get svc minio -n minio -o jsonpath='{.spec.ports[0].nodePort}'); \
	fi; \
	echo "Migrating from 172.16.249.133:9000 (docker compose) to $(NODE_IP):$$MINIO_NODEPORT (in-cluster)..."; \
	docker run --rm --network host quay.io/minio/mc:RELEASE.2024-09-09T17-00-14Z sh -c "\
		mc alias set old http://172.16.249.133:9000 minioadmin minioadmin && \
		mc alias set new http://$(NODE_IP):$$MINIO_NODEPORT minioadmin minioadmin && \
		mc mb -p new/sandbox-reports || true && \
		mc mirror --overwrite old/sandbox-reports new/sandbox-reports && \
		echo 'Migration complete.'"

# ══════════════════════════════════════════════════════════════════════════════
#  CLEANUP
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: clean clean-all

clean:
ifneq ($(_SVC),)
	@for dir in $(_TARGET_DIRS); do \
		printf "$(_BOLD)$(_YLW)── $$dir$(_RST)\n"; \
		$(MAKE) --no-print-directory -C $$dir clean; \
	done
else
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "DESTRUCTIVE — removes: sandbox workers + Kafka + MinIO (DATA included) + KEDA."; \
		echo "k3s + Calico KEPT -> re-deploy with: make deploy-infra && make launch."; \
		echo ">>> Confirm with: make clean CONFIRM=yes"; \
		echo ">>> Or local cleanup only: make clean <SERVICE>"; \
		exit 1; \
	fi
	-$(MAKE) undeploy
	-helm uninstall keda -n keda 2>/dev/null || true
	-kubectl delete namespace kafka minio keda --ignore-not-found
	@echo "In-cluster teardown complete (k3s + Calico kept)."
endif

clean-all:
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "HIGHLY DESTRUCTIVE — uninstalls k3s ENTIRELY (cluster + Calico + ALL data),"; \
		echo "removes the redis container and the 4 project docker images. Back to bare VM."; \
		echo "Rebuild with: make configuration && make deploy-infra && make launch."; \
		echo ">>> Confirm with: make clean-all CONFIRM=yes"; \
		exit 1; \
	fi
	-docker compose down 2>/dev/null || true
	-docker rm -f redis 2>/dev/null || true
	-docker rmi ghcr.io/kayodevv/charon-sandbox-consumer:latest \
		ghcr.io/kayodevv/ubuntu-sandbox:v1 \
		ghcr.io/kayodevv/ubuntu-pdf-sandbox:v1 \
		ghcr.io/kayodevv/charon-minio-watcher:latest 2>/dev/null || true
	@if [ -x /usr/local/bin/k3s-uninstall.sh ]; then \
		echo "Uninstalling k3s (cluster + data)..."; \
		sudo /usr/local/bin/k3s-uninstall.sh; \
	else \
		echo "k3s-uninstall.sh not found — k3s already uninstalled?"; \
	fi
	@echo "VM cleaned. Rebuild with: make configuration && make deploy-infra && make launch."
