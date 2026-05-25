---
phase: 08-scheduler-backups
plan: "03"
subsystem: scheduler
tags: [apscheduler, asyncioscheduler, sqlalchemyjobstore, cron, nightly-jobs, ai-refresh, backup, sched-01, sched-02, sched-03]
dependency_graph:
  requires:
    - app.db.engine (SYNC)
    - app.db.SessionLocal
    - app.config.settings.APP_TIMEZONE
    - app.services.ai_service.regenerate (async, frozen contract)
    - app.services.backup.run_backup (Plan 08-02)
    - app.services.settings.set_setting
    - app.models.user.User.is_active
    - app.models.brew_session.BrewSession.user_id
    - app.models.ai_recommendation.AIRecommendation (token columns)
    - app.events.SCHEDULER_* (Plan 08-01)
  provides:
    - app.services.scheduler.build_scheduler
    - app.services.scheduler.register_jobs (idempotent, stable IDs)
    - app.services.scheduler.start / shutdown (lifespan helpers)
    - app.services.scheduler._get_eligible_user_ids
    - app.services.scheduler.aggregate_tokens_since
    - app.services.scheduler.write_ai_run_status
    - app.services.scheduler.run_nightly_ai_refresh (SCHED-02/03)
    - app.services.scheduler.run_nightly_backup (SCHED-04 wrapper)
    - app_settings.last_ai_run_status (JSON string, written nightly)
    - app.main.lifespan (scheduler wired in, SCHED-01)
  affects:
    - Phase 9 (admin API-health panel reads last_ai_run_status via raw DB query)
    - Phase 9 ("Run backup now" button calls run_backup via same entry point)
tech_stack:
  added: []
  patterns:
    - sync-def job body + asyncio.run() bridge for async regenerate (sync→async, household-scale)
    - SQLAlchemyJobStore(engine=) with SYNC engine (not url=, not _async_engine)
    - replace_existing=True + stable job IDs for idempotent restarts
    - Lazy import of run_backup inside job body (decouples Plans 02/03)
    - Phase 9 cross-phase contract: last_ai_run_status read via raw DB query, not get_str()
key_files:
  created: []
  modified:
    - app/services/scheduler.py
    - app/main.py
    - tests/test_scheduler.py
key_decisions:
  - "sync→async bridge: asyncio.run(regenerate(uid, 'scheduler', db=db, force=False)) per user — same pattern as conftest._seed_user; each asyncio.run opens a fresh event loop in the ThreadPoolExecutor worker thread; correct and low-cost at household scale"
  - "Phase 9 reads last_ai_run_status via raw DB query — set_setting() pops the cache key after commit; until the next prewarm_cache() call get_str() raises SettingNotFoundError. Admin panel reads infrequently and can absorb a DB hit. DO NOT call prewarm_cache() after the write."
  - "apscheduler_jobs table is APScheduler-managed (auto-created by SQLAlchemyJobStore.start() via metadata.create_all); it is NOT in the Alembic migration chain. No migration needed."
  - "scheduler_start() called AFTER log.info('app.startup') to match task spec; jobs may read prewarm_cache'd settings"
  - "shutdown(wait=False) called BEFORE dispose_engine() — non-blocking so SIGTERM during mid-flight pg_dump never stalls container stop"
requirements-completed: [SCHED-01, SCHED-02, SCHED-03]

duration: 6min
completed: "2026-05-21"
---

# Phase 08 Plan 03: Scheduler Wiring + Nightly AI Refresh + Backup Wrapper Summary

**AsyncIOScheduler wired into FastAPI lifespan with SQLAlchemyJobStore (sync engine), nightly AI refresh job (eligibility filter + asyncio.run regenerate bridge + SCHED-03 token aggregation summary), and nightly backup wrapper — all six scheduler tests green.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-21T~19:16Z
- **Completed:** 2026-05-21T~19:22Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- `app/services/scheduler.py` replaced from stub: `build_scheduler()`, `register_jobs()` (idempotent, stable IDs), `start()`/`shutdown()` lifespan helpers, `_get_eligible_user_ids()`, `aggregate_tokens_since()`, `write_ai_run_status()`, `run_nightly_ai_refresh()`, `run_nightly_backup()`
- SCHED-01: SQLAlchemyJobStore uses the SYNC engine from `app.db`; `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`; exactly 2 jobs after any number of `register_jobs()` calls
- SCHED-02/03: AI refresh filters `is_active=True AND >= 3 brew sessions`, bridges sync→async via `asyncio.run()`, tallies status strings, aggregates token columns from this-run `ai_recommendations` rows, emits ONE `SCHEDULER_AI_RUN_COMPLETE` log line + writes `last_ai_run_status` as JSON string
- `app/main.py` lifespan wired: `scheduler_start()` after `prewarm_cache`, `scheduler_shutdown(wait=False)` before `dispose_engine()`
- All 6 `tests/test_scheduler.py` xfail stubs replaced with real assertions

