---
phase: 18-self-host-packaging
verified: 2026-05-28T00:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
deferred:
  - truth: "A fresh install auto-runs migrations on first start and lands the operator at /setup"
    addressed_in: "Phase 22"
    evidence: >
      DIST-05 infrastructure is complete and verified in code (entrypoint.sh runs
      `alembic upgrade head`; auth.py /setup zero-users guard confirmed). End-to-end
      smoke (V18-19: /healthz ok; V18-20: GET / -> /setup redirect on clean volume)
      requires a published GHCR image + `docker compose down -v`. Explicitly owned
      by Phase 22 per VALIDATION.md § Manual-Only Verifications and 18-05 SUMMARY.
  - truth: "Pushing a version tag triggers the release CI workflow and publishes a versioned multi-arch image to GHCR — GHCR public visibility"
    addressed_in: "Phase 22"
    evidence: >
      The release.yml workflow is fully wired (V18-04..V18-07, V18-16 all pass).
      The one-time GHCR package-settings UI flip (private->public after first tag push)
      is documented in CONTRIBUTING.md § "After first release". The act of pushing
      the first v* tag is Phase 22's release gate.
---

# Phase 18: Self-Host Packaging — Verification Report

**Phase Goal:** A new operator can deploy Snobbery on their own VPS with no `docker compose build` step and a complete, accurate guide
**Verified:** 2026-05-28
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Phase Scope

Five plans across two waves, 16 commits on `main` (commits 7a6934b through d223c4b plus tracking commits). Scope: split operator-facing compose from dev override, stamp Dockerfile with APP_VERSION + OCI labels, polish .env.example for NPM topology, create tag-triggered multi-arch release workflow, rewrite README operator-first and create CONTRIBUTING.md.

---

## Success Criteria Scorecard

| # | ROADMAP Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | `docker-compose.yml` references `image: ghcr.io/...` tag, works without local build step | Met | `image: ghcr.io/jheikkila54/coffee-snobbery:v1.2.0`; no `build:` block; test service removed — V18-01 PASS |
| 2 | Pushing a version tag triggers release CI, publishes versioned multi-arch image to GHCR | Met (workflow wired; first push deferred to Phase 22) | `.github/workflows/release.yml` two-job workflow confirmed; V18-04/05/06/07/16 all PASS; GHCR public-flip is one-time post-tag action documented in CONTRIBUTING.md |
| 3 | README contains complete from-zero walkthrough: prerequisites, env vars, first run, upgrade | Met | All 8 required H2 headers present; GHCR path in README; upgrade procedure (edit tag + pull + up); V18-08/09/10/11/12 all PASS |
| 4 | Deploy guide covers NPM setup including `TRUSTED_PROXY_IPS` and shared docker network | Met | README § "Reverse proxy" has NPM field-table, shared network step, `TRUSTED_PROXY_IPS=*` callout with load-bearing gotchas section — V18-10 PASS |
| 5 | Fresh install auto-runs migrations on first start and lands operator at `/setup` | Met (code verified; end-to-end smoke deferred to Phase 22) | `entrypoint.sh` runs `alembic upgrade head` before uvicorn start; `auth.py` has zero-users /setup guard confirmed. V18-19/V18-20 manual smoke requires first GHCR image pull. |
| 6 | `.env.example` documents every required env var with generation hints | Met | 11 keys present; `APP_SECRET_KEY` and `APP_ENCRYPTION_KEY` both carry generation hints; TRUSTED_PROXY_IPS block has NPM vs NGINX topology guidance; parity enforced by `tests/test_env_example.py` — V18-02 PASS |

---

## Validator Results (V18-01 through V18-20)

