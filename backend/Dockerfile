# syntax=docker/dockerfile:1
#
# Backend image (ADR-001, ADR-002, issue #28). Build context: ./backend
#
#   docker build -t doctorholiday-backend backend \
#     --build-arg VERSION=$(cat VERSION.txt) --build-arg REVISION=$(git rev-parse HEAD)
#
# Runs under the Kubernetes security context of the brief (§4c): numeric non-root user, read-only
# root filesystem (the app writes nothing, /tmp stays available), no capabilities needed, port 8080.
# Base images are pinned by digest; Dependabot proposes updates (#46).

# Base images are written out in each FROM line (tag + digest), not behind ARGs, so Dependabot
# can update them (#46). python:3.12-alpine and uv 0.12.24 were resolved on 2026-11-11.
# uv: backend/pyproject.toml requires >=0.12.23,<0.13; only its binary is copied.
# The interpreter of the runtime stage is the same image as in the build stage, so the venv's
# symlinks stay valid.
FROM ghcr.io/astral-sh/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a AS uv

FROM python:3.12-alpine@sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7 AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
# Interpreter comes from the base image, never from a uv download (ADR-002).
# --no-build: install hash-locked wheels only, never compile or run build scripts of sdists.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_BUILD=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Layer 1: third-party dependencies from the lockfile (changes rarely, cached).
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-install-project

# Layer 2: the application itself (not editable, so the runtime stage needs only the venv).
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-alpine@sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7 AS runtime
ARG VERSION=0.0.0-dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="doctorholiday-backend" \
      org.opencontainers.image.description="Doctor Holiday REST API (FastAPI)" \
      org.opencontainers.image.source="https://github.com/jankrus/doctorholiday" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

# apk upgrade: take the security fixes Alpine published after the pinned base image was built
# (the Trivy gate blocks HIGH and CRITICAL findings, brief §3e). The exact package versions end up
# in the SBOM of every build (#32). Then a fixed numeric UID/GID, so `runAsUser: 10001` in
# Kubernetes matches the image, with no home directory and no login shell. pip, setuptools and
# wheel are removed: the app is installed into the venv, they would only widen the scan surface.
RUN apk upgrade --no-cache \
    && addgroup -g 10001 app \
    && adduser -D -H -u 10001 -G app -s /sbin/nologin app \
    && python -m pip uninstall -y pip setuptools wheel \
    && rm -rf /root/.cache

COPY --from=build --chown=0:0 /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random

USER 10001:10001
WORKDIR /tmp
EXPOSE 8080

# No HEALTHCHECK: Kubernetes probes /healthz and /readyz (#38). Configuration only from env (#30).
ENTRYPOINT ["python", "-m", "doctorholiday"]
