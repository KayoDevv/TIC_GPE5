# makefiles/common.mk — Shared variables and functions for the CHARON monorepo.
# Included first in every child Makefile.

# ── Monorepo root detection ──────────────────────────────────────────────────
ROOT_DIR := $(shell d="$(CURDIR)"; while [ "$$d" != "/" ]; do \
	[ -f "$$d/docker-compose.yml" ] && echo "$$d" && break; \
	d=$$(dirname "$$d"); done)

# ── Tools ─────────────────────────────────────────────────────────────────────
DOCKER_COMPOSE := $(shell command -v docker-compose 2>/dev/null || echo "docker compose")
POETRY         := $(shell command -v poetry 2>/dev/null || echo "poetry")

# ── ANSI colors ───────────────────────────────────────────────────────────────
_RST  := \033[0m
_BOLD := \033[1m
_DIM  := \033[2m
_CYN  := \033[36m
_YLW  := \033[33m
_GRN  := \033[32m
_RED  := \033[31m

# ── Display macros ────────────────────────────────────────────────────────────
define header
	@printf "\n$(_BOLD)$(_CYN)══ %s$(_RST)\n" $(1)
endef

define section
	@printf "$(_BOLD)$(_YLW)── %s$(_RST)\n" $(1)
endef

define ok
	@printf "$(_GRN)  ✓ %s$(_RST)\n" $(1)
endef

define warn
	@printf "$(_YLW)  ⚠ %s$(_RST)\n" $(1)
endef

define err
	@printf "$(_RED)  ✗ %s$(_RST)\n" $(1)
endef

define skip
	@printf "$(_DIM)  ⏭ SKIP %s — %s$(_RST)\n" $(1) $(2)
endef