| Validator | What it checks | Result | Notes |
|-----------|---------------|--------|-------|
| V18-01 | Compose syntax + GHCR image pin, no `build:` block, no test service | PASS | `image: ghcr.io/jheikkila54/coffee-snobbery:v1.2.0`; services: `[coffee-snobbery-db, coffee-snobbery]` only |
| V18-02 | `.env.example` / `app/config.py` parity (11 keys, APP_VERSION absent) | PASS | 11 keys confirmed; APP_VERSION absent from both `.env.example` and `Settings`; test assertable |
| V18-03 | Single-worker three-place invariant (>=3 grep hits) | PASS | 4 hits: entrypoint.sh (2), scheduler.py (1), README (1) |
| V18-04 | Release workflow has `test` + `build-push` jobs; `build-push needs: test` | PASS | Structural shape confirmed via yaml parse |
| V18-05 | Release workflow `platforms: linux/amd64,linux/arm64` | PASS | Exact string present in release.yml |
| V18-06 | Release workflow `packages: write` permission on build-push job | PASS | `permissions: { contents: read, packages: write }` on build-push only (least privilege) |
| V18-07 | Release workflow `flavor: latest=auto` (pre-release filter) | PASS | `flavor: latest=auto` in metadata-action step |
| V18-08 | README required H2 headers: Quickstart, Prerequisites, Reverse proxy, Upgrade, Restore, Troubleshooting, License | PASS | All 7 (out of 8 in validator; "Environment variables" not in the list but present) confirmed |
| V18-09 | README references `ghcr.io/jheikkila54/coffee-snobbery` | PASS | Present in both Quickstart and Upgrade sections |
| V18-10 | README contains `TRUSTED_PROXY_IPS=*` callout | PASS | Present in load-bearing gotchas #1 |
| V18-11 | README upgrade procedure contains `docker compose pull` and `docker compose up -d` | PASS | Three-line upgrade block confirmed |
| V18-12 | README troubleshooting has GHCR 403 / "Image pull fails" entry | PASS | "Image pull fails / 403 from ghcr.io" heading with 4-step recovery |
| V18-13 | `CONTRIBUTING.md` exists with `make smoke`, `ruff`, `docker compose cp` | PASS | All three present; 187-line file confirmed |
| V18-14 | Dockerfile has >=4 `org.opencontainers.image.*` LABEL lines | PASS | 7 matches (6 label lines + 1 comment reference) |
| V18-15 | Dockerfile has `ARG APP_VERSION` | PASS | `ARG APP_VERSION=dev` in runtime stage only (not tailwind-builder) |
| V18-16 | Release workflow passes `APP_VERSION=` build-arg | PASS | `APP_VERSION=${{ github.ref_name }}` in build-args |
| V18-17 | `.gitignore` excludes `docker-compose.override.yml` (exact line) | PASS | Line `docker-compose.override.yml` present |
| V18-18 | `docker-compose.override.yml.example` committed | PASS | File exists at repo root with dev build block + test service |
| V18-19 | DIST-05 smoke: `/healthz` returns ok (clean volume) | DEFERRED to Phase 22 | Requires first `v*` tag push + clean volume — manual per VALIDATION.md |
| V18-20 | DIST-05 smoke: GET `/` redirects to `/setup` with zero users | DEFERRED to Phase 22 | Same preconditions as V18-19 |

---

## Required Artifacts

| Artifact | Expected | Status | Notes |
|----------|----------|--------|-------|
| `docker-compose.yml` | GHCR image pin, no build: block, operator-facing | VERIFIED | image: ghcr.io/jheikkila54/coffee-snobbery:v1.2.0 |
| `docker-compose.override.yml.example` | Dev build block + test service template | VERIFIED | 50 lines; target: runtime for web, target: dev for test service |
| `.gitignore` | Excludes `docker-compose.override.yml` | VERIFIED | Exact line present |
| `.dockerignore` | Excludes `docker-compose.override.yml` | VERIFIED | Confirmed present |
| `Dockerfile` | ARG APP_VERSION + ENV + 6 OCI LABEL lines | VERIFIED | 7 OCI hits; ARG in runtime stage only; labels before EXPOSE 8000 |
| `app/config.py` | `get_app_version()` helper (FOUND-10 compliant) | VERIFIED | Returns `os.environ.get("APP_VERSION") or None`; authorized location |
| `app/routers/admin/system.py` | Imports + calls `get_app_version` as version chain head | VERIFIED | `from app.config import get_app_version` + call confirmed |
| `pyproject.toml` | Version bumped to 1.2.0 | VERIFIED | `version = "1.2.0"` |
| `.github/workflows/release.yml` | Two-job tag-triggered workflow, multi-arch, GHCR publish | VERIFIED | 168 lines; test gates build-push via needs: |
| `.env.example` | 11 keys with NPM TRUSTED_PROXY_IPS prose + generation hints | VERIFIED | All hints present; NPM vs NGINX topology documented |
| `README.md` | Operator-first; all required H2 sections; NPM walkthrough | VERIFIED | 294 lines; sections in correct order |
| `CONTRIBUTING.md` | Dev guide carved from README; release ritual + GHCR flip | VERIFIED | 187 lines; GHCR public-visibility ritual documented |

