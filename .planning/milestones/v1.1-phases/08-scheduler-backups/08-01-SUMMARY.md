---
phase: 08-scheduler-backups
plan: "01"
subsystem: scheduler-foundation
tags: [events, testing, wave-0, conftest, scaffolding]
dependency_graph:
  requires: []
  provides:
    - app.events.SCHEDULER_AI_RUN_COMPLETE
    - app.events.BACKUP_COMPLETE
    - tests.conftest.sync_db
    - tests.conftest.mock_regenerate
    - tests.test_scheduler (6 named stubs)
    - tests.test_backup (3 named stubs)
  affects:
    - Plans 08-02/08-03 (consume the test harnesses and event constants)
    - Phase 9 (admin panel reads event constants from structlog)
tech_stack:
  added: []
  patterns:
    - xfail(strict=False) Wave 0 stubs with import-guard skips
    - AsyncMock fixture factory with force=False cost-control assertion
    - sync_db fixture mirroring fresh_db safety interlock (T-08-01)
key_files:
  created:
    - tests/test_scheduler.py
    - tests/test_backup.py
  modified:
    - app/events.py
    - tests/conftest.py
decisions:
  - "Wave 0 stubs use pytest.skip (via ImportError guard) rather than xfail for symbols not yet defined; xfail for code paths that exist but are incomplete — keeps collection clean with zero false passes"
  - "mock_regenerate returns a factory (not a pre-applied mock) so each test can specify its own per-user status map"
  - "sync_db fixture reuses _postgres_reachable() + 'test' in db_name interlock verbatim from fresh_db — no new safety logic needed"
metrics:
  duration_minutes: 6
  completed_date: "2026-05-21"
  tasks_completed: 3
  files_modified: 4
---

# Phase 08 Plan 01: Scheduler + Backup Foundation Summary

Wave 0 scaffolding for Phase 8: event taxonomy, test harnesses, and conftest fixtures that Plans 08-02 and 08-03 build against.

## What Was Built

**app/events.py** — 11 new structured-event constants in two blocks following the existing ai.* pattern:
- `scheduler.*` (6): SCHEDULER_STARTED, SCHEDULER_SHUTDOWN, SCHEDULER_JOB_START, SCHEDULER_JOB_SUCCESS, SCHEDULER_JOB_ERROR, SCHEDULER_AI_RUN_COMPLETE
- `backup.*` (5): BACKUP_STARTED, BACKUP_COMPLETE, BACKUP_ARTIFACT_OK, BACKUP_ARTIFACT_ERROR, BACKUP_PRUNED
- All 11 added to `__all__` in alphabetical order; each block includes per-event field-shape comments

**tests/conftest.py** — Two new Phase 8 fixtures:
- `sync_db`: yields a sync `SessionLocal` session with `_postgres_reachable()` + non-test-DB interlock (T-08-01)
- `mock_regenerate`: factory fixture returning an `AsyncMock` for `ai_service.regenerate`; asserts `force=False` on every call (SCHED-02 cost-control guard)

**tests/test_scheduler.py** — 6 named Wave 0 stubs (SCHED-01/02/03):
- `test_idempotent_job_registration` — exactly 2 jobs after N register_jobs() calls
- `test_lifespan_scheduler_lifecycle` — scheduler starts/stops in lifespan cleanly
- `test_eligibility_filter` — is_active=True AND >=3 sessions
- `test_ai_run_summary_tally` — regenerate() statuses tallied; force=False asserted (async)
- `test_token_aggregation` — this-run rows only; web-search split
- `test_status_row_write` — last_ai_run_status written as JSON string

**tests/test_backup.py** — 3 named Wave 0 stubs (SCHED-04):
- `test_retention_prune` — filename-date prune deletes right files
- `test_partial_failure_keeps_good` — one artifact fails; other kept; overall status=error
- `test_backup_status_row_write` — last_backup_status written as JSON string

## Test Results

```
9 tests collected
8 skipped (ImportError guard — app.services.scheduler/backup not yet implemented)
1 xfailed (test_ai_run_summary_tally — awaits mock then hits pytest.fail)
0 errors
0 false passes
```

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | d21e72e | feat(08-01): add scheduler.* and backup.* event taxonomy |
| 2 | 4413c53 | feat(08-01): add sync_db and mock_regenerate fixtures |
| 3 | 61e498e | test(08-01): add Wave 0 xfail stubs for SCHED-01/02/03/04 |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan is itself a stub plan. The test stubs are intentional Wave 0 scaffolding; Plans 08-02 and 08-03 implement the actual behavior and remove the xfail/skip markers.

## Threat Flags

None — this plan adds only event-name constants and test scaffolding. No new network endpoints, auth paths, file access patterns, or schema changes.

## Self-Check: PASSED

- app/events.py: FOUND
- tests/conftest.py: FOUND
- tests/test_scheduler.py: FOUND
- tests/test_backup.py: FOUND
- SUMMARY.md: FOUND
- Commit d21e72e: FOUND
- Commit 4413c53: FOUND
- Commit 61e498e: FOUND
