---
phase: 08-scheduler-backups
verified: 2026-05-21T20:00:00Z
status: human_needed
score: 7/7 must-haves verified
overrides_applied: 1
overrides:
  - must_have: "AsyncIOScheduler built with SQLAlchemyJobStore(url=DATABASE_URL)"
    reason: "Implementation uses SQLAlchemyJobStore(engine=engine) with the existing SYNC engine from app.db — reuses the existing connection pool instead of opening a second one. This is the correct, reviewer-endorsed equivalent. The jobstore is still SQLAlchemy-backed and jobs survive container restart."
    accepted_by: "phase-instructions"
    accepted_at: "2026-05-21T20:00:00Z"
human_verification:
  - test: "Container boot with apscheduler_jobs table check"
    expected: "After `docker compose up -d`, `docker compose exec coffee-snobbery-db psql -U $POSTGRES_USER -d $POSTGRES_DB -c \"select id from apscheduler_jobs order by id\"` returns exactly two rows: nightly_ai_refresh and nightly_backup."
    why_human: "Requires running Docker / live Postgres. Cannot execute in this environment (Docker Desktop down, host Python 3.14 != project 3.12)."
  - test: "Full pytest suite green in container"
    expected: "`docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/test_backup.py -q` exits 0 with 9 tests passing (no xfail, no skip for wrong reason). DB-dependent tests (test_eligibility_filter, test_token_aggregation, test_status_row_write, test_backup_status_row_write) require live Postgres."
    why_human: "Requires running Docker / live Postgres."
  - test: "pg_dump restore drill"
    expected: "Run `run_backup()` in-container. Restore the produced `db_YYYY-MM-DD.sql` into a fresh schema via `psql ... < db_YYYY-MM-DD.sql`. Row counts in restored schema match source schema."
    why_human: "Requires live Postgres and pg_dump binary (postgresql-client-16 in image). Manual validation per 08-VALIDATION.md Manual-Only section."
  - test: "Restart-within-grace-period drill"
    expected: "Stop container near 23:55, restart so 00:00 APP_TIMEZONE lands within the 1-hour misfire_grace_time window. Confirm nightly_ai_refresh ran exactly once: exactly one new last_ai_run_status row and exactly one SCHEDULER_AI_RUN_COMPLETE log line."
    why_human: "Requires real container restart timing. Manual validation per 08-VALIDATION.md Manual-Only section."
  - test: "/healthz after Phase 8 wiring"
    expected: "`curl -s 127.0.0.1:8080/healthz` returns `{\"status\": \"ok\"}` after container restart with the scheduler wired in."
    why_human: "Requires running container."
---

# Phase 08: Scheduler + Backups Verification Report