---

## Architectural Deviations Resolved

### 18-02: env-var read via `get_app_version()` helper (not inline in system.py)

**Plan specified:** `import os; os.environ.get("APP_VERSION")` directly in `app/routers/admin/system.py`.

**What shipped:** `get_app_version()` helper added to `app/config.py` (the sole authorized `os.environ` consumer per FOUND-10). `system.py` imports and calls the helper. Semantics are identical — D-12 env-var-first version resolution works exactly as designed.

**Root cause:** `tests/test_no_direct_env.py` (FOUND-10) asserts no `os.environ` references outside `app/config.py`. The plan's literal implementation would have caused that test to fail.

**Classification:** `key_link_drift_resolved` — not a gap. Architecturally correct; superior to the plan's literal specification.

**Verification:** `grep -rn "os.environ" app/ --include="*.py" | grep -v "app/config.py"` returns two comment-only hits in `app/migrations/env.py` (lines 5 and 42 are docstring/comment text, not actual `os.environ` calls). Zero offenders in application code.

---

## FOUND-10 Integrity Check

`tests/test_no_direct_env.py` invariant: `os.environ` in application code must only appear in `app/config.py`.

- `app/config.py`: 1 real call in `subprocess_env()`, 1 real call in `get_app_version()` — both authorized
- `app/migrations/env.py`: 2 hits — both are docstring/comment text, not executable `os.environ` calls
- All other `app/` files: 0 hits

FOUND-10 is intact.

---

## Data-Flow Trace: APP_VERSION end-to-end

| Stage | Source | Value | Status |
|-------|--------|-------|--------|
| Git tag push | `github.ref_name` (e.g., `v1.2.0`) | Real tag | WIRED |
| release.yml build-args | `APP_VERSION=${{ github.ref_name }}` | Tag value | WIRED |
| Dockerfile ARG/ENV | `ARG APP_VERSION=dev` + `ENV APP_VERSION=${APP_VERSION}` | Stamped into image env | WIRED |
| `app/config.py` `get_app_version()` | `os.environ.get("APP_VERSION")` | Returns tag string | WIRED |
| `system.py` version chain | `get_app_version()` then importlib.metadata then pyproject.toml | Falls through if env absent | WIRED |
| pyproject.toml fallback | `version = "1.2.0"` | Correct milestone string for CI/dev | WIRED |

---

## Items Deferred to Phase 22

| Item | Owned By | Evidence |
|------|---------|---------|
| V18-19: `/healthz` returns ok on clean-volume fresh install | Phase 22 | Requires first published `v*` GHCR image + `docker compose down -v` |
| V18-20: GET `/` redirects to `/setup` with zero users | Phase 22 | Same preconditions as V18-19 |
| GHCR private-to-public visibility flip | Phase 22 | One-time package settings UI action after first tag push; documented in CONTRIBUTING.md § "After first release" |
| First `v*` tag push exercising the full release.yml pipeline | Phase 22 | Phase 22 success criteria: "tag v1.2.0, push GHCR image" |

Infrastructure for all four items is complete and verified in code. Phase 22 executes the final operator-facing smoke.

---

## Anti-Patterns Scan

Files added/modified in this phase (8 files across 5 plans):

