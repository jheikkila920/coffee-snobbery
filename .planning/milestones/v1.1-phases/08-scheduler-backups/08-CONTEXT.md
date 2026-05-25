# Phase 8: Scheduler + Backups - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the in-process scheduler and the nightly maintenance jobs. Delivers 4
requirements (SCHED-01..04).

In scope:
- **APScheduler `AsyncIOScheduler`** started/stopped in FastAPI `lifespan`,
  backed by `SQLAlchemyJobStore` (jobs survive container restart), with
  `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1` (SCHED-01).
- **Nightly AI refresh @ 00:00 `APP_TIMEZONE`** — enumerate eligible users,
  call the frozen `ai_service.regenerate(uid, "scheduler", db=db)` per user
  (signature check applies; `force=False`), aggregate a run summary (SCHED-02).
- **Run summary** logged as one structured line AND persisted to the existing
  `app_settings.last_ai_run_status` row (SCHED-03).
- **Nightly backup @ 02:00 `APP_TIMEZONE`** — `pg_dump` SQL file + photos
  tarball into `/app/data/backups` (the `coffee_snobbery_backups` volume),
  prune older than `BACKUP_RETENTION_DAYS` (default 14), persist result to the
  existing `app_settings.last_backup_status` row (SCHED-04).
- A reusable **`backup` entry point** designed so Phase 9's "Run backup now"
  admin button can invoke it synchronously (forward dependency).

Out of scope (belongs to later phases):
- **Backups list / download UI, "Run backup now" button, system-info +
  API-health panels** — **Phase 9** (this phase only writes the status rows +
  files those panels read).
- **Admin-editable AI tool-version / model rows** — **Phase 9**.
- **No new user-facing routes or templates this phase** — no 375px / mobile
  work; the scheduler and backup service are headless.
- **Formal scheduler/backup test suite** — accrue tests as you go per CLAUDE.md;
  the formal suite is **Phase 12**.

</domain>

<decisions>
## Implementation Decisions

### Backup result + status (D-01)
- **`services/backup.py` exposes a single entry point that returns a structured
  result object** (per-artifact: filename, byte size, ok/error; plus overall
  status + duration). Both the scheduler and Phase 9's "Run backup now" button
  call this same entry point.
- The entry point **writes a structured (JSON) `app_settings.last_backup_status`**
  row capturing: overall status, timestamp, db filename + bytes, photos filename
  + bytes, duration, and any per-artifact error message — so the Phase 9
  system-info panel shows real numbers and can surface a failed artifact.
  - Planner confirms the `last_backup_status` row's `value_type` (it is seeded in
    migration `0001_initial`; if it is `string`, store a JSON string and document
    it — do NOT add a migration just for this).

### Same-day file naming + retention (D-02)
- **Date-only filenames, overwrite the day's file:** `db_YYYY-MM-DD.sql` and
  `photos_YYYY-MM-DD.tar.gz` — one idempotent snapshot per day. A manual run
  (Phase 9) on the same day overwrites that day's nightly file.
- **Retention prunes by parsing the date in the filename** (not mtime), deleting
  both `db_*` and `photos_*` files older than `BACKUP_RETENTION_DAYS`.
- Rationale: matches SC-4's exact filename and the existing CLAUDE.md restore
  runbook glob (`psql ... < db_YYYY-MM-DD.sql`) with zero runbook change.

### Backup partial-failure handling (D-03)
- **Keep partial + flag.** The two artifacts (`pg_dump`, photos tarball) are
  attempted independently; whatever succeeds is written and kept; the result
  records per-artifact ok/error and sets overall status = error if any artifact
  failed. Honest and recoverable for restore drills — a failed photos tarball
  never silently discards a good DB dump.
- **The AI refresh job and the backup job are fully independent APScheduler
  jobs** — one failing (or raising) never blocks or skips the other. `max_instances=1`
  is per-job, so neither overlaps itself.

### Nightly AI refresh eligibility + status (D-04)
- **Eligibility pre-filter = `User.is_active = true` AND `>= 3` brew sessions.**
  `regenerate()` still owns the rest of the gating (the `>= 5` distinct-flavor-note
  cold-start gate, the signature comparison, the in-memory + advisory locks,
  the throttle). The scheduler does NOT re-implement any of that — it filters
  cheaply, then calls `regenerate(uid, "scheduler", db=db)` and tallies the
  returned status string.