**Phase Goal:** APScheduler AsyncIOScheduler starts in FastAPI's lifespan with SQLAlchemyJobStore (jobs survive container restart), misfire_grace_time=3600, coalesce=True, max_instances=1. Nightly AI refresh at 00:00 APP_TIMEZONE iterates active users with >=3 brew sessions, computes signature, regenerates only when changed via ai_service.regenerate(user_id, generated_by="scheduler", force=False), logs a single summary line and writes app_settings.last_ai_run_status. Nightly backup at 02:00 runs pg_dump SQL + photos tarball into /app/data/backups and prunes older than BACKUP_RETENTION_DAYS (default 14), writing last_backup_status.
**Verified:** 2026-05-21T20:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | AsyncIOScheduler built with SQLAlchemyJobStore(engine=sync engine), misfire_grace_time=3600, coalesce=True, max_instances=1 | VERIFIED (override) | `scheduler.py:75-85` — `SQLAlchemyJobStore(engine=engine)` (SYNC engine from app.db); `job_defaults = {"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1}` |
| 2 | register_jobs() yields exactly 2 jobs after any number of calls (replace_existing=True, stable IDs) | VERIFIED | `scheduler.py:116-127` — both add_job calls have `replace_existing=True`, IDs "nightly_ai_refresh" and "nightly_backup"; `test_idempotent_job_registration` calls register_jobs() three times and asserts `len(jobs) == 2` |
| 3 | Nightly AI refresh enumerates is_active users with >=3 brew sessions and calls regenerate(uid, "scheduler", db=db, force=False) | VERIFIED | `scheduler.py:157-174` — `_get_eligible_user_ids` filters `is_active.is_(True)` and `HAVING count(BrewSession.id) >= 3`; `scheduler.py:299-301` — `asyncio.run(ai_service.regenerate(uid, "scheduler", db=db, force=False))` |
| 4 | ONE SCHEDULER_AI_RUN_COMPLETE structlog line emitted per run AND last_ai_run_status written as JSON string | VERIFIED | `scheduler.py:337` — single `log.info(SCHEDULER_AI_RUN_COMPLETE, **summary)` call; `scheduler.py:234` — `set_setting(db, "last_ai_run_status", json.dumps(summary), by_user_id=None)` |
| 5 | Scheduler starts in lifespan after Phase 3 hooks (prewarm_cache) and shuts down wait=False before engine disposal | VERIFIED | `main.py:170-179` — `prewarm_cache(db)` on line 170, `scheduler_start()` on line 173, `scheduler_shutdown()` on line 177, `dispose_engine()` on line 178 |
| 6 | pg_dump runs plain .sql (list args, no shell=True, PGPASSWORD via env, --clean --if-exists --no-owner --no-privileges), photos tarball, prune by filename date, last_backup_status written as JSON string | VERIFIED | `backup.py:129-171` — `subprocess.run([...], shell=False` implicit list; no -Fc; correct flags; PGPASSWORD via env dict; `backup.py:234` — `for f in list(Path(backup_dir).iterdir())` (materialized); `backup.py:237` — `date.fromisoformat(m.group(1))` (filename date, not mtime); `backup.py:272-273` — `json.dumps(result_dict)` passed to set_setting |
| 7 | Partial failure keeps good artifact; overall status=error if either artifact fails | VERIFIED | `backup.py:337-375` — each artifact in its own try/except; `result.status = "error"` set independently; prune also isolated in try/except (line 381-385); `test_partial_failure_keeps_good` directly asserts this behavior |