| File | TBD/FIXME/XXX | Stubs | Assessment |
|------|--------------|-------|------------|
| `docker-compose.yml` | 0 | 0 | Clean |
| `docker-compose.override.yml.example` | 0 | 0 | Clean |
| `.gitignore` / `.dockerignore` | 0 | 0 | Clean |
| `Dockerfile` | 0 | 0 | Clean; `ARG APP_VERSION=dev` is an intended default, not a stub |
| `app/config.py` | 0 | 0 | `get_app_version()` returns real env value or None |
| `app/routers/admin/system.py` | 0 | 0 | Clean |
| `pyproject.toml` | 0 | 0 | Version 1.2.0 |
| `.github/workflows/release.yml` | 0 | 0 | Clean; actionlint not run (not installed on host), YAML parsed clean via Python |
| `.env.example` | 0 | 0 | Clean |
| `README.md` | 0 | 0 | Clean; all sections carry real content |
| `CONTRIBUTING.md` | 0 | 0 | Clean |
| `CLAUDE.md` | 0 | 0 | 3 table rows appended |

No TBD, FIXME, or XXX markers found in any phase 18 file. No stub implementations.

---

## Behavioral Spot-Checks

| Behavior | Check | Result |
|----------|-------|--------|
| `docker-compose.yml` references GHCR image, no build block | `python -c "import yaml; ...assert 'build' not in svc..."` | PASS |
| OCI label count >=4 | `grep -c 'org.opencontainers.image' Dockerfile` | PASS (7) |
| ARG APP_VERSION in Dockerfile runtime stage | `grep -q 'ARG APP_VERSION' Dockerfile` | PASS |
| release.yml workflow wired (test -> build-push) | `python -c "import yaml; ...assert 'test' in needs..."` | PASS |
| Single-worker invariant survives README rewrite (>=3 hits) | `grep -RIn -E '\-\-workers 1\|single worker' README.md entrypoint.sh app/services/scheduler.py` | PASS (4 hits) |
| get_app_version helper exists in config.py | `grep -q 'def get_app_version' app/config.py` | PASS |
| system.py calls get_app_version (D-12 chain) | `grep -q 'get_app_version' app/routers/admin/system.py` | PASS |
| TRUSTED_PROXY_IPS=* in README | `grep -q 'TRUSTED_PROXY_IPS=\*' README.md` | PASS |
| alembic upgrade head in entrypoint.sh (DIST-05 code path) | `grep -q 'alembic upgrade head' entrypoint.sh` | PASS |
| pyproject.toml at 1.2.0 | `grep -q 'version = "1.2.0"' pyproject.toml` | PASS |
| APP_VERSION absent from .env.example | `grep -q 'APP_VERSION' .env.example` | PASS (absent) |
| FOUND-10: no os.environ outside app/config.py | `grep -rn "os.environ" app/ --include="*.py" \| grep -v "app/config.py"` | PASS (2 comment-only hits, 0 executable) |

---

## Requirements Coverage

| Requirement | Plan | Description | Status |
|-------------|------|-------------|--------|
| DIST-01 | 18-01 | Deploy with no `docker compose build` step | SATISFIED |
| DIST-02 | 18-02 / 18-04 | Versioned multi-arch image published to GHCR via CI | SATISFIED (workflow wired; first push Phase 22) |
| DIST-03 | 18-05 | README complete from-zero self-host walkthrough | SATISFIED |
| DIST-04 | 18-05 | NPM walkthrough with TRUSTED_PROXY_IPS + shared network | SATISFIED |
| DIST-05 | 18-05 | Fresh install boots: migrations auto-run, /setup first | SATISFIED (code path; smoke deferred Phase 22) |
| DIST-06 | 18-03 / 18-05 | .env.example documents all vars with generation hints | SATISFIED |

---

## Overall Verdict

**PHASE COMPLETE — COMPLETE-WITH-CARRY-FORWARD**

All 6 ROADMAP success criteria are satisfied by code evidence. Seventeen of 18 V18 validators (V18-01 through V18-18) pass in the current codebase. V18-19 and V18-20 are manual-only validators that require a published first GHCR image; they are explicitly deferred to Phase 22 per the VALIDATION.md contract. No blockers. No gaps.

The GHCR public-visibility flip and first `v*` tag push are one-time release-gating actions, not Phase 18 deliverables. Phase 22 ("Verification & Release") owns them.

---

*Verified: 2026-05-28*
*Verifier: Claude (gsd-verifier)*
