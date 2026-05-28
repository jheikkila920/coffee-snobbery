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
# Also write build_id.txt with a UTC timestamp so the SW CACHE_NAME bumps
# unconditionally on every build, not only when tailwind.src.css changes (C9).
RUN set -eux; \
    HASH="$(sha256sum app/static/css/tailwind.src.css | cut -c1-8)"; \
    tailwindcss \
      -i app/static/css/tailwind.src.css \
      -o "app/static/css/tailwind.${HASH}.css" \
      --minify; \
    echo "Built: app/static/css/tailwind.${HASH}.css"; \
    echo "$(date -u +%Y%m%d%H%M%S)" > app/static/build_id.txt; \
    echo "Build ID: $(cat app/static/build_id.txt)"

# --- Stage 2: Python runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Build-time version stamp (D-12). The release workflow passes
# APP_VERSION=${{ github.ref_name }} (e.g. v1.2.0). Local builds default to
# "dev". Consumed by app/routers/admin/system.py via os.environ["APP_VERSION"].
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

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
    apt-get install -y --no-install-recommends postgresql-client-16 gosu; \
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
COPY --from=tailwind-builder --chown=app:app /build/app/static/build_id.txt ./app/static/build_id.txt

RUN chmod +x entrypoint.sh

# Create the data mountpoints app-owned BEFORE `USER app`. Named volumes seed
# their ownership from the image dir on first mount, so this makes a fresh
# `coffee_snobbery_photos` / `coffee_snobbery_backups` volume writable by the
# non-root app user. Existing root-owned volumes need a one-time
# `docker compose run --rm -u root coffee-snobbery chown -R app:app /app/data`
# (or volume recreation). SCHED-04 backups and Phase 4 photo uploads both
# write here.
RUN mkdir -p /app/data/photos /app/data/backups && chown -R app:app /app/data

# OCI image labels — visible via `docker inspect`. The release workflow's
# docker/metadata-action additionally stamps org.opencontainers.image.{created,
# revision} at build time, which override the static values below. Plan 02
# provides the static fallback for local builds outside CI.
LABEL org.opencontainers.image.title="Snobbery" \
      org.opencontainers.image.description="Self-hosted household coffee log for pour-over enthusiasts" \
      org.opencontainers.image.url="https://github.com/jheikkila54/coffee-snobbery" \
      org.opencontainers.image.source="https://github.com/jheikkila54/coffee-snobbery" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="Proprietary"

EXPOSE 8000

# HEALTHCHECK calls our /healthz endpoint (CONTEXT D-08). The endpoint is
# DB-touching and bounded by a per-transaction 2s statement_timeout, so a
# hanging DB query will still trip this check within the timeout.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["./entrypoint.sh"]

# --- Stage 3: Dev/test — extends runtime with pytest + playwright ------------
#
# Inherits the compiled Tailwind CSS from `runtime` (via COPY --from=tailwind-builder
# above), so the conftest `app` fixture does not skip with "Tailwind CSS missing"
# (RESEARCH.md Pitfall 2). The prod `runtime` stage is untouched — no test tooling
# leaks into production images (CLAUDE.md invariant / T-12-10).
#
# One-command gate: docker compose run --rm coffee-snobbery-test
FROM runtime AS dev

USER root

# Install dev deps (pytest, ruff, mypy, respx, playwright Python bindings, etc.)
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

# Install Chromium browser binary + OS-level deps for bookworm-slim
# (libglib2.0-0, libfontconfig, libx11-6, etc.).
# --with-deps handles all system library requirements automatically.
# PLAYWRIGHT_BROWSERS_PATH is set as an ENV (persists to runtime) so the
# root-time install and the app-user launch resolve the SAME location —
# the default per-user cache (~/.cache) installs under root but the
# container runs as `app`, which would then fail to find the browser.
# chmod a+rx makes the root-installed browser readable by the app user.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium --with-deps \
    && chmod -R a+rx /ms-playwright

USER app

# Override entrypoint for test invocations.
# Full gate: docker compose run --rm coffee-snobbery-test
# E2e only:  docker compose run --rm coffee-snobbery-test tests/e2e/ -rs
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["tests/", "-rs", "--tb=short", "--ignore=tests/e2e"]
