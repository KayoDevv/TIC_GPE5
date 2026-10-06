# ghcr-image: charon-website:v1.1.8
# Website — static Nuxt landing page whose only job is to hand out the browser
# extension. The extension ZIP is built in the first stage and copied into the
# site's public/ before `nuxt generate`, so the image is self-contained: one
# image = one site + the exact extension build that matches it.
# Build context = monorepo root: make build-website
#
# VITE_API_BASE_URL is inlined by Vite at build time (see
# apps/frontend/src/p0/settings.ts) — it is NOT a runtime setting. Rebuild the
# image to point the extension at another backend.

FROM node:22-alpine AS extension

# GPE-NYX is the only target, so the node address is the default rather than a
# thing CI must remember to pass. `:-` (not an ARG default) so an empty
# --build-arg — what an unset CHARON_API_BASE_URL expands to — still lands here
# instead of silently baking localhost into the ZIP.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL:-http://172.16.249.133:30080}

WORKDIR /build/apps/frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run zip \
    && find .output -name '*-chrome.zip' -exec cp {} /charon-extension.zip \; \
    && test -s /charon-extension.zip

FROM node:22-alpine AS site

WORKDIR /build
COPY apps/website/package.json apps/website/package-lock.json ./
# postinstall (`nuxt prepare`) is deferred until app/ is in place: run against a
# bare package.json it types the auto-imports from the wrong srcDir, and the
# vue-tsc pass inside `nuxt generate` then fails on every composable.
RUN npm ci --ignore-scripts
COPY apps/website/ ./
COPY --from=extension /charon-extension.zip public/charon-extension.zip
RUN npm run postinstall && npm run generate

FROM nginxinc/nginx-unprivileged:1.29-alpine

# A version bump busts this layer so apk runs against a fresh index. The base
# image already dropped to the nginx user, so patching needs root back briefly.
ARG IMAGE_VERSION=dev
USER root
RUN echo "base packages for ${IMAGE_VERSION}" \
    && apk upgrade --no-cache
USER 101

COPY apps/website/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=site /build/.output/public /usr/share/nginx/html

EXPOSE 8080
