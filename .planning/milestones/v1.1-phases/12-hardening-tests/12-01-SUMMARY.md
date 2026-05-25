---
phase: 12-hardening-tests
plan: "01"
subsystem: test-infrastructure
tags: [test-isolation, ci-gate, conftest, pytest]
dependency_graph:
  requires: []
  provides:
    - tests/conftest.py::_reset_catalog_tables
    - tests/conftest.py::_require_postgres
    - tests/conftest.py::_CI_MODE
  affects:
    - tests/conftest.py (all DB-dependent fixtures)
    - pyproject.toml (addopts)
tech_stack:
  added: []
  patterns:
    - module-scoped TRUNCATE teardown (teardown-only fixture)
    - SNOB_CI skip-to-fail gate via _require_postgres()
key_files:
  modified:
    - tests/conftest.py
    - pyproject.toml
decisions:
  - "Module scope (not function) for _reset_catalog_tables keeps per-test cost near zero while guaranteeing clean catalog state at module boundaries"
  - "_require_postgres() wraps fail-vs-skip logic in one place; all critical-path fixtures delegate to it"
  - "pyproject.toml drops -x so gate run surfaces all failures; -x still available as CLI flag for dev one-shots"
metrics:
  duration: "9m 15s"
  completed: "2026-05-24"
  tasks: 2
  files_modified: 2
---

# Phase 12 Plan 01: Test Infrastructure Isolation Fix Summary

Module-scoped catalog TRUNCATE teardown + SNOB_CI skip-to-fail gate; full pytest suite runs green in two consecutive passes with no FK pollution.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add `_reset_catalog_tables` module-scoped autouse fixture + `_require_postgres` helper to conftest | 2f40505 | tests/conftest.py |
| 2 | Drop `-x` from addopts in pyproject.toml; update critical-path fixtures to use `_require_postgres` | c860303 | pyproject.toml |

## What Was Built

### D-01: Full-Suite Isolation Fix

Added `_reset_catalog_tables` as a `scope="module", autouse=True` pytest fixture in `tests/conftest.py`. It yields first (teardown-only) and on teardown:

1. Returns early if Postgres is unreachable.
2. Replicates the existing safety interlock verbatim — refuses to TRUNCATE any database without "test" in the name.
3. TRUNCATEs catalog and brew tables in FK-safe order: `brew_sessions` → `bags` → `coffees` → `equipment` → `recipes` → `roasters` → `flavor_notes`. Uses `RESTART IDENTITY CASCADE` to reset sequences. Never touches `users` (would CASCADE through `app_settings.updated_by_user_id SET NULL` and wipe the 19-row seed).
4. Clears `app.services.settings._cache` to reset the in-memory `setup_completed` state between modules.

This resolves both isolation gaps from T-INFRA-1:
- The `DELETE FROM coffees RESTRICT FK` error on second consecutive full-suite run (phase_04 test left coffee rows behind).
- `test_setup_concurrent_race` failing in full-suite because the settings cache retained `setup_completed=true` from a prior module.

### D-02: SNOB_CI Skip-Enforcement Gate

Added at the top of `tests/conftest.py`:
- `_CI_MODE = os.environ.get("SNOB_CI") == "1"` — module-level constant.
- `_require_postgres(reason: str)` — calls `pytest.fail(...)` under SNOB_CI=1, `pytest.skip(...)` otherwise.

Updated three critical-path fixtures to route through `_require_postgres`:
- `sync_db` — replaced bare `pytest.skip("Postgres not reachable")` calls.
- `seeded_admin_user` — added Postgres reachability check via `_require_postgres`.
- `seeded_regular_user` — added Postgres reachability check via `_require_postgres`.

`fresh_db` (autouse for all tests including pure-unit tests) was intentionally left with its existing `yield; return` pattern on unreachable Postgres — making it fail under SNOB_CI would break legitimate host-only unit runs that don't need a DB.

### pyproject.toml

Changed `addopts = "-x --tb=short"` to `addopts = "--tb=short"`. The `-x` (stop-at-first-failure) flag hides subsequent failures during the gate run. A comment documents that `-x` is still available as a CLI flag for fast dev one-shots.

## Verification Results

| Check | Result |
|-------|--------|
| Full suite run 1: `pytest tests/ --ignore=tests/e2e -rs -q` | 669 passed, 2 skipped, 10 xfailed |
| Full suite run 2 (consecutive, no DB reset): same command | 669 passed, 2 skipped, 10 xfailed |
| `test_setup_concurrent_race` in full-suite run | PASSED |
| `test_app_settings_seeded_with_19_rows` in full-suite run | PASSED |
| `SNOB_CI=1 pytest tests/ --ignore=tests/e2e -rs -q` | 669 passed, 2 skipped (non-Postgres skips only) |

The 2 remaining skips under SNOB_CI=1 are:
1. `tests/middleware/test_session.py:273` — architectural skip (FK CASCADE prevents the orphaned-session state the test would exercise; schema-bound, not Postgres reachability).
2. `tests/services/test_sessions.py:22` — `db_session` fixture stub for missing `async_session_factory` (deferred to Phase 7 async engine; not a Postgres reachability issue).

Neither is a critical-path Postgres skip — both are correctly left as skips.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. T-12-01 (skip-as-green repudiation) and T-12-02 (destructive teardown vs live DB) both mitigated as planned.

## Self-Check: PASSED

- `tests/conftest.py` — modified and committed at 2f40505
- `pyproject.toml` — modified and committed at c860303
- Both commits verified via `git log --oneline -5`
- Full suite: 669 passed on two consecutive runs
- `test_setup_concurrent_race` and `test_app_settings_seeded_with_19_rows` both pass
- `SNOB_CI=1` run: no unexpected critical-path skips
