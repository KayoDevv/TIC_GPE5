SERVICE_NAME := terraform

include ../../makefiles/common.mk

.PHONY: help install build test lint format typecheck run deploy clean

help:
	@printf "$(_BOLD)$(_CYN)$(SERVICE_NAME)$(_RST) $(_DIM)(Terraform)$(_RST)\n"
	@printf "  lint        terraform fmt -check\n"
	@printf "  format      terraform fmt\n"
	@printf "  test        terraform validate\n"

install:
	@echo "Terraform is a system binary (see make install-helm)."

build:
	$(call skip,"$(SERVICE_NAME)","no build")

test: validate

lint:
	$(call header,"$(SERVICE_NAME) — lint (fmt -check)")
	terraform fmt -check -recursive .

format:
	$(call header,"$(SERVICE_NAME) — format")
	terraform fmt -recursive .

typecheck:
	$(call skip,"$(SERVICE_NAME)","no type checker")

.PHONY: validate
validate:
	$(call header,"$(SERVICE_NAME) — validate")
	terraform init -backend=false
	terraform validate

run:
	$(call skip,"$(SERVICE_NAME)","no server")

deploy:
	$(call skip,"$(SERVICE_NAME)","use terraform apply manually")

clean:
	$(call header,"$(SERVICE_NAME) — clean")
	rm -rf .terraform .terraform.lock.hcl
