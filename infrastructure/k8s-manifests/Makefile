SERVICE_NAME := k8s-manifests

include ../../makefiles/common.mk

YAML_FILES := $(shell find . -name '*.yaml' -o -name '*.yml' 2>/dev/null | grep -v node_modules)

.PHONY: help install build test lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(Kubernetes)$(_RST)\n"
	@printf "  lint/test   kubeconform validation\n"

install:
	@echo "Nothing to install."

build:
	$(call skip,"$(SERVICE_NAME)","no build")

test: lint

lint:
	$(call header,"$(SERVICE_NAME) — lint (kubeconform)")
	@if command -v kubeconform >/dev/null 2>&1; then \
		kubeconform -strict -verbose -summary $(YAML_FILES); \
	else \
		echo "kubeconform not installed — skip."; \
	fi

format:
	$(call skip,"$(SERVICE_NAME)","no formatter")

typecheck:
	$(call skip,"$(SERVICE_NAME)","no type checker")

run:
	$(call skip,"$(SERVICE_NAME)","no server")

deploy:
	$(call skip,"$(SERVICE_NAME)","use kubectl apply -k manually")

clean:
	@echo "Nothing to clean."
