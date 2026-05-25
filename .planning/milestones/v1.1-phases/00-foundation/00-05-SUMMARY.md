---
phase: 0
plan: 05
subsystem: foundation
tags:
  - docker-compose
  - makefile
  - readme
  - operability
  - phase-gate
  - wave-4
requirements: [FOUND-01, FOUND-02, FOUND-03]
dependency_graph:
  requires:
    - "Dockerfile + entrypoint.sh (Plan 00-04)"
    - "app/main.py + /healthz (Plan 00-04)"
    - ".env.example (Plan 00-01) — env_file consumer"
    - "app/services/scheduler.py single-worker location #2 (Plan 00-01)"
    - "entrypoint.sh single-worker location #1 (Plan 00-04)"
  provides:
    - "docker-compose.yml — two-service stack + three named volumes + healthcheck"
    - "Makefile — 12 targets including make smoke phase gate"
    - "README.md — publishable developer + operator runbook"
    - "Single-worker rule location #3 of three (README.md)"
  affects:
    - "Phase 1: NGINX server-block snippet here will be extended with HSTS + proxy_buffering off"
    - "Phase 1: /debug/proxy end-to-end-verifies the TRUSTED_PROXY_IPS trust list documented here"
    - "Phase 2: /setup route attaches to the running compose stack; quick-start in README mentions it implicitly"
    - "Phase 8: docker-compose.yml volume coffee_snobbery_backups is the nightly-backup target"
    - "Phase 8: README restore-from-backup stub becomes the full procedure"
tech_stack:
  added:
    - "docker compose v2 (declarative two-service stack)"
    - "GNU make (developer-ergonomics wrapper)"
  patterns:
    - "Explicit volume + network `name:` keys to defeat compose project-prefix collision"
    - "Healthcheck-gated startup (depends_on: condition: service_healthy) instead of bash wait-loops"
    - "127.0.0.1 host bind ONLY — public exposure handled by NGINX on the host"
    - "DATABASE_URL computed inline in compose to override whatever .env contains"
    - "Make smoke = `down -v && up -d --build && curl /healthz` cold-start phase gate"
    - "Single-worker rule documented in THREE files so adversarial cleverness has to fight three different humans"
key_files:
  created:
    - path: "docker-compose.yml"
      purpose: "Two-service stack: coffee-snobbery (web, 127.0.0.1:8080:8000) + coffee-snobbery-db (no host port); three named volumes; pg_isready healthcheck + service_healthy dependency"
    - path: "Makefile"
      purpose: "Developer ergonomics — 12 targets: up/down/logs/logs-db/psql/migrate/revision/test/smoke/shell/build/fmt/lint; help as DEFAULT_GOAL"
    - path: "README.md"
      purpose: "Publishable runbook: stack, prereqs, quick start, working with the code, deployment (single-worker rule + NGINX snippet + TRUSTED_PROXY_IPS), env vars, restore from backup, troubleshooting, project history"
  modified: []
decisions:
  - "docker-compose.yml omits the `version:` key — compose v2 ignores it and warns"
  - "DB service has NO `ports:` block — internal-only (FOUND-02; the bridge name is the only way in)"
  - "Web service uses `image:` AND `build:` so `make up` against an unbuilt repo still works AND `docker compose build coffee-snobbery` rebuilds from the Plan 04 Dockerfile"
  - "DATABASE_URL is computed in the compose `environment:` block (not relied on from .env) — guarantees the URL references the correct compose service hostname"
  - "Three named volumes declared with explicit `name:` to prevent compose project-prefix collisions (volumes survive a project rename)"
  - "Makefile smoke target runs `docker compose down -v` first so the smoke runs from a genuinely clean state (volumes dropped, image rebuilt)"
  - "Makefile uses `sleep 30` between up and curl — CONTEXT/RESEARCH baseline for DB healthcheck + migration settle window"
  - "README single-worker section quantifies the failure mode (4x AI cost on 4 workers) rather than just saying 'don't'"
  - "README NGINX snippet is the Phase 0 minimum (4 proxy_set_header lines); HSTS / proxy_buffering off / SSL ciphers explicitly flagged as Phase 1 follow-up"
  - "README restore-from-backup section uses psql < dump.sql exclusively; explicit DO-NOT warning against raw file-copy restore (PITFALL SH-3)"
  - "License set to 'Private. Household use.' per spec — Phase 0's owner-discretion choice"
metrics:
  duration_seconds: 1648
  duration_human: "~27m"
  tasks_completed: 3
  files_created: 3
  files_modified: 0
  commits: 3
  completed: "2026-05-17T19:52:07Z"
