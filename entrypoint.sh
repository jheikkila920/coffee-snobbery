#!/usr/bin/env bash
# Snobbery container entrypoint (Phase 0 / Plan 00-04).
#
# IMPORTANT: This service MUST run with exactly one uvicorn worker. APScheduler
# (Phase 8) is in-process and module-level AI locks (Phase 7) require single-process.
# A future `--workers 4` would fire every nightly job 4x and bill 4x the AI cost.
# This is reinforced in README.md and app/services/scheduler.py.
#
# This file is location #1 of three places that loudly state the single-worker
# rule. The other two are:
#   (2) app/services/scheduler.py — top-of-file comment block.
#   (3) README.md — deployment section (lands in Plan 00-05).
#
# Anyone trying to add `--workers 4` trips over this note three times before
# they succeed. If you remove or weaken this comment, restore one of the other
# two locations to compensate so the count of warnings stays at three.

set -euo pipefail

# 1) Run migrations. Idempotent (CREATE EXTENSION IF NOT EXISTS;
#    CREATE TABLE against an empty schema). Compose's
#    `depends_on: coffee-snobbery-db: condition: service_healthy`
#    (Plan 00-05) gates this on Postgres being ready.
alembic upgrade head

# 2) Launch uvicorn behind the proxy-headers trust list (FOUND-04 / FOUND-08;
#    PITFALL SH-6). The ${TRUSTED_PROXY_IPS:-127.0.0.1} fallback handles a
#    missing env var gracefully — the var is mandatory in .env.example but
#    we keep a defensive default for local development.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"
