---
phase: 12-hardening-tests
plan: "05"
subsystem: infra/test-runtime
tags: [docker, playwright, pytest, ci, d-03]
dependency_graph:
  requires: [12-01]
  provides: [test-runtime-image, compose-test-profile]
  affects: [12-06, 12-07]
tech_stack:
  added: [playwright>=1.59,<2]
  patterns: [multi-stage-dockerfile, docker-compose-profiles]
key_files:
  created: []
  modified:
    - Dockerfile
    - docker-compose.yml
    - requirements-dev.txt
decisions:
  - "FROM runtime AS dev (inherits compiled Tailwind CSS — avoids Pitfall 2 / conftest skip)"
  - "playwright install chromium --with-deps handles bookworm-slim OS-level deps in one command"
  - "Source bind-mount in test service (.:/app) allows test iteration without image rebuild"
  - "No container_name on test service allows parallel docker compose run invocations"
metrics:
  duration: "~12 minutes (Chromium download dominates)"
  completed: "2026-05-23"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 12 Plan 05: Dev/Test Docker Runtime (D-03) Summary

Multi-stage Dockerfile `dev` target + Docker Compose `test` profile closes D-03: a fully reproducible one-command test gate that pins Playwright, bakes in Chromium, and keeps the prod runtime image test-free.

## What Was Built

**requirements-dev.txt** -- Added `playwright>=1.59,<2` pin alongside the existing pytest/ruff/mypy/respx pins.

**Dockerfile** -- Added `FROM runtime AS dev` as Stage 3. Installs `requirements-dev.txt` (pytest, playwright Python bindings, etc.) as root, then runs `playwright install chromium --with-deps` (handles libglib2.0-0, libfontconfig, and other OS libraries that `bookworm-slim` lacks). Switches back to `USER app`. Overrides ENTRYPOINT/CMD to `python -m pytest tests/ -rs --tb=short --ignore=tests/e2e` so `docker compose run --rm coffee-snobbery-test` runs the full non-e2e gate by default. The `runtime` stage is untouched.

**docker-compose.yml** -- Added `coffee-snobbery-test` service under `profiles: [test]`, building from `target: dev`. Sets `SNOB_CI=1` (activates conftest skip-guard), `DATABASE_URL` pointing at `coffee-snobbery-db`, source bind-mount `- .:/app`, and `depends_on: coffee-snobbery-db: condition: service_healthy`. No `container_name`, no `restart`, no `ports`, no photo/backup volumes.

## Verification Results

| Check | Result |
|---|---|
| `docker build --target dev -t coffee-snobbery:dev .` | PASS -- Chromium + all deps installed, image tagged |
| Runtime stage has no pytest/playwright | PASS -- all test tooling only in Stage 3 |
| `docker compose --profile test config` shows coffee-snobbery-test | PASS -- service present with target=dev, SNOB_CI=1 |
| `docker compose config` (no profile) omits coffee-snobbery-test | PASS -- service absent |
| Named volumes unchanged | PASS -- postgres_data/photos/backups untouched |
| Prod service/ports unchanged | PASS -- coffee-snobbery on 127.0.0.1:8080:8000 unchanged |

## Commits

| Task | Commit | Files |
|---|---|---|
| Task 1: Dev/test Dockerfile stage + playwright pin | 68aca2d | Dockerfile, requirements-dev.txt |
| Task 2: Compose test profile | fec0ba5 | docker-compose.yml |

## Deviations from Plan

None -- plan executed exactly as written. ctx7 quota was exceeded so the Playwright `--with-deps` flag was confirmed from training knowledge + PATTERNS.md line 443 (which already documented the correct invocation). The flag name/spelling matched exactly.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The test service shares the existing `coffee-snobbery-net` bridge and only touches a `*_test` sibling database (enforced by conftest + SNOB_CI=1). T-12-10 (prod image stays test-free) and T-12-11 (test container DB isolation) both satisfied.

## Known Stubs

None.

## Self-Check: PASSED

- Dockerfile exists and contains `FROM runtime AS dev`: FOUND
- requirements-dev.txt contains `playwright>=1.59,<2`: FOUND
- docker-compose.yml contains `coffee-snobbery-test` with `profiles: [test]`: FOUND
- Commit 68aca2d exists: FOUND
- Commit fec0ba5 exists: FOUND
