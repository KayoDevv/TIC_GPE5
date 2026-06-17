# Validation corpus — sandbox layer
# Usage: make -f scripts/validation/Makefile run CORPUS=<dir> RUN_ID=<id> [REPS=N MAX_INFLIGHT=N]
# Or via the root Makefile: make sandbox-validate CORPUS=<dir> RUN_ID=<id>
#
# Post-Option-B: Kafka and MinIO run in-cluster (Bitnami + MinIO StatefulSet).
# The host-side feeder/validator reach them via NodePort.
# The in-cluster Jobs reach them via K8s DNS (NetworkPolicy enforced).

NODE_IP      := $(shell hostname -I 2>/dev/null | awk '{print $$1}')
RUN_ID       ?= validation_$(shell date +%Y%m%d_%H%M%S)
REPS         ?= 1
CORPUS       ?= scripts/validation/real_corpus
MAX_INFLIGHT ?= 7
IDLE_TIMEOUT ?= 300
RATE         ?=
# Label provenance (M2 anti-circularity): academic_groundtruth | av_consensus |
# synthetic | unspecified. 'av_consensus' is excluded from the report's independence figure.
LABEL_SOURCE ?= unspecified

# Host upload endpoint — FIXED NodePorts, enabled by `make dev-expose`
# (Kafka 32092 + MinIO 32090). Prerequisite: run `make dev-expose` before the
# tests. In prod these NodePorts do not exist (ClusterIP only) — the host
# feeder/validator runs in dev only.
KAFKA_BOOTSTRAP        ?= $(NODE_IP):32092
MINIO_HOST_ENDPOINT    ?= $(NODE_IP):32090

# In-cluster endpoint — used in the presigned URL the K3s Jobs consume.
# MUST be a K8s DNS name so the `analysis-egress` NetworkPolicy allows the egress.
MINIO_CLUSTER_ENDPOINT := minio.minio.svc.cluster.local:9000

.PHONY: run feed collect report clean reset-offsets golden-freeze golden-compare golden-extend benchmark

# Single entry point: feed → collect → report.
# The corpus must contain benign/, malicious/, unknown/ subfolders (label = folder name).
run:
	@[ -d "$(CORPUS)" ] || { echo "ERROR: corpus not found: $(CORPUS)"; exit 1; }
	@echo "=== [1/3] Feed ==="
	@$(MAKE) -f scripts/validation/Makefile feed
	@echo "=== [2/3] Collect ==="
	@$(MAKE) -f scripts/validation/Makefile collect DRAIN=1
	@echo "=== [3/3] Report ==="
	@$(MAKE) -f scripts/validation/Makefile report REPORT_RUN_ID=$(RUN_ID)

feed:
	@[ -d "$(CORPUS)" ] || { echo "ERROR: corpus not found: $(CORPUS)"; exit 1; }
	KAFKA_BOOTSTRAP=$(KAFKA_BOOTSTRAP) \
	MINIO_ENDPOINT=$(MINIO_HOST_ENDPOINT) \
	MINIO_PRESIGN_ENDPOINT=$(MINIO_CLUSTER_ENDPOINT) \
	python3 -m scripts.validation.feeder \
		--corpus $(CORPUS) --run-id $(RUN_ID) \
		--repetitions $(REPS) --max-inflight $(MAX_INFLIGHT) \
		--label-source $(LABEL_SOURCE) \
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

# Golden baseline (M3 anti-regression) — freezes the verdicts of a reference run,
# then compares every new run against this baseline BEFORE merging a scoring
# change. The baseline (hashes + scores only) is committed to git.
#   make -f scripts/validation/Makefile golden-freeze RUN_ID=run_OpusV1.4
#   make -f scripts/validation/Makefile golden-compare RUN_ID=<new_run>
golden-freeze:
	@[ -n "$(RUN_ID)" ] || { echo "ERROR: RUN_ID required (reference run to freeze)"; exit 1; }
	python3 -m scripts.validation.golden freeze --run-id $(RUN_ID) \
		$(if $(THRESHOLD),--threshold $(THRESHOLD),) \
		$(if $(SUSPICIOUS_THRESHOLD),--suspicious-threshold $(SUSPICIOUS_THRESHOLD),)

golden-compare:
	@[ -n "$(RUN_ID)" ] || { echo "ERROR: RUN_ID required (new run to compare)"; exit 1; }
	python3 -m scripts.validation.golden compare --run-id $(RUN_ID)

# Graft hand-triaged trap samples (found by a benchmark) onto the baseline
# without re-freezing everything. SHA = list of sha256 prefixes (space-separated)
# to ADD (gating); ACCEPT = out-of-scope prefixes (reported, never blocking — e.g. fb87d8a7).
#   make -f scripts/validation/Makefile golden-extend RUN_ID=big_test \
#        SHA="<dropper1> <dropper2> <near_threshold>" ACCEPT="<fb87d8a7>"
golden-extend:
	@[ -n "$(RUN_ID)" ] || { echo "ERROR: RUN_ID required (run the samples come from)"; exit 1; }
	@[ -n "$(SHA)$(ACCEPT)" ] || { echo "ERROR: SHA and/or ACCEPT required (sha256 prefixes)"; exit 1; }
	python3 -m scripts.validation.golden extend --run-id $(RUN_ID) \
		$(foreach s,$(SHA),--sha $(s)) \
		$(foreach s,$(ACCEPT),--accept $(s))

# Large-N accuracy benchmark — ON-DEMAND, NOT a CI gate.
# Replays a large corpus and produces the F1/recall/precision/distribution report
# (answers M7: large N for citable figures at the defence + post-D6).
# Different from golden: golden (small, gate) keeps KNOWN errors closed; the
# benchmark (large, throwaway) HUNTS unknown errors. Do not merge the two.
# REPS defaults to 3 for figure stability. Delegates to `run` (zero duplicated logic).
benchmark:
	@[ -d "$(CORPUS)" ] || { echo "ERROR: corpus not found: $(CORPUS)"; exit 1; }
	@$(MAKE) -f scripts/validation/Makefile run \
		CORPUS=$(CORPUS) \
		RUN_ID=$(if $(RUN_ID),$(RUN_ID),benchmark_$(shell date +%Y%m%d_%H%M%S)) \
		REPS=$(if $(REPS),$(REPS),3) MAX_INFLIGHT=$(MAX_INFLIGHT) \
		LABEL_SOURCE=$(LABEL_SOURCE)

clean:
	rm -f validation/feeder_state.duckdb validation/results.duckdb

# Reset the validation consumer-group offset (if results from old runs linger).
# Post-Option-B: kubectl exec into the Bitnami Kafka pod (no more docker exec).
reset-offsets:
	kubectl exec -n kafka kafka-controller-0 -- kafka-consumer-groups.sh \
		--bootstrap-server localhost:9092 \
		--group charon-validation-collector \
		--topic sandbox_layer.result \
		--reset-offsets --to-latest --execute
