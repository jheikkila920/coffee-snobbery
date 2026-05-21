---
status: partial
phase: 08-scheduler-backups
source: [08-VERIFICATION.md]
started: "2026-05-21T20:30:00Z"
updated: "2026-05-21T20:30:00Z"
---

## Current Test

[awaiting human testing — requires the Docker stack running]

## Tests

### 1. Container boot + apscheduler_jobs table
expected: After `docker compose up -d coffee-snobbery`, `docker compose exec coffee-snobbery-db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "select id from apscheduler_jobs order by id"` returns exactly two rows: `nightly_ai_refresh` and `nightly_backup`. Startup logs show a `scheduler.started` line.
result: [pending]

### 2. Full pytest suite green in container
expected: `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx && docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/test_backup.py -q` exits 0 with the 9 named tests passing (no xfail, no skip-for-wrong-reason). The four DB-dependent tests (test_eligibility_filter, test_token_aggregation, test_status_row_write, test_backup_status_row_write) need live Postgres.
result: [pending]

### 3. pg_dump restore drill
expected: Run `run_backup()` in-container, then restore the produced `db_YYYY-MM-DD.sql` into a fresh schema via `psql ... < db_YYYY-MM-DD.sql`. Row counts in the restored schema match the source schema. Confirms the dump is real and restorable (the entire point of the phase).
result: [pending]

### 4. Restart-within-grace-period drill
expected: Stop the container near 23:55 APP_TIMEZONE and restart so 00:00 lands inside the 1-hour misfire_grace_time window. Confirm `nightly_ai_refresh` ran exactly once: exactly one new `last_ai_run_status` row and exactly one `SCHEDULER_AI_RUN_COMPLETE` log line (coalesce=True + max_instances=1 prevent duplicates).
result: [pending]

### 5. /healthz after Phase 8 wiring
expected: `curl -s http://127.0.0.1:8080/healthz` returns `{"status": "ok"}` after a container restart with the scheduler wired into lifespan — no regression from the new start/shutdown hooks.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