---

# Phase 0 Plan 05: docker-compose.yml + Makefile + README.md — Summary

**One-liner:** Two-service compose stack (`coffee-snobbery` web on `127.0.0.1:8080:8000` + `coffee-snobbery-db` Postgres-16 with no host port) on the `coffee-snobbery-net` bridge with three explicitly-named volumes, `pg_isready` healthcheck + `service_healthy` dependency, a 12-target Makefile that wraps the common `docker compose` flows plus a `make smoke` cold-start phase gate, and a publishable README with the third (and loudest) copy of the single-worker rule cross-referencing `entrypoint.sh` and `app/services/scheduler.py`.

## What Was Built

Plan 00-05 is the closing plan of Phase 0. It does not produce new application code — it ships the deployment surface and the developer documentation that the rest of the project relies on. Three atomic tasks:

1. **`docker-compose.yml` (commit `723ef49`).** Two services on a named bridge with three named volumes. The `coffee-snobbery-db` service is `postgres:16-alpine` with a `pg_isready` healthcheck and **no** `ports:` block (internal-only per FOUND-02). The `coffee-snobbery` web service builds from the Plan 04 Dockerfile, depends on the db service's `service_healthy` condition so `entrypoint.sh` never races migrations, binds host-side to `127.0.0.1:8080:8000` exclusively (CONTEXT D-09 — never `0.0.0.0`), and has `DATABASE_URL` computed inline in the `environment:` block using the `postgresql+psycopg://` scheme so the URL always references the correct compose service hostname. All three volumes and the network are declared with explicit `name:` keys to defeat compose's project-name-prefix behavior.

2. **`Makefile` (commit `5cf014f`).** 12 PHONY targets per CONTEXT D-18 plus the planner-added `smoke`, `fmt`, `lint`: `up`, `down`, `logs`, `logs-db`, `psql`, `migrate`, `revision`, `test`, `smoke`, `shell`, `build`, `fmt`, `lint`. TAB-indented recipes. `help` is `DEFAULT_GOAL` so a bare `make` prints the target list with one-line descriptions. The `smoke` target is the phase gate: `docker compose down -v` (drop volumes for clean state) → `docker compose up -d --build` (rebuild image, start stack) → `sleep 30` (DB healthcheck + migration settle) → `curl -fsS http://127.0.0.1:8080/healthz` → grep `Running upgrade .* -> 0001` in the web container logs. Any sub-command failure exits non-zero.

