SERVICE_NAME := minio-watcher

include ../../../makefiles/common.mk

IMAGE := ghcr.io/kayodevv/charon-minio-watcher:latest
ROOT  := $(shell d="$(CURDIR)"; while [ "$$d" != "/" ]; do [ -f "$$d/docker-compose.yml" ] && echo "$$d" && break; d=$$(dirname "$$d"); done)

.PHONY: help install build test lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(Docker)$(_RST)\n"
	@printf "  build       Build Docker image\n"
	@printf "  deploy      Build + tag\n"

install:
	$(call skip,"$(SERVICE_NAME)","no dependency manager (Docker-only)")

build:
	$(call header,"$(SERVICE_NAME) — build")
	docker build -t $(IMAGE) -f Dockerfile $(ROOT)

test:
	$(call skip,"$(SERVICE_NAME)","no tests")

lint:
	$(call skip,"$(SERVICE_NAME)","no linter (single file)")

format:
	$(call skip,"$(SERVICE_NAME)","no formatter (single file)")

typecheck:
	$(call skip,"$(SERVICE_NAME)","no type checker")

run:
	$(call skip,"$(SERVICE_NAME)","use make run-watcher (from root)")

deploy: build
	$(call header,"$(SERVICE_NAME) — deploy")
	@echo "Image built. Import to K3s: make import-images (from root)."

clean:
	$(call header,"$(SERVICE_NAME) — clean")
	@echo "Nothing to clean."