**Score:** 7/7 truths verified (1 override applied for engine= vs url= pattern — see overrides section)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/events.py` | scheduler.* and backup.* event constants (11 total), all in __all__ | VERIFIED | All 6 scheduler.* and 5 backup.* constants present; __all__ includes all 11; field-shape comments match plan spec |
| `app/services/scheduler.py` | build_scheduler, register_jobs, run_nightly_ai_refresh, run_nightly_backup, _get_eligible_user_ids, aggregate_tokens_since, write_ai_run_status, start, shutdown | VERIFIED | All exported; 367 lines; substantive implementation |
| `app/services/backup.py` | run_backup, BackupResult, ArtifactResult, prune_old_backups, write_backup_status | VERIFIED | All exported in __all__; 449 lines; substantive implementation |
| `app/main.py` | scheduler_start() after prewarm_cache; scheduler_shutdown() before dispose_engine | VERIFIED | Lines 173 (start) and 177 (shutdown) in lifespan; correct ordering confirmed |
| `tests/test_scheduler.py` | 6 named tests: test_idempotent_job_registration, test_lifespan_scheduler_lifecycle, test_eligibility_filter, test_ai_run_summary_tally, test_token_aggregation, test_status_row_write | VERIFIED | All 6 present; no xfail markers (real assertions); correct test bodies |
| `tests/test_backup.py` | 3 named tests: test_retention_prune, test_partial_failure_keeps_good, test_backup_status_row_write | VERIFIED | All 3 present; no xfail markers (real assertions) |
| `tests/conftest.py` | sync_db and mock_regenerate fixtures | VERIFIED | Both present; sync_db has _postgres_reachable + non-test-DB interlock; mock_regenerate uses AsyncMock with force=False assertion |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/services/scheduler.py` | `app.db.engine` (SYNC) | `SQLAlchemyJobStore(engine=engine)` | VERIFIED | Line 76: `SQLAlchemyJobStore(engine=engine)` |
| `app/services/scheduler.py` | `app.services.ai_service.regenerate` | `asyncio.run(regenerate(uid, "scheduler", db=db, force=False))` | VERIFIED | Lines 299-301: exact call pattern confirmed |
| `app/main.py lifespan` | `scheduler.start() / scheduler.shutdown(wait=False)` | start after prewarm_cache, shutdown before dispose_engine | VERIFIED | Lines 173, 177, 178 in lifespan; ordering confirmed |
| `app/services/backup.py` | `subprocess.run([pg_dump,...])` | list args, no shell=True, PGPASSWORD via env | VERIFIED | Lines 147-169: confirmed list, shell=False (implicit), env dict for PGPASSWORD |
| `app/services/backup.py` | `app_settings.last_backup_status` | `set_setting(db, "last_backup_status", json.dumps(...))` | VERIFIED | Lines 268-274: `write_backup_status` calls `set_setting` with `json.dumps(result_dict)` |
| `app/services/scheduler.py` | `app_settings.last_ai_run_status` | `set_setting(db, "last_ai_run_status", json.dumps(summary))` | VERIFIED | Line 234: exact pattern |
| `app/services/scheduler.py (run_nightly_backup)` | `app.services.backup.run_backup` | lazy import inside job body | VERIFIED | Lines 355-357: `from app.services.backup import run_backup; run_backup()` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `scheduler.py run_nightly_ai_refresh` | `eligible_user_ids` | `_get_eligible_user_ids(db)` — real SQLAlchemy query with join/group-by/having | Yes (static analysis confirms non-trivial query, not empty list) | FLOWING |
| `scheduler.py run_nightly_ai_refresh` | `summary` token totals | `aggregate_tokens_since(db, run_start)` — real SUM query on ai_recommendations | Yes | FLOWING |
| `scheduler.py run_nightly_ai_refresh` | `run_start` | `db.execute(text("SELECT now()")).scalar_one()` (DB clock, not app clock) | Yes — WR-01 addressed | FLOWING |
| `backup.py run_backup` | `status_dict` | per-artifact try/except with real subprocess + tarfile; `json.dumps(status_dict)` to set_setting | Yes | FLOWING |
| `backup.py prune_old_backups` | `file_date` | `date.fromisoformat(m.group(1))` from filename regex, not st_mtime | Yes — D-02 honored | FLOWING |

---

### Behavioral Spot-Checks

Step 7b: Runtime spot-checks SKIPPED — Docker Desktop is down and host Python 3.14 != project target 3.12. Static analysis substituted where possible; runtime behaviors flagged in Human Verification section.

| Behavior | Static Check | Result | Status |
|----------|-------------|--------|--------|
| `test_idempotent_job_registration` calls register_jobs 3x, asserts len==2 | Code read | MemoryJobStore override, 3 register_jobs calls, `assert len(jobs) == 2` confirmed | PASS (static) |
| `test_retention_prune` logic correctness | Code read | Fixed today=2026-05-21, retention=14, files dated 2026-05-01 (delete) and 2026-05-20 (keep), asserts deleted==2 | PASS (static) |
| `test_partial_failure_keeps_good` isolates pg_dump failure | Code read | `_run_pg_dump` patched to raise; `write_backup_status` patched; photos tarball still attempted via independent try/except | PASS (static) |
| DB-dependent tests (eligibility_filter, token_aggregation, status_row_write, backup_status_row_write) | N/A — need live Postgres | Cannot verify | SKIP (human needed) |
| Container boots with scheduler.started log + 2 apscheduler_jobs rows | N/A — need container | Cannot verify | SKIP (human needed) |

