SERVICE_NAME := kafka-schemas

include ../../makefiles/common.mk

SCHEMA_FILES := $(wildcard *.json)

.PHONY: help install build test lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(JSON Schema)$(_RST)\n"
	@printf "  test/lint   JSON syntax validation\n"

install:
	@echo "Nothing to install (static JSON)."

build:
	$(call skip,"$(SERVICE_NAME)","no build (JSON schemas)")

test: lint

lint:
	$(call header,"$(SERVICE_NAME) — lint (JSON syntax)")
	@fail=0; for f in $(SCHEMA_FILES); do \
		if python3 -m json.tool "$$f" >/dev/null 2>&1; then \
			printf "$(_GRN)  ✓ $$f$(_RST)\n"; \
		else \
			printf "$(_RED)  ✗ $$f — invalid JSON$(_RST)\n"; \
			fail=1; \
		fi; \
	done; \
	[ "$$fail" = "0" ] || exit 1

format:
	$(call skip,"$(SERVICE_NAME)","no formatter")

typecheck:
	$(call skip,"$(SERVICE_NAME)","no type checker")

run:
	$(call skip,"$(SERVICE_NAME)","no server")

deploy:
	$(call skip,"$(SERVICE_NAME)","no deployment (schemas registered via kafka-init)")

clean:
	@echo "Nothing to clean."
