SERVICE_NAME := frontend

include ../../makefiles/common.mk

_HAS_PKG := $(wildcard package.json)
_NPM     := npm

.PHONY: help install build test test-e2e lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(npm/WXT)$(_RST)\n"
	@printf "  install     npm ci\n"
	@printf "  build       wxt build\n"
	@printf "  test        vitest run\n"
	@printf "  test-e2e    playwright e2e\n"
	@printf "  lint        eslint\n"
	@printf "  format      prettier\n"
	@printf "  typecheck   vue-tsc\n"
	@printf "  run         wxt dev server\n"
	@printf "  deploy      build + zip\n"
	@printf "  clean       remove artifacts\n"

install:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — install")
	@if [ -f package-lock.json ]; then $(_NPM) ci; else $(_NPM) install; fi
endif

build:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — build")
	$(_NPM) run build
endif

test:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — test")
	$(_NPM) run test
endif

test-e2e:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — test:e2e")
	$(_NPM) run test:e2e
endif

lint:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — lint")
	@if $(_NPM) run --silent lint 2>/dev/null; then :; else \
		printf "$(_DIM)  ⏭ SKIP $(SERVICE_NAME) — no lint script$(_RST)\n"; \
	fi
endif

format:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — format")
	@if $(_NPM) run --silent format 2>/dev/null; then :; else \
		printf "$(_DIM)  ⏭ SKIP $(SERVICE_NAME) — no format script$(_RST)\n"; \
	fi
endif

typecheck:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — typecheck")
	$(_NPM) run typecheck
endif

run:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — dev")
	$(_NPM) run dev
endif

deploy:
ifndef _HAS_PKG
	$(call skip,"$(SERVICE_NAME)","package.json not found")
else
	$(call header,"$(SERVICE_NAME) — deploy (build + zip)")
	$(_NPM) run build
	$(_NPM) run zip
endif

clean:
	$(call header,"$(SERVICE_NAME) — clean")
	rm -rf node_modules .output dist .wxt/types test-results
