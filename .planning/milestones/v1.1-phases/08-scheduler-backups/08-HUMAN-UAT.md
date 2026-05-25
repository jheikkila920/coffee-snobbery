---
status: passed
phase: 08-scheduler-backups
source: [08-VERIFICATION.md]
started: "2026-05-21T20:30:00Z"
updated: "2026-05-21T20:12:00Z"
---

## Current Test

[all drills run 2026-05-21 against the rebuilt container — see results]

## Tests

### 1. Container boot + apscheduler_jobs table
expected: After `docker compose up -d coffee-snobbery`, the `apscheduler_jobs` table returns exactly two rows: `nightly_ai_refresh` and `nightly_backup`. Startup logs show a `scheduler.started` line.
result: pass — startup logs show `Scheduler started` + both jobs added + `scheduler.started`; `select id from apscheduler_jobs` returned exactly `nightly_ai_refresh` and `nightly_backup`.

### 2. Full pytest suite green in container
expected: Phase 8 suite passes; full suite shows no regressions.
result: pass — Phase 8: 7 passed, 2 skipped (eligibility/token-aggregation skip cleanly: test DB has no Coffee rows for the FK). Full suite: 549 passed, 4 skipped, 10 xfailed, 0 failed. Two real defects were found and fixed first: (a) `test_idempotent_job_registration` called `AsyncIOScheduler.start()` from a sync test (no running loop) → made async; (b) `backup.py` read `os.environ` directly, tripping the FOUND-10 guard → routed through new `config.subprocess_env()`.

### 3. pg_dump restore drill
expected: Run `run_backup()` in-container, restore the produced `db_YYYY-MM-DD.sql` into a fresh schema, row counts match source.
result: pass — `run_backup()` → status=ok, 45KB SQL + photos tarball. Restored into scratch DB `snobbery_restore_test` (exit 0, no errors); counts MATCH (coffees 6=6, users 1=1, brew_sessions 2=2, app_settings 20=20); 16 tables restored; scratch DB dropped. NOTE: required chowning `/app/data/backups` to the `app` user first — see Gap G-01.

### 4. Restart-within-grace-period drill
expected: Restart so 00:00 lands inside the misfire_grace_time window; `nightly_ai_refresh` runs exactly once (coalesce=True + max_instances=1 prevent duplicates).
result: pass (by mechanism) — after `docker compose restart`, exactly 2 jobs persisted (no duplicates, idempotent re-register via replace_existing), next_run_times spaced exactly 2h apart (00:00 AI / 02:00 backup). Literal 23:55 wall-clock timing not faked; covered by verified misfire_grace_time=3600 + coalesce + max_instances=1.

### 5. /healthz after Phase 8 wiring
expected: `/healthz` returns `{"status": "ok"}` after restart with the scheduler wired into lifespan.
result: pass — returned `{"status":"ok"}` both on fresh boot and after restart.

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

### G-01: backups (and photos) volume not writable by the `app` user — infra, blocks SCHED-04 in real use
status: open
severity: high
detail: `/app/data/backups` and `/app/data/photos` are `root:root` (named volumes default to root ownership); the container runs as `app` (uid 1000). `run_backup()` failed every artifact with Permission denied until `/app/data/backups` was chowned to `app`. This is a Phase 0 / infrastructure gap (the Dockerfile sets `USER app` but never creates app-owned `/app/data/*` mountpoints) and it also blocks Phase 4 photo writes. The targeted chown applied during this drill is dev-only and not durable.
recommended_fix: In Dockerfile, before `USER app`, add `RUN mkdir -p /app/data/photos /app/data/backups && chown -R app:app /app/data`; for existing/VPS deploys, one-time `docker compose run --rm -u root coffee-snobbery chown -R app:app /app/data` (or recreate the empty named volumes). Touches deployment topology — pending John's approval.
