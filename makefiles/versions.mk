# Derived from the Dockerfile `# ghcr-image:` headers by `make sync-versions`.
# Edit the headers, not this file.

OWNER ?= kayodevv

AGENT_VERSION    ?= v1.2.0
PDF_VERSION      ?= v1.2.1
CONSUMER_VERSION ?= v1.1.1
BACKEND_VERSION  ?= v1.0.1
ML_VERSION       ?= v1.0.1
VERDICT_VERSION  ?= v1.0.1
LLM_VERSION      ?= v1.0.1
SINKHOLE_VERSION ?= v1.0.1
WEBSITE_VERSION  ?= v1.1.0

AGENT_IMAGE    := ghcr.io/$(OWNER)/ubuntu-sandbox:$(AGENT_VERSION)
PDF_IMAGE      := ghcr.io/$(OWNER)/ubuntu-pdf-sandbox:$(PDF_VERSION)
CONSUMER_IMAGE := ghcr.io/$(OWNER)/charon-sandbox-consumer:$(CONSUMER_VERSION)
BACKEND_IMAGE  := ghcr.io/$(OWNER)/charon-core-backend:$(BACKEND_VERSION)
ML_IMAGE       := ghcr.io/$(OWNER)/charon-ml-layer:$(ML_VERSION)
VERDICT_IMAGE  := ghcr.io/$(OWNER)/charon-verdict-layer:$(VERDICT_VERSION)
LLM_IMAGE      := ghcr.io/$(OWNER)/charon-llm-layer:$(LLM_VERSION)
SINKHOLE_IMAGE := ghcr.io/$(OWNER)/inetsim-sinkhole:$(SINKHOLE_VERSION)
WEBSITE_IMAGE  := ghcr.io/$(OWNER)/charon-website:$(WEBSITE_VERSION)