- **`app_settings.last_ai_run_status` stores the full SCHED-03 summary**
  (structured): `users_processed`, `regenerations`, `skips`, `tokens_input_total`,
  `tokens_output_total`, `tokens_input_search_total`, `errors`, plus a timestamp
  and overall ok/error — the same fields as the structured log line. Phase 9's
  API-health panel reads this for real per-run numbers (not just a message).
  - Token totals are aggregated from the `ai_recommendations` rows written during
    this run (columns `tokens_input`, `tokens_output`, `tokens_input_search`
    already exist); non-web-search input = `tokens_input - tokens_input_search`.

### Claude's Discretion (resolve with the noted default; document in the plan)
- **Job-registration idempotency:** with `SQLAlchemyJobStore`, re-adding jobs on
  every startup duplicates them. Use **stable explicit job IDs** (e.g.
  `nightly_ai_refresh`, `nightly_backup`) + **`replace_existing=True`** so each
  start reconciles to exactly two jobs. (Researcher/planner: confirm the exact
  3.x API.)
- **Timezone wiring:** `CronTrigger(hour=0, minute=0, timezone=APP_TIMEZONE)` and
  `hour=2` for backup; default `America/Chicago`. Confirm `AsyncIOScheduler`
  timezone handling + DST behavior.
- **User iteration:** **sequential**, one user at a time (household scale; avoids
  hammering the AI provider and the connection pool). Bound each `regenerate`
  call's DB work to its own transaction/session as the existing service expects.
- **`pg_dump` invocation:** run from inside the web container (matched
  `postgresql-client-16`, installed Phase 0) against `coffee-snobbery-db`, reading
  host/port/db/user/password from config (`DATABASE_URL` / Postgres env) — never
  hardcoded. Planner picks flags (e.g. `--no-owner`, `--clean`/`--if-exists`)
  consistent with the `psql < file.sql` restore path. Shell out via
  `subprocess.run` (per Tech Stack gap-libraries guidance — no Python pg-backup
  lib); tar the photos volume via the `tarfile` stdlib.
- **DB dump format:** **plain, uncompressed `.sql`** — locked by the CLAUDE.md
  restore runbook + SC-4 filename. Do NOT gzip the SQL (would break the runbook
  glob). Photos remain `.tar.gz`.
- **`scheduler.*` / `backup.*` event taxonomy** in `app/events.py`
  (scheduler start/shutdown, job start/success/error, ai-run summary,
  backup summary/prune).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 8: Scheduler + Backups" — goal sentence, the 4
  success criteria, and Notes (carries pitfall SH-1: default `MemoryJobStore`
  loses jobs + default 1s `misfire_grace_time` skips restarts; SH-5: version-matched
  `pg_dump`; COST-3: `last_ai_run_status` for the admin health panel; re-references
  the single-worker rule).
- `.planning/REQUIREMENTS.md` §"AI Run Scheduling" — SCHED-01..04 verbatim
  (lines ~113-116).
- `.planning/PROJECT.md` §"Constraints" (Scheduling: APScheduler in-process, no
  external worker), §"Key Decisions" (APScheduler `SQLAlchemyJobStore` +
  `misfire_grace_time=3600` + `coalesce=True`; single uvicorn worker), §"Admin"
  active requirements (nightly backup + retention + system-info panel — the
  forward consumer).
- `.planning/STATE.md` — current session continuity + carried research flags.

### Prior phase context (decisions Phase 8 consumes)
- `.planning/phases/07-ai-services/07-CONTEXT.md` — the frozen
  `regenerate(user_id, generated_by, *, db, force=False) -> str` contract and
  its return-status set (`generated`/`skipped`/`locked`/`try_again`/
  `not_configured`/`error`); the cost controls `regenerate()` already owns
  (signature, cold-start gate, locks, throttle, `max_uses`, telemetry).
- `.planning/phases/06-analytics-home-page/06-CONTEXT.md` — `compute_input_signature`
  composition + the cold-start counts the AI gate uses (background; the scheduler
  does not call these directly — `regenerate()` does).
