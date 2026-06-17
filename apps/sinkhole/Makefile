SERVICE_NAME := sinkhole

include ../../makefiles/common.mk

IMAGE := ghcr.io/kayodevv/inetsim-sinkhole:v1.0.0

.PHONY: help install build test lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(Docker)$(_RST)\n"
	@printf "  build    Build the INetSim sinkhole image\n"
	@printf "  deploy   Build the image (import to K3s is a root op)\n"
	@printf "  clean    Remove build artifacts\n"

install:
	$(call skip,"$(SERVICE_NAME)","no dependency manager (Docker-only)")

build:
	$(call header,"$(SERVICE_NAME) — build")
	docker build -t $(IMAGE) -f Dockerfile.inetsim .

test:
	$(call skip,"$(SERVICE_NAME)","no tests")

lint:
	$(call skip,"$(SERVICE_NAME)","no pyproject.toml (Docker-only)")

format:
	$(call skip,"$(SERVICE_NAME)","no pyproject.toml (Docker-only)")

typecheck:
	$(call skip,"$(SERVICE_NAME)","not applicable")

run:
	$(call skip,"$(SERVICE_NAME)","deployed in-cluster via kustomize")

deploy: build
	$(call header,"$(SERVICE_NAME) — deploy")
	@echo "Image built. Import to K3s: make import-images (from root)."

clean:
	$(call header,"$(SERVICE_NAME) — clean")
	@echo "nothing to clean (Docker-only)"
