# syntax=docker/dockerfile:1
#
# Frontend image (ADR-001, ADR-004, issue #28). Build context: ./frontend
#
#   docker build -t doctorholiday-frontend frontend \
#     --build-arg VERSION=$(cat VERSION.txt) --build-arg REVISION=$(git rev-parse HEAD)
#
# Stage 1 builds the static SPA with Node, stage 2 serves it with nginx-unprivileged. The runtime
# image contains no Node, no npm and no sources, only nginx and the built files. It runs under
# the Kubernetes security context of the brief (§4c): non-root user, read-only root filesystem,
# no capabilities, port 8080. Base images are pinned by digest; Dependabot proposes updates (#46).

# Base images are written out in each FROM line (tag + digest), not behind ARGs, so Dependabot
# can update them (#46). Resolved on 2026-11-11: node 22.22 (the project needs Node >= 22.13,
# see package.json) and nginx-unprivileged `alpine` (mainline nginx 1.31, ADR-001). The 1.28 stable
# line was rejected: its nginx package has open HIGH/CRITICAL findings without a fix in that repo.

FROM node:22.22-alpine@sha256:e58326d0d441090181ac150dc2078d3e2cf6a0d42e809aebba3ef5880935ffdd AS build
WORKDIR /app
# Layer 1: dependencies from the lockfile. `npm ci` installs exactly package-lock.json (with
# integrity hashes) and fails if package.json and the lockfile disagree. --ignore-scripts: no
# install scripts of third-party packages run during the build.
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts

# Layer 2: sources. `npm run build` type-checks and runs vite build; sourcemaps are off (vite.config.ts).
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e AS runtime
ARG VERSION=0.0.0-dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="doctorholiday-frontend" \
      org.opencontainers.image.description="Doctor Holiday single-page application (React) on nginx" \
      org.opencontainers.image.source="https://github.com/jankrus/doctorholiday" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

# apk upgrade: take the security fixes Alpine published after the pinned base image was built
# (the Trivy gate blocks HIGH and CRITICAL findings, brief §3e). The exact package versions end up
# in the SBOM of every build (#32). Needs root, so the user is set back right after.
USER root
RUN apk upgrade --no-cache

COPY --chown=0:0 nginx.conf /etc/nginx/nginx.conf
COPY --chown=0:0 security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build --chown=0:0 /app/dist /usr/share/nginx/html

# The image's own user (UID 101) is numeric and non-root; set explicitly so it cannot drift.
USER 101:101
EXPOSE 8080

# Start nginx directly: the image's entrypoint scripts try to rewrite files under /etc/nginx,
# which is read-only here. Probes use GET /healthz (#38).
ENTRYPOINT ["nginx", "-g", "daemon off;"]