## Task Commits

1. **Task 1: Build AsyncIOScheduler + idempotent register_jobs** - `eabf80d` (feat)
2. **Task 2: Nightly AI refresh job + backup wrapper + green scheduler tests** - `664a2a5` (feat)
3. **Task 3: Wire scheduler start/shutdown into lifespan** - `92ff71f` (feat)
4. **[Rule 1 - Bug] Correct MemoryJobStore override in test** - `4de2480` (fix)

## Files Created/Modified

- `app/services/scheduler.py` — Full APScheduler implementation (was stub); 338 lines added
- `app/main.py` — Lifespan wired with scheduler_start/shutdown imports + calls
- `tests/test_scheduler.py` — All 6 xfail stubs replaced with real assertions

## Decisions Made

**sync→async bridge (asyncio.run per user):**
`regenerate()` is `async def` but the APScheduler job body must be `sync def` to avoid blocking the event loop (Pitfall 4). Each per-user call uses `asyncio.run(ai_service.regenerate(uid, "scheduler", db=db, force=False))` — the same pattern as `conftest._seed_user`. At household scale (sequential, 2 users max) this is correct and low-cost.

**Phase 9 cross-phase contract (last_ai_run_status):**
`set_setting()` pops the cache key after every write. The scheduler deliberately does NOT call `prewarm_cache()` after the write. Phase 9's API-health panel MUST read `last_ai_run_status` via a raw DB query:
```python
row = db.execute(
    select(AppSetting).where(AppSetting.key == "last_ai_run_status")
).scalar_one()
parsed = json.loads(row.value)
```

**apscheduler_jobs table:**
APScheduler auto-creates it via `SQLAlchemyJobStore.start()` → `metadata.create_all()`. Not in the Alembic migration chain. No migration needed — add a comment in migration README if confusion arises.

**register_jobs() signature change:**
The Wave 0 stubs assumed `register_jobs(sched)` (accepting a scheduler argument). The plan text only mentioned a module-level call, but the tests needed to pass a local in-memory-backed scheduler. `register_jobs()` accepts an optional `sched` parameter defaulting to the module-level singleton — backward-compatible and test-friendly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MemoryJobStore pre-start in test_idempotent_job_registration**
- **Found during:** Task 1 review
- **Issue:** Test stub showed manually calling `.start(sched, "default")` on the MemoryJobStore before `sched.start()` — APScheduler calls `jobstore.start()` internally during `scheduler.start()`, so pre-starting would double-initialize the store
- **Fix:** Removed the manual `.start()` call; let APScheduler's own `start()` initialize the MemoryJobStore
- **Files modified:** tests/test_scheduler.py
- **Committed in:** 4de2480

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Minor test correctness fix; no functional scope change.

## Known Stubs

None. All three implementations are complete and all test assertions are real.

## Phase 9 Cross-Phase Contract

**DO NOT BREAK:** `last_ai_run_status` is written as a JSON STRING to `app_settings` (value_type="string"). Phase 9's API-health panel MUST read it via a raw DB query (not `get_str()`). The JSON shape:

```json
{
  "users_processed": 2,
  "regenerations": 1,
  "skips": 1,
  "errors": 0,
  "tokens_input_total": 200,
  "tokens_output_total": 100,
  "tokens_input_search_total": 30,
  "overall": "ok",
  "timestamp": "ISO-8601 UTC"
}
```

`non_search_input = tokens_input_total - tokens_input_search_total`

## Threat Flags

None — this plan adds no new network endpoints, auth paths, or schema changes. The `apscheduler_jobs` table is APScheduler-internal and not exposed via any route. The security-relevant patterns (max_instances=1, is_active filter, force=False) are addressed in the implementation and verified by tests.

## Self-Check: PASSED

- app/services/scheduler.py: FOUND
- app/main.py: FOUND (scheduler_start/shutdown wired)
- tests/test_scheduler.py: FOUND (xfail stubs removed, real assertions)
- Commit eabf80d: FOUND
- Commit 664a2a5: FOUND
- Commit 92ff71f: FOUND
- Commit 4de2480: FOUND
- SQLAlchemyJobStore(engine= present: VERIFIED (line 76)
- asyncio.run( present: VERIFIED (line 287-288)
- force=False present: VERIFIED (line 288)
- scheduler.shutdown(wait=False) present: VERIFIED (line 148)
- SCHEDULER_AI_RUN_COMPLETE single emit: VERIFIED (one log.info call, line 325)
- json.dumps adjacent to last_ai_run_status: VERIFIED (line 234)
- single-worker warning block preserved: VERIFIED (grep count=4)
- ruff check scheduler.py: PASSED
- ruff check tests/test_scheduler.py: PASSED
- ruff check app/main.py: PASSED
