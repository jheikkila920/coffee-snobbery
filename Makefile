# Snobbery — Makefile (Phase 0 / Plan 00-05).
#
# Thin wrapper around `docker compose` for the common developer flows.
# Raw `docker compose` commands still work — this file is convenience over
# correctness (CLAUDE.md "Working with the code"). See CONTEXT D-18 for the
# required target list.
#
# Usage:
#   make up         # bring the stack up in the background
#   make smoke      # full cold-start end-to-end check (phase gate)
#   make logs       # tail the web container logs
#   make revision MSG="add foo column"
#
# Makefiles are TAB-sensitive; recipes below use tabs, not spaces.

.PHONY: help up down logs logs-db psql migrate revision test smoke shell build fmt lint

.DEFAULT_GOAL := help

help:
	@echo "Snobbery — make targets:"
	@echo "  up         Bring the stack up (docker compose up -d)"
	@echo "  down       Stop the stack (docker compose down)"
	@echo "  logs       Tail coffee-snobbery web logs"
	@echo "  logs-db    Tail coffee-snobbery-db logs"
	@echo "  psql       Open a psql shell in the db container"
	@echo "  migrate    Run alembic upgrade head"
	@echo "  revision   Generate a new alembic revision (use: make revision MSG=\"desc\")"
	@echo "  test       Run pytest inside the web container"
	@echo "  smoke      Cold-start end-to-end check (phase gate)"
	@echo "  shell      Open a bash shell in the web container"
	@echo "  build      Rebuild the web image"
	@echo "  fmt        Run ruff format inside the web container"
	@echo "  lint       Run ruff check inside the web container"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f coffee-snobbery

logs-db:
	docker compose logs -f coffee-snobbery-db

# Doubled $$ so make passes a literal $ through to the shell. POSTGRES_USER and
# POSTGRES_DB are read from the db container's own environment (set via
# .env / docker-compose.yml). No need to source .env on the host.
psql:
	docker compose exec coffee-snobbery-db psql -U $$POSTGRES_USER -d $$POSTGRES_DB

migrate:
	docker compose exec coffee-snobbery alembic upgrade head

# Usage: make revision MSG="add foo column"
revision:
	docker compose exec coffee-snobbery alembic revision --autogenerate -m "$$MSG"

test:
	docker compose exec coffee-snobbery pytest -x

shell:
	docker compose exec coffee-snobbery bash

build:
	docker compose build coffee-snobbery

fmt:
	docker compose exec coffee-snobbery ruff format .

lint:
	docker compose exec coffee-snobbery ruff check .

# Smoke — the Phase 0 gating verification (CONTEXT D-18 + planner add).
# Drops volumes so we test from a genuinely clean cold-start, rebuilds,
# waits ~30s for the DB healthcheck + alembic migrations to settle, then
# curls /healthz and asserts the migration head via `alembic current`.
# We assert against `alembic current` rather than a log grep because Alembic
# runs in entrypoint.sh before structlog initializes, so its INFO log line
# `Running upgrade <prev> -> <new>` is silently dropped by stdlib's default
# WARNING level. `alembic current` queries `alembic_version` directly — a
# stronger assertion that's independent of log format or visibility.
# Any sub-command failure exits non-zero (`set -e` + `&&` chaining).
smoke:
	docker compose down -v
	docker compose up -d --build
	@echo "Waiting ~30s for DB healthcheck + migrations to settle..."
	sleep 30
	curl -fsS http://127.0.0.1:8080/healthz
	@echo ""
	# Assert the DB is migrated to the LIVE Alembic head. `alembic current`
	# appends ` (head)` only when the applied revision IS the head, so this
	# marker check is revision-id-agnostic — it never names a revision and so
	# does not need bumping when a new migration lands.
	docker compose exec coffee-snobbery alembic current | grep -E '\(head\)'
	@echo "smoke: OK"
