---
phase: 14-audit-remediation
plan: "03"
subsystem: scheduler
tags: [scheduler, sessions, security, apscheduler, b2]
dependency_graph:
  requires: [app/services/scheduler.py, app/models/session.py, app/db.py]
  provides: [nightly_session_sweep job at 03:00 APP_TIMEZONE]
  affects: [sessions table (expired row cleanup)]
tech_stack:
  added: []
  patterns: [lazy-import in job body, SessionLocal() per job run, SCHEDULER_JOB_START/SUCCESS/ERROR logging]
key_files:
  created: []
  modified:
    - app/services/scheduler.py
    - tests/test_scheduler.py
decisions:
  - Lazy-import SessionModel and sql_delete inside job body (mirrors run_nightly_backup pattern, avoids import-cycle risk)
  - Job opens its own SessionLocal() — tests must seed+commit before calling, then query in a fresh session
  - Strict < on expires_at (not <=) avoids deleting just-expiring rows (Pitfall 5)
  - No admin "Sweep now" button (D-06 — deferred; stale sessions are harmless until swept)
metrics:
  duration: ~15m
  completed: 2026-05-25
  tasks_completed: 2
  files_modified: 2
---

# Phase 14 Plan 03: Nightly Session Sweep (B2) Summary

**One-liner:** APScheduler `nightly_session_sweep` job at 03:00 APP_TIMEZONE running `DELETE FROM sessions WHERE expires_at < now()` — closes the deferred `sessions.py:182-185` TODO; 3 idempotent jobs total.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add run_nightly_session_sweep job + register it | a0d755f | app/services/scheduler.py |
| 2 | Update idempotency assertion + author sweep tests | 66b7347 | tests/test_scheduler.py |

## What Was Built

**`app/services/scheduler.py`:**
- Added `run_nightly_session_sweep() -> None` after `run_nightly_backup`. Lazy-imports `sql_delete` from sqlalchemy and `Session as SessionModel` from `app.models.session` inside the body (mirrors the backup pattern, avoids import-cycle risk). Opens `with SessionLocal() as db:`, executes `sql_delete(SessionModel).where(SessionModel.expires_at < func.now())`, commits, logs `SCHEDULER_JOB_SUCCESS`. On any exception: logs `SCHEDULER_JOB_ERROR` with `error_class`/`error_msg` and re-raises.
- Added third `target.add_job(run_nightly_session_sweep, CronTrigger(hour=3, minute=0, timezone=settings.APP_TIMEZONE), id="nightly_session_sweep", replace_existing=True)` in `register_jobs()`. Total: 3 jobs, all idempotent.
- Updated module docstring and `register_jobs` docstring to reflect 3 jobs.

**`tests/test_scheduler.py`:**
- Updated `test_idempotent_job_registration`: `assert len(jobs) == 3` and expected set `{"nightly_ai_refresh", "nightly_backup", "nightly_session_sweep"}`.
- Added `_seed_user_for_sweep(sync_db)` helper that seeds a minimal User row and returns its id as FK target for session rows.
- Added `test_session_sweep_deletes_expired`: seeds one expired session (`expires_at` 1 day past) and one unexpired (`expires_at` 1 day future), commits, calls `run_nightly_session_sweep()`, queries via a fresh `SessionLocal()`, asserts expired row is gone.
- Added `test_session_sweep_retains_unexpired`: seeds one unexpired session, calls sweep, queries fresh, asserts it survived.
- Added `import uuid` and `timedelta` imports at file top.

## Test Results

```
tests/test_scheduler.py: 8 passed, 0 skipped, 0 failed
Full verification suite (scheduler + admin_users + ai_service + search): 89 passed
```

No skips. All new tests exercise real Postgres via `sync_db` fixture.

## Deviations from Plan

None — plan executed exactly as written. The lazy-import pattern, strict `<`, `expires_at` column, and no admin button were all specified; the implementation matches verbatim.

## Implementation Notes

- `func` is already imported at module level (`from sqlalchemy import func, select, text` line 42); no module-level import change needed for the DELETE path.
- `SessionLocal` is already imported at module level (line 46).
- The `expires_at` btree index (migration `p1_sessions`) makes the DELETE an index scan — no table scan on the sessions table.
- The deferred TODO at `sessions.py:182-185` is conceptually closed: sweeping is scheduler-only per D-06.
- Tests use the `sync_db` fixture's commit-then-fresh-session pattern because `run_nightly_session_sweep` opens its own `SessionLocal()` — the fixture's open transaction is invisible to the job.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The job writes only to the `sessions` table (DELETE of expired rows). Covered by the plan's threat model (T-V3-01, T-V3-02).

## Self-Check: PASSED

- `app/services/scheduler.py` exists and contains `def run_nightly_session_sweep(`, `id="nightly_session_sweep"`, `CronTrigger(hour=3, minute=0`, `expires_at < func.now()`.
- `tests/test_scheduler.py` contains `test_session_sweep_deletes_expired`, `test_session_sweep_retains_unexpired`, `assert len(jobs) == 3`.
- Commits a0d755f and 66b7347 confirmed in git log.
- `ruff check` and `ruff format --check` both exit 0 on both files.
- 8/8 scheduler tests pass; 89/89 plan verification suite passes.