- `.planning/phases/03-encryption-settings/03-CONTEXT.md` — the typed `settings`
  reader + cache (write-through invalidation) used to read `BACKUP_RETENTION_DAYS`-
  adjacent settings and to write the `last_*_status` rows; `app_settings`
  `value_type` coercion (`string`/`integer`/`boolean`/`json`).
- `.planning/phases/00-foundation/00-CONTEXT.md` — single-uvicorn-worker rule;
  sync `SessionLocal` pattern + the "no sync DB on the async event loop" caveat
  (relevant to an `AsyncIOScheduler` job body); `postgresql-client-16` in the web
  image; the `coffee_snobbery_backups` volume mounted at `/app/data/backups`.

### Code in this repo (read before implementing)
- `app/services/scheduler.py` — current **placeholder stub**; Phase 8 replaces
  its body. Contains the single-worker warning (location #2 of 3 — preserve the
  count if you edit it).
- `app/services/ai_service.py` (`regenerate`, ~line 1126) — the entry point the
  AI refresh loop calls.
- `app/main.py` (`lifespan`, ~line 147) — where the scheduler starts/stops; note
  the existing Phase 3 hook ordering and the `engine` / `_async_engine` disposal
  on shutdown.
- `app/config.py` — `APP_TIMEZONE` (default `America/Chicago`, line ~52),
  `BACKUP_RETENTION_DAYS` (default 14, line ~53), `DATABASE_URL` (line ~39).
- `app/migrations/versions/0001_initial.py` — seeded `last_ai_run_status` (~line
  291) and `last_backup_status` (~line 299) rows; check their `value_type`.
- `app/models/ai_recommendation.py` — token columns for the SCHED-03 split
  (`tokens_input`, `tokens_output`, `tokens_input_search`, `web_search_count`).
- `app/models/user.py` — `is_active` (line ~45) for the eligibility filter.
- `app/services/settings.py` — typed read/write + cache invalidation for the
  status rows.