---

### Probe Execution

Step 7c: No probe scripts found in `scripts/*/tests/probe-*.sh`. Phase plans declare container-based test commands (`docker compose exec ...`). All probe execution requires Docker — SKIPPED in this environment.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SCHED-01 | 08-03-PLAN.md | AsyncIOScheduler in lifespan, SQLAlchemyJobStore, misfire_grace_time=3600, coalesce=True, max_instances=1 | SATISFIED | `scheduler.py:75-91`, `main.py:173,177`; static analysis confirms all parameters |
| SCHED-02 | 08-03-PLAN.md | Nightly AI refresh at 00:00 APP_TIMEZONE; active users >=3 sessions; regenerate only when signature changed (via regenerate force=False) | SATISFIED | `scheduler.py:116-121, 157-174, 299-301`; CronTrigger(hour=0, minute=0); eligibility query; asyncio.run(regenerate(..., force=False)) |
| SCHED-03 | 08-03-PLAN.md | Job summary logged; users processed, regenerations, skips, tokens (web-search split), errors; written to last_ai_run_status | SATISFIED | `scheduler.py:265-337`; single SCHEDULER_AI_RUN_COMPLETE emit; json.dumps to set_setting; token aggregation with `tokens_input_search_total` split |
| SCHED-04 | 08-02-PLAN.md | Nightly backup at 02:00; pg_dump .sql + photos tarball; BACKUP_RETENTION_DAYS prune; last_backup_status written | SATISFIED | `backup.py` full implementation; `scheduler.py:346-366` nightly_backup job; CronTrigger(hour=2, minute=0); prune by filename date |

No orphaned requirements. REQUIREMENTS.md maps SCHED-01..04 to Phase 8, all four claimed in plans 08-02 and 08-03, all four verified.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `backup.py:397-399` | `import datetime` inside `run_backup` function body while `date`, `timedelta` are module-level imports (IN-01 from code review) | Info | Style inconsistency; not a correctness issue |
| `backup.py:420` | `_db = db  # type: ignore[assignment]` — type: ignore masking a real type-safety concern (WR-05 from code review, deferred) | Warning | WR-05 was explicitly deferred in the review guidance; the test uses `db=object()` with `write_backup_status` patched out, so the bogus session is never exercised. Non-blocking. |
| `test_scheduler.py:162-211` | `test_ai_run_summary_tally` re-implements the production tally logic in the test body instead of calling `run_nightly_ai_refresh()` (WR-06 from code review, deferred) | Warning | WR-06 was explicitly deferred in the review guidance. The force=False guard is genuinely exercised; tally coverage is tautological. Non-blocking. |

No TBD, FIXME, or XXX markers found in any Phase 8 files.

---

### Code Review Resolution Check

The 08-REVIEW.md documented 1 critical + 7 warnings. Verifying which were fixed vs deferred:

| Finding | Resolution | Verified |
|---------|-----------|---------|
| CR-01: `_parse_db_url` regex breaks on reserved chars in passwords | FIXED — `backup.py:39,117` uses `sqlalchemy.engine.make_url` | Yes — `from sqlalchemy.engine import make_url` at line 39; `u = make_url(url)` at line 117 |
| WR-01: app-clock vs DB-clock skew for token aggregation | FIXED — `scheduler.py:280` reads `run_start` via `db.execute(text("SELECT now()"))` | Yes |
| WR-02: `iterdir()` mutated while iterating | FIXED — `backup.py:234` uses `for f in list(Path(backup_dir).iterdir())` | Yes |
| WR-03: prune failure aborts run_backup | FIXED — `backup.py:381-385` wraps prune in try/except | Yes |
| WR-04: `_tar_photos` follows symlinks | FIXED — `backup.py:174-182` adds `_no_symlinks` filter function | Yes |
| WR-05: test uses `db=object()` sentinel (deferred per review guidance) | DEFERRED — known follow-up | Noted as Warning above |
| WR-06: `test_ai_run_summary_tally` tautology (deferred per review guidance) | DEFERRED — known follow-up | Noted as Warning above |
| WR-07: per-user session and regenerate lock-release interaction | ADDRESSED with comment at call site — `scheduler.py:285-294` documents the interaction | Yes |

