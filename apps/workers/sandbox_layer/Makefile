SERVICE_NAME := sandbox-layer

include ../../../makefiles/common.mk

include ../../../makefiles/versions.mk
ROOT           := $(shell d="$(CURDIR)"; while [ "$$d" != "/" ]; do [ -f "$$d/docker-compose.yml" ] && echo "$$d" && break; d=$$(dirname "$$d"); done)

.PHONY: help install build test lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(Docker)$(_RST)\n"
	@printf "  build       Build all 3 Docker images (consumer + agent + pdf-agent)\n"
	@printf "  deploy      Build + tag\n"
	@printf "  test        Pytest (if tests present)\n"
	@printf "  clean       Remove artifacts\n"

install:
	$(call skip,"$(SERVICE_NAME)","no dependency manager (Docker-only)")

build:
	$(call header,"$(SERVICE_NAME) — build (3 images)")
	docker build -t $(CONSUMER_IMAGE) -f Dockerfile.consumer $(ROOT)
	docker build -t $(AGENT_IMAGE)    -f Dockerfile.agent $(ROOT)
	docker build -t $(PDF_IMAGE)      -f Dockerfile.pdf-agent $(ROOT)

test:
	@if [ -d agent/tests ] && [ -n "$$(ls agent/tests/*.py 2>/dev/null)" ]; then \
		printf "\n\033[1m\033[36m══ $(SERVICE_NAME) — test\033[0m\n"; \
		python3 -m pytest agent/tests -v; \
	else \
		printf "\033[2m  ⏭ SKIP $(SERVICE_NAME) — no tests\033[0m\n"; \
	fi

lint:
	$(call skip,"$(SERVICE_NAME)","no pyproject.toml")

format:
	$(call skip,"$(SERVICE_NAME)","no pyproject.toml")

typecheck:
	$(call skip,"$(SERVICE_NAME)","no pyproject.toml")

run:
	$(call skip,"$(SERVICE_NAME)","use make run-consumer or kubectl")

deploy: build
	$(call header,"$(SERVICE_NAME) — deploy")
	@echo "Images built. Import to K3s: make import-images (from root)."

clean:
	$(call header,"$(SERVICE_NAME) — clean")
	rm -rf __pycache__ .pytest_cache