### Operational + spec
- `CLAUDE.md` §"Restore from backup" (the runbook the backup filenames must
  match), §"Architectural invariants" (signature-based regen is the cost control
  — don't break it; single-worker), §"Stack invariants" (APScheduler in-process),
  §"When to ask vs proceed" (changes to AI scheduling / cost-control = ask first),
  §"Files worth knowing" (`services/scheduler.py`, `entrypoint.sh`).
- `CLAUDE.md` "Technology Stack" §1 (`APScheduler>=3.11,<4` — stay on 3.x; 4.x is
  alpha) + gap-libraries row (backup = shell out to `pg_dump` via `subprocess.run`
  + `tarfile` stdlib; ~50 LOC, no Python pg-backup lib).

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- `APScheduler` 3.11 — `AsyncIOScheduler`, `SQLAlchemyJobStore(url=...)`,
  `CronTrigger(timezone=...)`, `add_job(..., id=..., replace_existing=True,
  coalesce=True, misfire_grace_time=3600, max_instances=1)`, start/shutdown
  inside an async lifespan.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`app/services/ai_service.py::regenerate`** — frozen SCHED-02 contract; the
  AI loop's only call into the AI subsystem. Returns a status string the loop
  tallies into the run summary.
- **`app/services/settings.py`** — typed reader/writer + in-memory cache;
  used to persist `last_ai_run_status` / `last_backup_status` and read
  retention/timezone-adjacent settings.
- **`app/config.py`** — `APP_TIMEZONE`, `BACKUP_RETENTION_DAYS`, `DATABASE_URL`
  already defined and annotated "consumed by Phase 8".
- **`app/main.py::lifespan`** — established hook site; add scheduler
  start (after the existing Phase 3 hooks) + shutdown (before engine disposal).
- **`app/events.py`** — structured-event taxonomy module; add `scheduler.*` /
  `backup.*` constants following the existing `ai.*` pattern.
- **`app/models/ai_recommendation.py`** — token columns drive the SCHED-03
  web-search-vs-non split.

### Established Patterns
- "Cross-cutting → middleware; feature surface → router; stateful logic →
  service." Phase 8 is service + lifespan wiring only: `services/scheduler.py`
  (replace stub) + new `services/backup.py`. No router, no templates.
- structlog one-JSON-line-per-event with a stable event name (SCHED-03 summary
  is one such line).
- `app_settings` is the runtime key/value store; status rows already exist —
  write to them, don't add columns.
- Single uvicorn worker is the concurrency assumption — in-process scheduler +
  module-level AI locks both depend on it.
- "async where it pays": the scheduler is async (`AsyncIOScheduler`), but the AI
  loop's DB reads and `regenerate`'s writes follow the existing sync-up-front /
  async-LLM / sync-write pattern — do not block the event loop with long sync DB
  scans inside the job body; bound DB work per user.

### Integration Points
- `app/main.py` lifespan — scheduler `start()` / `shutdown(wait=False)`.
- `app/services/scheduler.py` — job definitions (the two cron jobs + the AI-loop
  and backup-call function bodies, or thin wrappers delegating to
  `services/backup.py` and an AI-refresh function).
- `app/services/backup.py` — NEW. `pg_dump` + photos tarball + prune + structured
  result + `last_backup_status` write. Designed as the shared entry point Phase 9
  reuses synchronously.
- **Phase 9 forward dependency:** the backup result shape and the two
  `last_*_status` JSON shapes are the contract Phase 9's system-info +
  API-health panels and the "Run backup now" button consume.

</code_context>

<specifics>
## Specific Ideas

- **Backups directory is `/app/data/backups`** (the `coffee_snobbery_backups`
  named volume) — filenames `db_YYYY-MM-DD.sql` + `photos_YYYY-MM-DD.tar.gz`,
  matching the CLAUDE.md restore runbook exactly.
- **Two warning sites for the single-worker rule already exist** in scheduler.py
  (location #2 of 3). If the stub comment is rewritten, keep the count at three
  (entrypoint.sh, scheduler.py, README.md).
- **No migration expected** — both status `app_settings` rows are already seeded.
  Add a migration only if planning surfaces a genuinely new column/index need.
- **`pg_dump` version match is load-bearing** (SH-5) — `postgresql-client-16`
  ships in the web image from Phase 0; the dump runs there, not in the db
  container.

## No SPEC.md
No `*-SPEC.md` exists for this phase — requirements are SCHED-01..04 in
REQUIREMENTS.md plus the decisions above and the canonical refs.

## Research flags (for gsd-phase-researcher)
- **APScheduler 3.11 idempotent job registration** with `SQLAlchemyJobStore` +
  `replace_existing=True` + stable IDs across container restarts (avoid duplicate
  jobs); confirm `AsyncIOScheduler` start/shutdown inside an async FastAPI
  lifespan and that `SQLAlchemyJobStore(url=DATABASE_URL)` accepts the
  `postgresql+psycopg://` URL (or whether it needs a sync driver URL).
- **Misfire/coalesce on cron jobs after restart** — verify `misfire_grace_time=3600`
  + `coalesce=True` actually fire a missed 00:00/02:00 job once on a restart that
  lands within the grace window (SC-4 simulated-restart criterion).
- **`pg_dump` flags + connection** for a clean `psql < file.sql` restore path
  (e.g. `--clean --if-exists --no-owner`); confirm whether to pass the password
  via `PGPASSWORD` env or `~/.pgpass` in the subprocess call.

</specifics>

<deferred>
## Deferred Ideas

- **Backups list / download UI, "Run backup now" button, system-info +
  API-health panels** — Phase 9 (Phase 8 only produces the files + status rows
  they read).
- **Per-month / per-user AI cost ceiling** — already v2-deferred (PROJECT);
  signature regen + throttle + `max_uses` is the v1 control. The scheduler must
  not add a new ceiling.
- **Off-site / encrypted backup shipping, restore automation, backup integrity
  verification** — out of scope for v1; nightly local snapshot + retention only.
- **DB dump compression (`.sql.gz`)** — rejected for v1 (would break the
  restore-runbook glob); revisit only if backup disk usage on the VPS becomes a
  problem.

### Reviewed Todos (not folded)
- **"Inline add-new-coffee from the brew form"** (open in STATE.md) — Phase 4/5
  catalog scope, unrelated to scheduling/backups. Not folded.

</deferred>

---

*Phase: 8-Scheduler + Backups*
*Context gathered: 2026-05-21*