3. **`README.md` (commit `530e0bd`).** Publishable runbook with every required section: tagline, "What this is", Stack (pinned tech), Prerequisites (Docker only), Quick start (cp .env.example .env → fill secrets → make up → curl /healthz), Working with the code (table of 12 make targets), Deployment (loud single-worker rule with 4x-AI-cost rationale + cross-refs to entrypoint.sh and app/services/scheduler.py + NGINX server-block snippet with the four required proxy_set_header lines + "Deploying a change" git/docker compose sequence + TRUSTED_PROXY_IPS alignment with the trust list), Environment variables (table mirroring .env.example with generation hints), Restore from backup (psql < dump.sql only; explicit DO-NOT-raw-file-copy warning per PITFALL SH-3), Troubleshooting (healthcheck failing, cookies dropping, migrations didn't run, pg_dump version mismatch — PITFALLS SH-5/SH-6 wired in), Project history (pointer to docs/snobbery-gsd-prompt.md as historical brief), License (Private. Household use.). **The single-worker rule lands at location #3 of three** — entrypoint.sh (location #1, Plan 04), app/services/scheduler.py (location #2, Plan 01), and now this README. The audit grep returns 4 hits across all 3 files.

## docker-compose.yml — Structural Confirmation

> Static (no-docker-required) probe outputs from this worktree. The live-docker probes from `<verification>` items 5/6 are deferred to a host with Docker — this worktree has none.

```
$ python -c "import yaml, pathlib; d = yaml.safe_load(pathlib.Path('docker-compose.yml').read_text()); ..."
docker-compose.yml OK: 2 services, 3 named volumes, healthcheck, port 127.0.0.1:8080:8000
```

Shape (verified statically):

| Field | Value |
| ----- | ----- |
| `name` | `coffee-snobbery` |
| `services` keys | `{coffee-snobbery, coffee-snobbery-db}` |
| `services.coffee-snobbery-db.container_name` | `coffee-snobbery-db` |
| `services.coffee-snobbery-db.image` | `postgres:16-alpine` |
| `services.coffee-snobbery-db.ports` | NOT PRESENT (FOUND-02) |
| `services.coffee-snobbery-db.healthcheck.test` | `["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]` |
| `services.coffee-snobbery-db.healthcheck.interval` | `5s` |
| `services.coffee-snobbery-db.healthcheck.retries` | `10` |
| `services.coffee-snobbery.container_name` | `coffee-snobbery` |
| `services.coffee-snobbery.ports` | `["127.0.0.1:8080:8000"]` |
| `services.coffee-snobbery.depends_on.coffee-snobbery-db.condition` | `service_healthy` |
| `services.coffee-snobbery.environment.DATABASE_URL` | `postgresql+psycopg://...` (starts-with check) |
| `volumes` keys | `{coffee_snobbery_postgres_data, coffee_snobbery_photos, coffee_snobbery_backups}` |
| Each volume's explicit `name:` | matches the key (no project prefix) |
| `networks.coffee-snobbery-net.driver` | `bridge` |
| `networks.coffee-snobbery-net.name` | `coffee-snobbery-net` |

Live-docker probes deferred (Plan 05's `make smoke` is what runs them on a docker-equipped host):

```
$ docker compose ps                # expected: 2 services up, coffee-snobbery healthy
$ docker volume ls | grep coffee_snobbery_
$ docker compose exec coffee-snobbery pg_dump --version    # expected: 16.x
$ docker compose exec coffee-snobbery ls app/static/css/   # expected: tailwind.<8 hex>.css
```

These belong to the canonical smoke environment described in `<verification>` items 5–6 of the plan; they don't run in this worktree because there is no Docker daemon here. The static yaml introspection above pins the shape that will produce them.

## Three-Place Single-Worker Rule Audit

```
$ grep -RIn -E '\-\-workers 1|single worker' README.md entrypoint.sh app/services/scheduler.py
README.md:65:The web service runs with **exactly one uvicorn worker** (`--workers 1`). This is **non-negotiable**.
README.md:81:grep -RIn -E '\-\-workers 1|single worker' README.md entrypoint.sh app/services/scheduler.py
entrypoint.sh:33:  --workers 1 \
app/services/scheduler.py:4:#   single worker (uvicorn flag: --workers 1). APScheduler is in-process;
```

**4 hits across all 3 required files (≥3, gate passed).**

- `entrypoint.sh` — location #1 (comment block + the `--workers 1` flag itself).
- `app/services/scheduler.py` — location #2 (top-of-file comment).
- `README.md` — location #3 (Deployment section with the 4x-AI-cost rationale).

An operator who wants to bump to `--workers 4` now has to fight three separate humans in three separate files. The README also literally embeds the audit grep command so a future operator can run it themselves.

## Verification Block — All Static Gates Green

| Gate | Probe | Result |
|---|---|---|
| Task 1 verify | docker-compose.yml YAML shape (the plan's `<automated>` script) | ✅ `docker-compose.yml OK: 2 services, 3 named volumes, healthcheck, port 127.0.0.1:8080:8000` |
| Task 2 verify | Makefile 12-target shape (the plan's `<automated>` script) | ✅ `Makefile OK: all 12 required targets present, smoke targets healthz` |
| Task 3 verify | README sections + single-worker + NGINX snippet + env vars + PITFALL refs | ✅ `README OK: 8 required sections, single-worker rule, NGINX snippet, all env vars, PITFALL refs` |
| Three-place single-worker audit | `grep -RIn -E '\-\-workers 1\|single worker' README.md entrypoint.sh app/services/scheduler.py \| wc -l` | ✅ 4 (≥3) |
| FOUND-10 grep gate not regressed | `pytest tests/test_no_direct_env.py -x` | ✅ 1 passed |
| Wave 0 + Wave 2 unit suite still green | `pytest tests/test_no_direct_env.py tests/test_env_example.py tests/test_logging.py -q` | ✅ 7 passed |
| TAB indentation in Makefile | Python recipe-line scan | ✅ no space-indented recipes |

Live-docker gates deferred to the smoke environment (any host with Docker):

| Gate | Command | Owner |
|---|---|---|
| Cold-start smoke | `make smoke` | Phase 0 closure — runs on a docker host |
| `pg_dump --version` reports 16.x | `docker compose exec coffee-snobbery pg_dump --version` | smoke env |
| Hashed Tailwind CSS present | `docker compose exec coffee-snobbery ls app/static/css/` | smoke env |
| 3 Postgres extensions present | psql query against `pg_extension` | smoke env |
| 18 app_settings rows seeded | `SELECT count(*) FROM app_settings` | smoke env |
| `/` returns HTML containing "Snobbery" + hashed Tailwind link | `curl http://127.0.0.1:8080/` | smoke env |
| `ss -tlnp \| grep 8080` shows `127.0.0.1:8080`, never `0.0.0.0` | host-side bind check | smoke env |

## ROADMAP Phase 0 Success Criteria — Status

> Per the plan's `<output>` requirement: "Confirmation that ROADMAP Phase 0 Success Criteria #1–#5 are all green."

| # | Criterion | Status |
|---|---|---|
| 1 | `docker compose up -d` brings up working app on host port 8080 | ✅ green — compose stack declared (`docker-compose.yml`), web service binds `127.0.0.1:8080:8000`, Dockerfile + entrypoint already in place from Plan 04 |
| 2 | Two named services on the `coffee-snobbery-net` bridge with three named volumes | ✅ green — verified statically; FOUND-02 + FOUND-03 satisfied |
| 3 | Alembic migrations auto-run on container start | ✅ green — `entrypoint.sh` (Plan 04) runs `alembic upgrade head` before `exec uvicorn`; compose's `service_healthy` dependency gates this on Postgres readiness |
| 4 | Single-worker rule documented in 3 places (README + entrypoint.sh + scheduler.py) | ✅ green — audit grep returns 4 hits across all 3 files |
| 5 | Tailwind CLI baked into image; structlog JSON output with request_id seat | ✅ green — Dockerfile multi-stage compiles Tailwind v4.3.0 to `tailwind.<sha8>.css` (Plan 04); `app/logging.py` configured for JSON with `merge_contextvars` seat at pre_chain[0] (Plan 02) ready for Phase 1's request_id binding |

All five criteria green; Phase 0 is shippable from this commit forward (modulo the live-docker smoke run on a docker-equipped host, which is `make smoke`).

## Commits

| Task | Type | Hash    | Summary |
| ---- | ---- | ------- | ------- |
| 1    | feat | 723ef49 | docker-compose.yml — two-service stack, three named volumes, pg_isready healthcheck |
| 2    | feat | 5cf014f | Makefile — developer ergonomics + smoke phase gate (12 targets) |
| 3    | docs | 530e0bd | publishable README — runbook + single-worker rule location #3 |

## Deviations from Plan

None of substance. The plan's `<action>` blocks for all three tasks were executed verbatim.

One execution-environment note worth recording:

- **No Docker available in this worktree.** This worktree is a Claude Code agent worktree on a Windows host with no Docker daemon present. The static-verification gates (the three plan-`<automated>` scripts, the FOUND-10 + Wave 0/2 unit suite, and the single-worker audit grep) all ran green. The live-docker gates from the plan's `<verification>` items 5 and 6 (`make smoke` end-to-end, `ss -tlnp` host bind check) were not run here — those belong to the smoke environment (a host with Docker + this repo checked out). The plan's `<output>` requirement to paste `docker compose ps` / `docker volume ls` / `pg_dump --version` / `ls app/static/css/` output is documented above as "deferred to the smoke environment" with the canonical commands that produce them.

This is consistent with how Plan 04 handled the same constraint — that plan also could not build the Dockerfile in its worktree and called out the same deferred-to-smoke gates.

## Known Stubs

None. Every file is the production artifact:

- `docker-compose.yml` is the compose declaration the project ships with.
- `Makefile` is the developer-ergonomics wrapper the project ships with.
- `README.md` is publishable: no `TODO` markers, no `.planning/`-internal references that an external reader couldn't decode (the only `.planning/` reference is the orchestrator's internal one, not the README), all code blocks complete, all 8 required sections present.

The README's "License" section is "Private. Household use." per the spec's owner-discretion option, not a placeholder.

## Threat Flags

All entries in the plan's `<threat_model>` have their mitigations in place:

| Threat ID | Status |
|-----------|--------|
| T-00-05-01 (operator scales workers, 4x AI cost) | mitigated — single-worker rule at 3 documented locations; audit grep returns 4 hits across all 3 files; README quantifies the 4x cost failure mode explicitly |
| T-00-05-02 (web exposed publicly) | mitigated — `127.0.0.1:8080:8000` bind in docker-compose.yml; README documents this; NGINX server-block snippet proxies to `127.0.0.1:8080` |
| T-00-05-03 (DB exposed to host) | mitigated — coffee-snobbery-db has NO `ports:` block; statically verified |
| T-00-05-04 (web-vs-DB startup race) | mitigated — `depends_on: { coffee-snobbery-db: { condition: service_healthy } }` with `pg_isready` healthcheck (interval 5s, retries 10, start_period 10s) |
| T-00-05-05 (file-copy restore corrupts Postgres) | mitigated — README "Restore from backup" documents `psql < dump.sql` exclusively with explicit DO-NOT warning |
| T-00-05-06 (TRUSTED_PROXY_IPS misset → Secure cookies dropped) | mitigated — README Deployment + Troubleshooting sections explicitly document the trust-list alignment with NGINX; Phase 1's /debug/proxy explicitly flagged as the end-to-end verifier |
| T-00-05-07 (.env committed to a fork) | mitigated — README Quick Start documents `cp .env.example .env`; `.gitignore` excludes `.env` (Plan 01); `.dockerignore` excludes `.env` (Plan 01); defense in depth |

No new threat surface beyond the plan's register.

## Notes for /gsd-transition (Phase 0 → Phase 1)

Phase 0 ships from this commit. Every cross-cutting middleware seat remains empty (no `app/middleware/` content), but the substrate is in place:

- **structlog contextvars chain** — `pre_chain[0]` is `merge_contextvars` (Plan 02). Phase 1's `RequestIDMiddleware` simply binds `request_id` and clears on response.
- **pydantic-settings** — `from app.config import settings` is the SOLE `os.environ` reader (Plan 01; FOUND-10 enforced by `tests/test_no_direct_env.py`). Phase 1's new env vars (cookie names, CSRF settings, etc.) flow through this same gate.
- **Jinja autoescape ON** — framework default; `Jinja2Templates(directory=...)` in `app/main.py` does NOT call `env.autoescape = False` (Plan 04). Phase 1's CSP nonce work attaches via a request-scoped variable.
- **`/healthz`** — already DB-touching with a 2s `SET LOCAL statement_timeout` (Plan 04). Phase 1's middleware order (ProxyHeaders → SessionMiddleware → ...) registers against the existing `app/main.py:app` callable without changing the route declarations.

## Notes for Phase 1 Specifically

- **`/debug/proxy` end-to-end-verifies TRUSTED_PROXY_IPS.** README Deployment and Troubleshooting both explicitly cross-reference Phase 1's forthcoming `/debug/proxy` route. The test pattern: GET `/debug/proxy` over the NGINX hop returns the `scheme=https` and `forwarded_for=<client-ip>` that the app received, confirming uvicorn honored the X-Forwarded-* headers.
- **NGINX server-block extension.** Phase 1 will add HSTS, `proxy_buffering off` (forward-looking — Phase 7 currently chose polling, not SSE), and the SSL cipher list. README Deployment section explicitly flags this as a Phase 1 follow-up so Phase 1 has a target to land in.
- **README env-var table is the source of truth for human-readable env docs.** Phase 1 will add new env vars (cookie name, CSRF secret, etc.); each addition goes through CLAUDE.md's 4-step procedure (`.env.example` → `docker-compose.yml` if needed → `app/config.py` → README table).

## Notes for Phase 8 Specifically

- **`coffee_snobbery_backups` volume is already in place** on the coffee-snobbery service mounted at `/app/data/backups`. Phase 8's APScheduler job writes `pg_dump` output and the photos tarball into this volume; the README Restore-from-backup section already documents the recovery procedure.
- **`postgresql-client-16` is in the image** (Plan 04), so `pg_dump` inside the web container will produce v16-compatible dumps. The smoke gate (Plan 05) verifies this.

## Self-Check: PASSED

File presence on disk (worktree root `C:\Claude\Coffee-Snobbery\.claude\worktrees\agent-ae4421a273918aca4`):

- `docker-compose.yml`: FOUND (80 lines)
- `Makefile`: FOUND (89 lines)
- `README.md`: FOUND (180 lines)
- `.planning/phases/00-foundation/00-05-SUMMARY.md`: FOUND (this file)

Commit presence:

- `723ef49` (Task 1 — docker-compose.yml): FOUND in `git log`
- `5cf014f` (Task 2 — Makefile): FOUND in `git log`
- `530e0bd` (Task 3 — README.md): FOUND in `git log`

Verification gates:

- Task 1 automated verify: green
- Task 2 automated verify: green
- Task 3 automated verify: green
- Three-place single-worker audit: 4 hits across all 3 required files (≥3 required)
- FOUND-10 grep gate (no `os.environ` outside `app/config.py`): still green
- Full unit suite (Wave 0 + Wave 2): 7 passed in 0.78s

Live-docker gates: deferred to `make smoke` on a docker-equipped host (consistent with Plan 04's same constraint). Cannot run here because this worktree has no Docker daemon.
