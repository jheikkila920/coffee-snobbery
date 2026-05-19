# syntax=docker/dockerfile:1.7
#
# Snobbery — multi-stage Dockerfile (Phase 0 / Plan 00-04).
#
# Stage 1 (tailwind-builder) isolates the Tailwind v4 standalone CLI binary
# (CONTEXT D-04 / D-15). It downloads the binary, compiles
# app/static/css/tailwind.src.css against the templates content-scan path,
# and emits a content-hashed app/static/css/tailwind.<sha8>.css. The runtime
# image carries zero Tailwind tooling — just the compiled output.
#
# Stage 2 (runtime) is python:3.12-slim with postgresql-client-16 installed
# from PGDG (PITFALL SH-5 — slim's default Postgres client is v15 and would
# silently truncate Phase 8 backups against the v16 server). Runs as
# non-root user `app` UID 1000 (CONTEXT D-05). curl is intentionally
# retained after the PGDG install for HEALTHCHECK use (RESEARCH Open
# Question #5).

# --- Stage 1: Tailwind builder -----------------------------------------------
FROM debian:bookworm-slim AS tailwind-builder

# Tailwind v3.4.x: the repo's tailwind.src.css uses v3 directives
# (@tailwind base/components/utilities) and tailwind.config.js is a v3-style
# JS config. The v4 CLI is CSS-first and ignores the JS config, producing a
# near-empty stylesheet — so the CLI must stay on the v3 line.
ARG TAILWIND_VERSION=v3.4.17
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Download the Tailwind standalone CLI binary. Filename pattern is
# tailwindcss-{platform}-{arch}; buildx fills TARGETARCH (amd64/arm64).
# Source: https://tailwindcss.com/blog/standalone-cli + GitHub releases.
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) bin=tailwindcss-linux-x64 ;; \
      arm64) bin=tailwindcss-linux-arm64 ;; \
      *) echo "unsupported arch: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/${bin}" -o /usr/local/bin/tailwindcss; \
    chmod +x /usr/local/bin/tailwindcss

WORKDIR /build
COPY tailwind.config.js ./
COPY app/static/css/tailwind.src.css ./app/static/css/tailwind.src.css
COPY app/templates ./app/templates
# tailwind.config.js content scan includes app/static/js/**/*.js (Alpine
# components build class strings dynamically); copy it so those classes are
# generated rather than silently dropped.
COPY app/static/js ./app/static/js

# Compute SHA-8 of the source CSS and emit the content-hashed output.
RUN set -eux; \
    HASH="$(sha256sum app/static/css/tailwind.src.css | cut -c1-8)"; \
    tailwindcss \
      -i app/static/css/tailwind.src.css \
      -o "app/static/css/tailwind.${HASH}.css" \
      --minify; \
    echo "Built: app/static/css/tailwind.${HASH}.css"

# --- Stage 2: Python runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Install postgresql-client-16 from the PostgreSQL official APT repo so
# pg_dump matches the Postgres 16 server (PITFALL SH-5). Source:
# https://wiki.postgresql.org/wiki/Apt
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release; \
    mkdir -p /etc/apt/keyrings; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-16; \
    # Keep curl (HEALTHCHECK + ad-hoc debugging — RESEARCH Open Question #5).
    apt-get purge -y --auto-remove gnupg lsb-release; \
    rm -rf /var/lib/apt/lists/*

# Non-root app user (CONTEXT D-05; aligns with typical host deploy UID for
# future bind-mount work).
RUN useradd -u 1000 -m -s /bin/bash app

WORKDIR /app

# Install Python deps in a cached layer separate from the source COPY so
# code edits don't invalidate the dep install.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the application code. .dockerignore (Plan 00-01) trims .git,
# .planning, .claude, docs, etc.
COPY --chown=app:app . .

# Copy the Tailwind-compiled CSS produced by Stage 1. The glob picks up
# tailwind.<sha8>.css; the source tailwind.src.css already lives in the
# image via the COPY above.
COPY --from=tailwind-builder --chown=app:app /build/app/static/css/tailwind.*.css ./app/static/css/

RUN chmod +x entrypoint.sh

USER app
EXPOSE 8000

# HEALTHCHECK calls our /healthz endpoint (CONTEXT D-08). The endpoint is
# DB-touching and bounded by a per-transaction 2s statement_timeout, so a
# hanging DB query will still trip this check within the timeout.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["./entrypoint.sh"]
