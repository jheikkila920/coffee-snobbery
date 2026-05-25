---
phase: 12-hardening-tests
plan: "07"
subsystem: ci-docs
tags: [ci, github-actions, readme, tailwind, postgresql, d-04, d-08]
dependency_graph:
  requires: [12-01, 12-02, 12-05]
  provides: [D-04-ci-gate, D-08-readme-gap-fill]
  affects: [all-tests-via-ci, vps-deploy-docs]
tech_stack:
  added: [github-actions-ci]
  patterns: [postgres-service-container, tailwind-ci-build, snob-ci-gate]
key_files:
  created:
    - .github/workflows/ci.yml
  modified:
    - README.md
decisions:
  - "Replicate Dockerfile stage 1 Tailwind build in CI (download tailwindcss v3.4.17 binary + sha256-hash scheme) rather than building the full Docker image — keeps CI fast and honest without hollow skips"
  - "Place G-01 chown note as a subsection under Deploying a change (not a Troubleshooting entry) since it is a one-time setup step, not a recurring failure mode"
  - "Place iOS Wake Lock caveat in a new ## Known caveats section rather than Troubleshooting — it is a platform limitation, not an operational failure"
metrics:
  duration: "~18 minutes"
  completed: "2026-05-24T01:27:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 2
---

# Phase 12 Plan 07: CI Workflow and README Gap-Fill Summary

GitHub Actions CI gate (D-04) and targeted README gap-fill (D-08). The CI workflow runs ruff + full pytest against Postgres 16 on every push/PR; the README gains the iOS Wake Lock caveat and G-01 chown deploy note.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | GitHub Actions CI workflow (D-04) | 1963cfc | .github/workflows/ci.yml (created) |
| 2 | README gap-fill (D-08) | fd43399 | README.md (modified) |

## What Was Built

### Task 1: CI Workflow (D-04)

`.github/workflows/ci.yml` — triggers on push and pull_request. One job (`test`) on `ubuntu-latest`:

- `postgres:16-alpine` service container with `pg_isready` healthcheck (5s interval, 10 retries), port 5432:5432
- `actions/checkout@v4` + `actions/setup-python@v5` (Python 3.12, pip cache)
- `pip install -r requirements-dev.txt` (installs ruff, pytest, playwright, etc.)
- Tailwind CSS build step: downloads tailwindcss v3.4.17 Linux x64 binary, computes `sha256sum app/static/css/tailwind.src.css | cut -c1-8` as HASH, emits `tailwind.${HASH}.css --minify` — mirrors Dockerfile stage 1 exactly
- `ruff format --check .` then `ruff check .` (lint-first, fail fast)
- `python -m pytest tests/ -rs --tb=short --ignore=tests/e2e` with `SNOB_CI=1`, `DATABASE_URL=postgresql+psycopg://test:test@localhost:5432/snobbery` (conftest rewrites to `snobbery_test` automatically — no explicit migration step needed)
- `APP_SECRET_KEY` / `APP_ENCRYPTION_KEY` from GitHub secrets with non-production fallback literals
- No Playwright browser install; no e2e tests; no deploy/build-push step

**Tailwind CI build rationale:** `app/main.py:compute_tailwind_css_path()` raises `RuntimeError` if no hashed CSS exists; conftest catches this as `pytest.skip`. Without the build step, ~⅓ of the suite would skip silently, defeating `SNOB_CI=1`. Replicating the Dockerfile hash scheme (sha256sum + cut -c1-8) is the exact approach used by the image builder and produces the same filename the app discovers at startup.

### Task 2: README Gap-Fill (D-08)

Two surgical additions only — no tested prose rewritten:

**iOS Wake-Lock caveat** (new `## Known caveats` section, before `## Project history`): documents that Guided Brew Mode requests the Wake Lock API, that iOS Safari has incomplete support, and that the app falls back to a silent-audio-loop technique. Notes that the lock is re-acquired on `visibilitychange → visible` and that a visible indicator shows status. Wording lifted from Phase 11 CONTEXT.md D-11.

**G-01 chown deploy note** (new `#### One-time: fix root-owned volumes...` subsection under `### Deploying a change`): documents the one-time `docker compose run --rm -u root coffee-snobbery chown -R app:app /app/data` command needed for pre-existing VPS volumes that predate the Phase 8 Dockerfile fix. Fresh deploys are explicitly called out as unaffected.

**Confirmed present (not modified):**
- `### Single uvicorn worker — DO NOT change` (line 63) — present
- `## Restore from backup` with `psql < dump.sql` + photos tar commands — present
- NGINX server-block with `Strict-Transport-Security`, `max-age=63072000`, `proxy_set_header X-Forwarded-Proto $scheme`, `proxy_buffering off` — all present

**README doc tests:** `tests/docs/test_readme_nginx.py` (3 tests) and `tests/test_env_example.py` (1 test) both pass after the edits.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Model Coverage

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-12-15 | `SNOB_CI=1` in pytest step — unexpected skips fail the build |
| T-12-16 | `APP_SECRET_KEY` / `APP_ENCRYPTION_KEY` from GitHub secrets; non-production fallbacks are throwaway literals, no production secret in ci.yml |
| T-12-17 | D-08 chown + wake-lock notes added to README |

## Known Stubs

None — all additions are complete documentation of real implemented behavior.

## Self-Check

Files created/modified:
- [x] `.github/workflows/ci.yml` exists — verified by YAML parse
- [x] `README.md` modified — verified by content checks

Commits:
- [x] 1963cfc exists (feat: CI workflow)
- [x] fd43399 exists (docs: README gap-fill)

## Self-Check: PASSED
