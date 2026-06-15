# makefiles/python.mk — Shared targets for Python services (Poetry).
# Requires: common.mk included BEFORE this file.
#
# Expected variables (set in child Makefile BEFORE include):
#   SERVICE_NAME  — service display name (e.g. "core-backend")
#   SRC_DIR       — source directory (default: src)
#   TEST_DIR      — test directory (default: tests)
#   COVERAGE_MIN  — minimum coverage threshold (default: 100)
#   DEV_CMD       — dev server command (optional)

SERVICE_NAME ?= $(notdir $(CURDIR))
SRC_DIR      ?= src
TEST_DIR     ?= tests
COVERAGE_MIN ?= 100

_HAS_PYPROJECT := $(wildcard pyproject.toml)

.PHONY: help install build test test-cov lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(Python/Poetry)$(_RST)\n"
	@printf "  install     Install dependencies\n"
	@printf "  build       Build package\n"
	@printf "  test        Run tests\n"
	@printf "  test-cov    Run tests with coverage\n"
	@printf "  lint        Check code (ruff)\n"
	@printf "  format      Format code (ruff)\n"
	@printf "  typecheck   Type check (mypy)\n"
	@printf "  run         Start dev server\n"
	@printf "  deploy      Build Docker image\n"
	@printf "  clean       Remove artifacts\n"

install:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
	$(call header,"$(SERVICE_NAME) — install")
	$(POETRY) install
endif

build:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
	$(call header,"$(SERVICE_NAME) — build")
ifdef BUILD_CMD
	$(BUILD_CMD)
else
	@if [ -f Dockerfile ]; then \
		docker build -t gpe-etna/$(SERVICE_NAME) .; \
	else \
		$(POETRY) check --lock; \
	fi
endif
endif

test:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
	$(call header,"$(SERVICE_NAME) — test")
	$(POETRY) run pytest $(TEST_DIR) -v
endif

test-cov:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
	$(call header,"$(SERVICE_NAME) — test + coverage (min=$(COVERAGE_MIN)%)")
	$(POETRY) run pytest $(TEST_DIR) --cov=$(SRC_DIR) --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)
endif

lint:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
	$(call header,"$(SERVICE_NAME) — lint")
	$(POETRY) run ruff check .
endif

format:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
	$(call header,"$(SERVICE_NAME) — format")
	$(POETRY) run ruff format .
	$(POETRY) run ruff check --fix .
endif

typecheck:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
	$(call header,"$(SERVICE_NAME) — typecheck")
	$(POETRY) run mypy $(SRC_DIR)/
endif

run:
ifndef _HAS_PYPROJECT
	$(call skip,"$(SERVICE_NAME)","pyproject.toml not found")
else
ifdef DEV_CMD
	$(call header,"$(SERVICE_NAME) — dev")
	$(DEV_CMD)
else
	$(call skip,"$(SERVICE_NAME)","DEV_CMD not set")
endif
endif

deploy:
	@if [ -f Dockerfile ]; then \
		printf "\n\033[1m\033[36m══ $(SERVICE_NAME) — deploy\033[0m\n"; \
		docker build -t gpe-etna/$(SERVICE_NAME) .; \
	else \
		printf "\033[2m  ⏭ SKIP $(SERVICE_NAME) — Dockerfile not found\033[0m\n"; \
	fi

clean:
	$(call header,"$(SERVICE_NAME) — clean")
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist .coverage htmlcov __pycache__ .eggs *.egg-info
