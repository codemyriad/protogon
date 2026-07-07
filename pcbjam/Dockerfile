# Self-contained "pcbjam + Protogon" static site, served by nginx.
#
# Stage 1 downloads prebuilt KiCad WASM + the referenced 3D models and builds the
# @pcbjam/standalone shell (build/build-dist.sh); stage 2 is a tiny nginx image
# serving the finished dist/ with the required cross-origin-isolation headers.
#
# Build context is the REPO ROOT (the board files live there); Dockerfile.dockerignore
# trims it to just what the build needs. Build from the repo root:
#   docker build -f pcbjam/Dockerfile -t ghcr.io/codemyriad/protogon-pcbjam .
#
# Pin overrides (rarely needed) via --build-arg PCBJAM_TAG=... WASM_VER=... MODELS_TAG=...

# ---------- stage 1: build the static site ----------
FROM node:22-bookworm-slim AS builder

ARG PCBJAM_TAG=v0.1.6.2
ARG WASM_VER=v0.1.5
ARG MODELS_TAG=10.0.3

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates jq \
 && rm -rf /var/lib/apt/lists/*
RUN corepack enable

# Board sources the build needs (paths relative to the repo-root context).
WORKDIR /src
COPY codemyriad-protogon.kicad_pcb codemyriad-protogon.kicad_pro ./
COPY JLC2KiCad_lib/footprint/packages3d/ ./JLC2KiCad_lib/footprint/packages3d/

# Build recipe + gallery + nginx config.
COPY pcbjam/build/ /build/

RUN PCBJAM_TAG="${PCBJAM_TAG}" WASM_VER="${WASM_VER}" MODELS_TAG="${MODELS_TAG}" \
    BOARD_SRC=/src BUILD_DIR=/tmp/pcbjam-build OUT_DIR=/out \
    bash /build/build-dist.sh

# ---------- stage 2: serve ----------
FROM nginx:1.27-alpine
COPY pcbjam/build/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /out /usr/share/nginx/html
EXPOSE 8080
