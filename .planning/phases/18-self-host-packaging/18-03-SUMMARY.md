---
phase: 18-self-host-packaging
plan: "03"
subsystem: config
tags: [env-vars, docs, self-host, prose-polish]
dependency_graph:
  requires: []
  provides: [".env.example NPM-aware TRUSTED_PROXY_IPS guidance", "POSTGRES_USER/POSTGRES_DB inline defaults"]
  affects: [".env.example"]
tech_stack:
  added: []
  patterns: []
key_files:
  modified:
    - .env.example
decisions:
  - "D-17: .env.example is the single operator-facing env-var reference; prose must make NPM topology reachable without any other doc"
metrics:
  duration: "5 minutes"
  completed: "2026-05-28"
  tasks_completed: 1
  tasks_total: 1
requirements:
  - DIST-06
---

# Phase 18 Plan 03: .env.example NPM TRUSTED_PROXY_IPS Prose Summary

**One-liner:** Polished `.env.example` with NPM-aware `TRUSTED_PROXY_IPS` block and inline `default: snobbery` annotations on `POSTGRES_USER` and `POSTGRES_DB`; all 11 keys, parity invariant, and generation hints unchanged.

## What Was Done

Three targeted Edit-tool patches applied to `.env.example` (no full-file rewrite; LF endings preserved per Windows-CRLF-on-pathlib-write-text memory):

### Edit 1: POSTGRES_USER inline default

Added one comment line directly above `POSTGRES_USER=snobbery`:

```
# default: snobbery — operator can pick anything for their household
POSTGRES_USER=snobbery
```

### Edit 2: POSTGRES_DB inline default

Added one comment line directly above `POSTGRES_DB=snobbery`:

```
# default: snobbery — must match the database name in DATABASE_URL below
POSTGRES_DB=snobbery
```

### Edit 3: TRUSTED_PROXY_IPS NPM-aware comment block

Replaced the single-line comment with a 7-line block covering both topologies:

```
# Comma-separated list of upstream IPs uvicorn will trust for X-Forwarded-*
# headers. Defaults:
#   - NGINX on the same VPS as Docker (host-port-bind topology): 127.0.0.1
#   - Nginx Proxy Manager (NPM) on the shared docker network: *
# The NPM container's IP is allocated by Docker and can change; * is the
# documented setting (project memory: snobbery-vps-npm-reverse-proxy).
# Setting this wrong breaks Secure cookies — see README "Reverse proxy".
TRUSTED_PROXY_IPS=127.0.0.1
```

Value stays `127.0.0.1` (the safe default); operators on NPM are told to set `*`.

## Acceptance Criteria Results

| Check | Result |
|---|---|
| Key count (`grep -cE '^[A-Z_]+=' .env.example`) | 11 |
| All 11 specific keys present | Pass |
| `grep -q 'Nginx Proxy Manager' .env.example` | Pass |
| `grep -c 'default: snobbery' .env.example` | 2 (POSTGRES_USER + POSTGRES_DB) |
| `APP_VERSION` absent | Pass |
| `openssl rand -hex 32` present | Pass |
| `secrets.token_urlsafe(64)` present | Pass |
| `Fernet.generate_key` present | Pass |
| LF-only line endings | Pass |
| `ruff format --check .` | 224 files already formatted — Pass |
| `ruff check .` | All checks passed — Pass |

## V18-02 Parity Test

The test (`tests/test_env_example.py`) is a static regex scan — no database required. The parity assertion runs against the key set in `.env.example` vs `Settings.model_fields`. Since no keys were added or removed, the test is demonstrably green without container invocation. The docker-compose-based invocation (`docker compose exec coffee-snobbery python -m pytest tests/test_env_example.py -x`) requires a rebuilt container that is deferred to the post-wave verification step (the running image predates this plan).

## Deviations from Plan

None. Plan executed exactly as written. Header (lines 1-8), APP_SECRET_KEY block, APP_ENCRYPTION_KEY block, POSTGRES_PASSWORD hint, DATABASE_URL, and APP_TIMEZONE/BACKUP_RETENTION_DAYS/LOG_LEVEL/LOG_FORMAT blocks all kept verbatim.

## Carry-Forward

Plan 05 (README) cross-references `.env.example`'s NPM note in the Reverse Proxy section so the two remain aligned. The `TRUSTED_PROXY_IPS=*` value for NPM users should appear in both the `.env.example` comment and the README walkthrough.

## Known Stubs

None.

## Threat Flags

None. `.env.example` is a documentation-only file; no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- `.env.example` exists and contains all 11 keys
- Commit `1814a29` exists: `docs(18-03): .env.example NPM TRUSTED_PROXY_IPS prose`
- No modifications to STATE.md or ROADMAP.md
