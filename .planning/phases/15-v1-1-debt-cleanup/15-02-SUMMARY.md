---
phase: 15-v1-1-debt-cleanup
plan: "02"
subsystem: test-infra
tags: [test-isolation, ci, debt-cleanup, DEBT-02]
dependency_graph:
  requires: []
  provides: [T-INFRA-1-closed, double-run-green, ci-double-run-guard]
  affects: [tests/routers/test_auth.py, .github/workflows/ci.yml]
tech_stack:
  added: []
  patterns: [in-test-cache-clear-guard, ci-double-run-isolation-gate]
key_files:
  created: []
  modified:
    - tests/routers/test_auth.py
    - .github/workflows/ci.yml
decisions:
  - "D-05 honored: conftest fixtures untouched (git diff tests/conftest.py is empty)"
  - "D-06 honored: root-cause fix via cache clear, no skip/xfail/quarantine on test_setup_concurrent_race"
  - "D-07 honored: CI double-run reuses the same Postgres service with no drop/recreate between runs"
metrics:
  duration: "10 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_changed: 2
---

# Phase 15 Plan 02: Test Isolation Fix (DEBT-02) Summary

**One-liner:** In-test `_svc_mod._cache.clear()` guard fixes `test_setup_concurrent_race` deterministically; CI double-run step locks the isolation against regression.

## What Was Built

Closed T-INFRA-1 (DEBT-02) via two minimal changes:

1. **`tests/routers/test_auth.py`** -- Added a single `_svc_mod._cache.clear()` guard inside `test_setup_concurrent_race`, immediately after `_require_auth_router()` and before the primer GET. Wrapped in `try/except` so import failure is safe. Uses alias `_svc_mod` to avoid shadowing. Mirrors the existing `_reset_catalog_tables` teardown pattern in `conftest.py` exactly.

2. **`.github/workflows/ci.yml`** -- Appended `Pytest isolation double-run` step immediately after `Pytest full suite`. Same `env:` block verbatim (same `DATABASE_URL`, `POSTGRES_*`, `APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `SNOB_CI: "1"`). Same `run:` command. No DB drop/recreate between runs -- the second run reuses the existing Postgres service, so teardown residue from run 1 surfaces as failures in run 2.

## Task Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1: Fix test_setup_concurrent_race | `cb7082e` | fix(15-02): add in-test settings cache clear to test_setup_concurrent_race |
| Task 2: Add CI double-run step | `677818e` | chore(15-02): add Pytest isolation double-run step to CI |
| Task 3: Double-run proof | (no commit -- proof-only) | Full suite green twice in a row against same DB |

## Double-Run Proof (T-INFRA-1 Evidence)

Full suite run against `coffee-snobbery-test` (baked image, rebuilt with Task 1 fix):

**Run 1:**
```
999 passed, 2 skipped, 10 xfailed, 159 warnings in 130.82s (0:02:10)
```
Exit 0.

**Run 2 (same DB, no drop/recreate immediately after Run 1):**
```
999 passed, 2 skipped, 10 xfailed, 159 warnings in 120.79s (0:02:00)
```
Exit 0.

`test_setup_concurrent_race` confirmed PASSED (not skipped) in both runs. It is not in the `-rs` SKIPPED summary for either run.

**The 2 legitimate skips (both runs):**
- `tests/middleware/test_session.py:261` -- FK CASCADE prevents orphaned-session state in normal operation; structural skip with a clear comment about when to convert it.
- `tests/services/test_sessions.py:22` -- `db_session` fixture requires async engine (Phase 7 async engine prerequisite); structural skip.

Neither skip is related to `test_setup_concurrent_race`. Both are pre-existing and documented.

## Root Cause Summary

`test_setup_blocked_after_completion` updates `setup_completed='true'` via raw `engine.begin()`, bypassing `set_setting()`, so `_svc._cache` is not invalidated. When `test_setup_concurrent_race` runs next in the same module, the `async_client` fixture's lifespan `prewarm_cache` can read the stale `true` from `_cache`, causing both concurrent POSTs to see `setup_completed=true` and redirect to `/login` -- wrong result `['/login', '/login']` instead of `['/', '/login']`.

The fix: clear `_svc._cache` before the `async_client` fixture triggers `prewarm_cache`. The `fresh_db` autouse already resets the DB value to `false`; the cache clear ensures the prewarm reads the reset DB value, not the stale cache entry.

## Decision Compliance

| Decision | Status |
|----------|--------|
| D-05 (prove-and-lock; no conftest fixture rewrite) | Honored -- `git diff tests/conftest.py` is empty |
| D-06 (root-cause fix; no skip/xfail/quarantine) | Honored -- no skip/xfail markers added to `test_setup_concurrent_race` |
| D-07 (green twice against same DB + CI double-run guard) | Honored -- both runs exit 0; CI step added without DB drop/recreate |

## Deviations from Plan

None. Plan executed exactly as written. All three tasks completed. The `.env` file was not present in the worktree (gitignored), so it was temporarily copied from the main repo for the Docker test run -- not committed.

## Known Stubs

None.

## Threat Flags

None. This plan touches only test code and CI config -- no production code, no auth/session/crypto/input-validation surface. The existing `"test" not in _active_db.lower()` guard in `conftest.py` is preserved unchanged (D-05).

## Self-Check: PASSED

- `tests/routers/test_auth.py` modified and contains `_cache.clear()` inside `test_setup_concurrent_race`: confirmed
- `.github/workflows/ci.yml` modified and contains `Pytest isolation double-run` step: confirmed
- Commit `cb7082e` exists: confirmed
- Commit `677818e` exists: confirmed
- `tests/conftest.py` unchanged: `git diff tests/conftest.py` is empty
- `ruff format --check tests/routers/test_auth.py` and `ruff check tests/routers/test_auth.py`: both exit 0
- Double-run proof: 999 passed, 2 skipped, 10 xfailed in both runs (exit 0 both times)
- `test_setup_concurrent_race` PASSED (not skipped) in both runs