---

### Human Verification Required

Five items require a running container. Automated static analysis cannot substitute for these.

#### 1. Container Boot + apscheduler_jobs Table

**Test:** `docker compose up -d coffee-snobbery && docker compose exec coffee-snobbery-db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "select id from apscheduler_jobs order by id"`
**Expected:** Two rows returned — `nightly_ai_refresh` and `nightly_backup`.
**Why human:** Requires live Docker + Postgres.

#### 2. Full pytest suite in container

**Test:** `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio && docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/test_backup.py -q`
**Expected:** 9 tests pass (2 may skip with Postgres-required message if DB not seeded; 0 errors, 0 false passes).
**Why human:** Requires live Docker. The four DB-dependent tests need live Postgres and a seeded test database.

#### 3. pg_dump Restore Drill

**Test:** Run `run_backup()` in-container, then `psql -U $POSTGRES_USER $POSTGRES_DB < /app/data/backups/db_$(date +%Y-%m-%d).sql` against a fresh schema, compare row counts.
**Expected:** Row counts in restored schema match source schema.
**Why human:** Requires live pg_dump binary (postgresql-client-16 in image) and Postgres; manual validation per 08-VALIDATION.md.

#### 4. Restart-Within-Grace-Period Drill

**Test:** Stop container near 23:55 APP_TIMEZONE, restart so 00:00 fires within the 1-hour misfire_grace_time window; observe logs.
**Expected:** Exactly one SCHEDULER_AI_RUN_COMPLETE log line; exactly one last_ai_run_status update; no duplicate job fires.
**Why human:** Requires real wall-clock timing and container restart; manual validation per 08-VALIDATION.md.

#### 5. /healthz Regression Check After Phase 8 Wiring

**Test:** `curl -s http://127.0.0.1:8080/healthz` after container restart.
**Expected:** `{"status": "ok"}` — no regression from scheduler wiring.
**Why human:** Requires running container.

---

### Known Follow-ups (Not Blocking)

The following items were explicitly deferred in the code review (08-REVIEW.md) and are tracked here as known tech debt, not gaps:

1. **WR-05** — `test_partial_failure_keeps_good` passes `db=object()` sentinel; a future test improvement should pass `db=None` + patch `SessionLocal` to give real session coverage.
2. **WR-06** — `test_ai_run_summary_tally` re-implements the production tally in the test body. Future improvement: call `run_nightly_ai_refresh()` directly with mocked regenerate and assert on the emitted summary.
3. **IN-01** — `import datetime` inside `run_backup` function body; minor style inconsistency.
4. **IN-02** — Magic numbers for cron hours (0, 2) and pg_dump timeout (300) not named as module constants.
5. **IN-04** — `overall` key in the runtime summary dict not documented in the SCHEDULER_AI_RUN_COMPLETE field-shape comment in events.py.
6. **IN-05** — Asymmetric failure semantics: backup job re-raises on failure (APScheduler sees it), AI job absorbs errors into summary (APScheduler always sees success). Intentional but undocumented in AI job docstring.

---

### Gaps Summary

No blocking gaps found. All 7 must-have truths verify by static analysis. The single override (engine= instead of url=) is intentional and reviewer-endorsed. Code review CR-01 and WR-01 through WR-04 were all fixed before this verification.

The phase goal is statically fully achieved. Human verification is required for runtime behavior that cannot be confirmed without a running container (apscheduler_jobs table creation, full pytest suite, pg_dump restore drill, restart-within-grace behavior).

---

_Verified: 2026-05-21T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
