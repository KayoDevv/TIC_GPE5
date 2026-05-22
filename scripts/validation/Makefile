# Validation corpus — sandbox layer
# Usage : make -f scripts/validation/Makefile run CORPUS=<dir> RUN_ID=<id> [REPS=N MAX_INFLIGHT=N]
# Ou via le Makefile racine : make sandbox-validate CORPUS=<dir> RUN_ID=<id>
#
# Post-Option-B : Kafka et MinIO tournent in-cluster (Bitnami + MinIO StatefulSet).
# Le feeder/validator sur host les joint via NodePort.
# Les Jobs in-cluster les joignent via DNS K8s (NetworkPolicy enforced).

NODE_IP      := $(shell hostname -I 2>/dev/null | awk '{print $$1}')
RUN_ID       ?= validation_$(shell date +%Y%m%d_%H%M%S)
REPS         ?= 1
CORPUS       ?= scripts/validation/real_corpus
MAX_INFLIGHT ?= 15
IDLE_TIMEOUT ?= 300
RATE         ?=

# Endpoint host pour upload — NodePort accessible depuis la VM (host)
KAFKA_BOOTSTRAP        ?= $(NODE_IP):32092
MINIO_NODEPORT         := $(shell kubectl get svc minio -n minio -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null)
MINIO_HOST_ENDPOINT    := $(if $(MINIO_NODEPORT),$(NODE_IP):$(MINIO_NODEPORT),$(NODE_IP):9000)

# Endpoint in-cluster — utilisé dans la presigned URL que les Jobs K3s consomment.
# DOIT être un DNS K8s pour que la NetworkPolicy `analysis-egress` autorise l'egress.
MINIO_CLUSTER_ENDPOINT := minio.minio.svc.cluster.local:9000

.PHONY: run feed collect report clean reset-offsets

# Point d'entrée unique : feed → collect → report.
# Le corpus doit contenir des sous-dossiers benign/, malicious/, unknown/ (label = nom du dossier).
run:
	@[ -d "$(CORPUS)" ] || { echo "ERREUR: corpus introuvable : $(CORPUS)"; exit 1; }
	@echo "=== [1/3] Feed ==="
	@$(MAKE) -f scripts/validation/Makefile feed
	@echo "=== [2/3] Collect ==="
	@$(MAKE) -f scripts/validation/Makefile collect DRAIN=1
	@echo "=== [3/3] Rapport ==="
	@$(MAKE) -f scripts/validation/Makefile report REPORT_RUN_ID=$(RUN_ID)

feed:
	@[ -d "$(CORPUS)" ] || { echo "ERREUR: corpus introuvable : $(CORPUS)"; exit 1; }
	KAFKA_BOOTSTRAP=$(KAFKA_BOOTSTRAP) \
	MINIO_ENDPOINT=$(MINIO_HOST_ENDPOINT) \
	MINIO_PRESIGN_ENDPOINT=$(MINIO_CLUSTER_ENDPOINT) \
	python3 -m scripts.validation.feeder \
		--corpus $(CORPUS) --run-id $(RUN_ID) \
		--repetitions $(REPS) --max-inflight $(MAX_INFLIGHT) \
		$(if $(RATE),--rate $(RATE),)

collect:
	KAFKA_BOOTSTRAP=$(KAFKA_BOOTSTRAP) \
	python3 -m scripts.validation.validator \
		$(if $(RUN_ID),--run-id $(RUN_ID),) \
		$(if $(filter 1,$(DRAIN)),--until-drained,) \
		--idle-timeout $(IDLE_TIMEOUT)

report:
	@mkdir -p validation
	python3 -m scripts.validation.report \
		$(if $(REPORT_RUN_ID),--run-id $(REPORT_RUN_ID),) \
		$(if $(THRESHOLD),--threshold $(THRESHOLD),)

clean:
	rm -f validation/feeder_state.duckdb validation/results.duckdb

# Reset offset du consumer group de validation (si résultats d'anciens runs traînent).
# Post-Option-B : kubectl exec dans le pod Bitnami Kafka (plus de docker exec).
reset-offsets:
	kubectl exec -n kafka kafka-controller-0 -- kafka-consumer-groups.sh \
		--bootstrap-server localhost:9092 \
		--group charon-validation-collector \
		--topic sandbox_layer.result \
		--reset-offsets --to-latest --execute
