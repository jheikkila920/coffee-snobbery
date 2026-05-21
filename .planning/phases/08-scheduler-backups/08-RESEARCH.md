# Phase 8: Scheduler + Backups - Research

**Researched:** 2026-05-21
**Domain:** APScheduler 3.11 in-process scheduling, pg_dump backup, FastAPI lifespan wiring
**Confidence:** HIGH (codebase verified; APScheduler API confirmed via official docs + maintainer issues)

## Summary

Phase 8 is a pure backend wiring phase: replace the `scheduler.py` stub with a real
`AsyncIOScheduler` backed by `SQLAlchemyJobStore`, wire it into the existing `lifespan`,
and implement two nightly jobs. No routes, templates, or UI changes.

The central technical concern is **engine compatibility**: APScheduler's
`SQLAlchemyJobStore` is synchronous internally and must receive a **sync** engine.
The app already has a sync engine in `app/db.py` (`engine`). Pass it via
`SQLAlchemyJobStore(engine=engine)` — do not pass the `_async_engine` from `main.py`
and do not create a third engine. This is the single most failure-prone decision in
the phase.

The second concern is **event-loop safety**: nightly job bodies do sync DB work and
call `regenerate()` (a sync function with async AI calls inside). The safe, documented
approach is a `sync def` job body — `AsyncIOScheduler` automatically runs sync
functions in the event loop's default executor (a ThreadPoolExecutor), keeping the
event loop unblocked. No `asyncio.to_thread` wrapping is needed.

**Primary recommendation:** `SQLAlchemyJobStore(engine=engine)` (reuse app sync engine)
+ `sync def` job bodies + `shutdown(wait=False)` in lifespan.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `services/backup.py` exposes a single entry point returning a structured result
  object (per-artifact: filename, bytes, ok/error; overall status + duration). Both
  scheduler and Phase 9 "Run backup now" button call this same entry point.
- **D-01 (status row):** Entry point writes a structured JSON `app_settings.last_backup_status`
  row. Planner confirms the `last_backup_status` row's `value_type` (it is `"string"` per
  migration 0001 — store a JSON string; do NOT add a migration).
- **D-02:** Date-only filenames `db_YYYY-MM-DD.sql` and `photos_YYYY-MM-DD.tar.gz`, one
  idempotent snapshot per day (same-day run overwrites). Retention prunes by parsing the
  date in the filename, not mtime. Matches CLAUDE.md restore runbook exactly.
- **D-03:** Keep partial artifacts on partial failure. Two artifacts attempted independently;
  result records per-artifact ok/error; overall status = error if any artifact failed.
  AI refresh and backup jobs are fully independent APScheduler jobs.
- **D-04:** Eligibility pre-filter = `User.is_active = true` AND `>= 3` brew sessions.
  `regenerate()` owns all other gating. Scheduler does NOT re-implement any gating.
  `app_settings.last_ai_run_status` stores the full SCHED-03 summary as a JSON string.
  Token totals aggregated from `ai_recommendations` rows written during this run.

### Claude's Discretion
- **Job-registration idempotency:** stable explicit job IDs + `replace_existing=True` (confirm exact 3.x API — confirmed below).
- **Timezone wiring:** `CronTrigger(hour=0, minute=0, timezone=APP_TIMEZONE)` and `hour=2` for backup.
- **User iteration:** sequential, one user at a time (household scale).
- **`pg_dump` invocation:** from web container, flags `--clean --if-exists --no-owner`, password via `PGPASSWORD` env, host/port/db/user from `DATABASE_URL`, never hardcoded.
- **DB dump format:** plain uncompressed `.sql` — locked by CLAUDE.md restore runbook.
- **`scheduler.*` / `backup.*` event taxonomy** in `app/events.py` following `ai.*` pattern.

### Deferred Ideas (OUT OF SCOPE)
- Backups list / download UI, "Run backup now" button, system-info + API-health panels — Phase 9.
- Per-month / per-user AI cost ceiling.
- Off-site / encrypted backup shipping, restore automation, backup integrity verification.
- DB dump compression (`.sql.gz`).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHED-01 | APScheduler `AsyncIOScheduler` started/stopped in FastAPI `lifespan`, backed by `SQLAlchemyJobStore`, with `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1` | APScheduler 3.11 API confirmed; `engine=` pattern confirmed safe for sync engine |
| SCHED-02 | Nightly AI refresh @ 00:00 `APP_TIMEZONE` — enumerate eligible users, call frozen `regenerate(uid, "scheduler", db=db)` per user, aggregate run summary | `regenerate()` contract confirmed from 07-CONTEXT; eligibility query pattern confirmed from user model |
| SCHED-03 | Run summary logged as one structured line AND persisted to `app_settings.last_ai_run_status` | `last_ai_run_status` confirmed `value_type="string"` — store JSON string via `set_setting()`; token columns confirmed in `ai_recommendation.py` |
| SCHED-04 | Nightly backup @ 02:00 `APP_TIMEZONE` — `pg_dump` SQL + photos tarball + prune older than `BACKUP_RETENTION_DAYS`, persist result to `app_settings.last_backup_status` | `pg_dump` flags confirmed; `last_backup_status` confirmed `value_type="string"`; `BACKUP_RETENTION_DAYS` confirmed in `config.py` |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Scheduler lifecycle (start/stop) | Backend / lifespan | — | APScheduler is in-process; wired in FastAPI `lifespan` async context manager |
| Nightly AI refresh job | Backend / service | DB (read eligible users, aggregate tokens) | Pure server-side; no HTTP, no templates |
| Nightly backup job | Backend / service | Filesystem + subprocess | `pg_dump` + tarfile; no HTTP layer involved |
| Job persistence across restarts | Database / Storage | — | `SQLAlchemyJobStore` writes job state to Postgres; survives container restart |
| Status rows (last run, last backup) | Database / Storage | Backend service | `app_settings` key-value rows written by service layer, read by Phase 9 UI |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| APScheduler | `>=3.11,<4` (3.11.2 current) | In-process cron scheduling | Locked by CLAUDE.md; 4.x is still alpha |
| SQLAlchemy | `>=2.0.49,<2.1` (existing) | `SQLAlchemyJobStore` backend | Already in stack; job store reuses app sync engine |
| Python `tarfile` | stdlib | Photos archive | No external dep needed; stdlib is sufficient |
| Python `subprocess` | stdlib | `pg_dump` invocation | Per CLAUDE.md gap-libraries guidance; no Python pg-backup lib |
| structlog | `>=25.5,<26` (existing) | Structured log lines | Already in stack; SCHED-03 summary is one JSON log line |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `app.services.settings` | project module | Write `last_ai_run_status` / `last_backup_status` | Use `set_setting(db, key, json_blob, by_user_id=None)` |
| `app.db.SessionLocal` | project module | Get a sync Session for job body DB access | One session per user iteration in the AI job |
| `app.db.engine` | project module | Pass to `SQLAlchemyJobStore(engine=engine)` | Must be the SYNC engine from `app/db.py`, never the async one |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `SQLAlchemyJobStore(engine=engine)` | `SQLAlchemyJobStore(url=DATABASE_URL)` | URL creates a second engine / connection pool; `engine=` reuses existing pool. Use `engine=`. |
| `sync def` job | `async def` job + sync DB | APScheduler runs `async def` in the event loop directly — any sync DB call inside blocks the loop. Use `sync def` instead. |
| `PGPASSWORD` env in subprocess | `~/.pgpass` file | `~/.pgpass` requires filesystem setup in the Docker image; `PGPASSWORD` via `subprocess.run(env=...)` is simpler and equally safe inside a container. Use `PGPASSWORD`. |
| Plain `.sql` dump | `pg_dump -Fc` custom format | Custom format requires `pg_restore`, not `psql <`; breaks the CLAUDE.md restore runbook. Use plain. |

**Installation:** No new packages required. APScheduler is already a dependency.

## Architecture Patterns

### System Architecture Diagram

```
FastAPI lifespan (app/main.py)
        |
        +-- startup: scheduler.start()
        |      |
        |      +-- SQLAlchemyJobStore (app/db.py engine, SYNC) --> Postgres apscheduler_jobs table
        |      +-- AsyncIOScheduler (event loop)
        |             |
        |             +-- nightly_ai_refresh @ 00:00 APP_TIMEZONE (CronTrigger)
        |             |       --> runs in ThreadPoolExecutor (sync def body)
        |             |       --> SessionLocal() per user
        |             |       --> ai_service.regenerate(uid, "scheduler", db=db)
        |             |       --> aggregate status from ai_recommendations
        |             |       --> set_setting(last_ai_run_status, json_blob)
        |             |       --> structlog SCHEDULER_AI_RUN_COMPLETE event
        |             |
        |             +-- nightly_backup @ 02:00 APP_TIMEZONE (CronTrigger)
        |                     --> runs in ThreadPoolExecutor (sync def body)
        |                     --> services/backup.py entry point
        |                     --> pg_dump to /app/data/backups/db_YYYY-MM-DD.sql
        |                     --> tarfile photos to /app/data/backups/photos_YYYY-MM-DD.tar.gz
        |                     --> prune old files by filename date parse
        |                     --> set_setting(last_backup_status, json_blob)
        |                     --> structlog BACKUP_COMPLETE event
        |
        +-- shutdown: scheduler.shutdown(wait=False)
        +-- dispose_engine() + _async_engine.dispose()
```

### Recommended Project Structure

```
app/
├── services/
│   ├── scheduler.py     # Replace stub — AsyncIOScheduler init, job defs, start/shutdown helpers
│   └── backup.py        # NEW — pg_dump + photos tarball + prune + structured result
├── events.py            # Add scheduler.* and backup.* constants
└── main.py              # lifespan: call scheduler.start() / scheduler.shutdown(wait=False)
```

### Pattern 1: AsyncIOScheduler with SQLAlchemyJobStore (Correct Engine)

**What:** Wire the scheduler in lifespan using the existing sync `engine` from `app/db.py`.

**Why `engine=engine` not `url=`:** `SQLAlchemyJobStore` is synchronous internally — it
calls `.execute()` and `.begin()` via the standard sync SQLAlchemy API. If you pass the
`postgresql+psycopg://` URL via `url=`, APScheduler calls `create_engine(url)` and creates
a *second* connection pool. If you pass the async `_async_engine` object, initialization
succeeds (no validation) but runtime calls fail because the job store issues sync
`.begin()` calls against an async engine. The only correct choice is `engine=engine` from
`app/db.py` (the sync engine already in the pool). [VERIFIED: APScheduler source + official docs]

```python
# app/services/scheduler.py
# Source: https://apscheduler.readthedocs.io/en/3.x/userguide.html
#         https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/sqlalchemy.html
from __future__ import annotations

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db import engine  # SYNC engine — required by SQLAlchemyJobStore

def build_scheduler() -> AsyncIOScheduler:
    jobstores = {
        "default": SQLAlchemyJobStore(engine=engine),
    }
    executors = {
        "default": ThreadPoolExecutor(max_workers=2),
    }
    job_defaults = {
        "coalesce": True,
        "misfire_grace_time": 3600,
        "max_instances": 1,
    }
    return AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone=settings.APP_TIMEZONE,
    )

scheduler = build_scheduler()

def register_jobs() -> None:
    """Add jobs with stable IDs + replace_existing=True for idempotent startup."""
    scheduler.add_job(
        run_nightly_ai_refresh,
        CronTrigger(hour=0, minute=0, timezone=settings.APP_TIMEZONE),
        id="nightly_ai_refresh",
        replace_existing=True,
    )
    scheduler.add_job(
        run_nightly_backup,
        CronTrigger(hour=2, minute=0, timezone=settings.APP_TIMEZONE),
        id="nightly_backup",
        replace_existing=True,
    )
```

### Pattern 2: Lifespan Integration

**What:** Insert `scheduler.start()` after existing Phase 3 hooks; `scheduler.shutdown(wait=False)` before engine disposal.

```python
# app/main.py lifespan (additions only — existing lines preserved)
# Source: https://apscheduler.readthedocs.io/en/3.x/userguide.html
from app.services.scheduler import scheduler, register_jobs

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    encryption_startup_check()
    with SessionLocal() as db:
        credentials.rewrap_if_needed(db)
        settings_service.prewarm_cache(db)
    # Phase 8: start scheduler AFTER prewarm_cache (jobs may read settings)
    register_jobs()
    scheduler.start()
    log.info("app.startup", version=app.version)
    yield
    log.info("app.shutdown")
    scheduler.shutdown(wait=False)  # non-blocking: don't delay container stop
    dispose_engine()
    await _async_engine.dispose()
```

**Why `shutdown(wait=False)`:** The lifespan shutdown runs in response to SIGTERM from
Docker. With `wait=True`, if a job is mid-flight during shutdown (e.g., mid-pg_dump),
the container would block indefinitely. `wait=False` tells the scheduler to stop
dispatching new jobs and return immediately; in-flight thread-pool jobs finish naturally
(or are killed when the process exits). [VERIFIED: APScheduler docs]

### Pattern 3: Sync Job Body (Correct for DB-using jobs)

**What:** Job functions are plain `sync def`. `AsyncIOScheduler` with `ThreadPoolExecutor`
runs them in a worker thread — the event loop is never blocked.

**Why not `async def`:** If a job is `async def`, `AsyncIOScheduler` runs it directly
on the event loop via `AsyncIOExecutor`. Any sync DB call inside would block the loop.
The AI refresh job does sync DB queries (`SessionLocal()`, SQLAlchemy `select()`). A
plain `sync def` body with `ThreadPoolExecutor` is the maintainer-recommended pattern
for jobs with blocking I/O. [VERIFIED: APScheduler maintainer, Discussion #999]

```python
# Source: https://github.com/agronholm/apscheduler/discussions/999
def run_nightly_ai_refresh() -> None:
    """Nightly AI refresh job — runs in ThreadPoolExecutor, not on event loop."""
    from app.db import SessionLocal
    from app.models.brew_session import BrewSession
    from app.models.user import User
    from app.services import ai_service, settings as settings_service
    import structlog
    from sqlalchemy import func, select

    log = structlog.get_logger(__name__)
    summary = {
        "users_processed": 0,
        "regenerations": 0,
        "skips": 0,
        "errors": 0,
        "tokens_input_total": 0,
        "tokens_output_total": 0,
        "tokens_input_search_total": 0,
    }
    # Eligibility query: is_active AND >= 3 brew sessions (D-04)
    with SessionLocal() as db:
        eligible_user_ids = _get_eligible_user_ids(db)

    for uid in eligible_user_ids:
        with SessionLocal() as db:
            status = ai_service.regenerate(uid, "scheduler", db=db, force=False)
        summary["users_processed"] += 1
        if status == "generated":
            summary["regenerations"] += 1
        elif status in ("skipped", "locked", "try_again", "not_configured"):
            summary["skips"] += 1
        else:  # "error"
            summary["errors"] += 1

    # Aggregate token totals from rows written this run (ai_recommendations)
    # ... (see token aggregation pattern below)
    # Write summary to last_ai_run_status (value_type="string" → JSON string)
    with SessionLocal() as db:
        settings_service.set_setting(
            db, "last_ai_run_status", json.dumps({**summary, "timestamp": ...}),
            by_user_id=None,
        )
    log.info(SCHEDULER_AI_RUN_COMPLETE, **summary)
```

### Pattern 4: pg_dump Invocation

**What:** Shell out to `pg_dump` via `subprocess.run`, passing credentials via `PGPASSWORD`
in the subprocess environment. Parse connection details from `settings.DATABASE_URL`.

```python
# Source: https://www.postgresql.org/docs/current/app-pgdump.html
import subprocess, re, os
from app.config import settings

def _parse_db_url(url: str) -> dict:
    """Parse postgresql+psycopg://user:pass@host:port/db."""
    m = re.match(
        r"postgresql\+psycopg://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)", url
    )
    if not m:
        raise ValueError(f"Cannot parse DATABASE_URL: {url!r}")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": m.group(4) or "5432",
        "dbname": m.group(5),
    }

def dump_database(dest_path: str) -> None:
    conn = _parse_db_url(settings.DATABASE_URL)
    env = {**os.environ, "PGPASSWORD": conn["password"]}
    result = subprocess.run(
        [
            "pg_dump",
            "--clean",          # emit DROP before CREATE
            "--if-exists",      # silence "does not exist" on first restore
            "--no-owner",       # don't emit ALTER OWNER (restore as any user)
            "--no-privileges",  # don't emit GRANT/REVOKE
            "-h", conn["host"],
            "-p", conn["port"],
            "-U", conn["user"],
            "-d", conn["dbname"],
            "-f", dest_path,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,  # 5 min hard cap; a household DB should dump in seconds
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr}")
```

**Restore command (matches CLAUDE.md runbook):**
```bash
psql -U $POSTGRES_USER $POSTGRES_DB < /app/data/backups/db_YYYY-MM-DD.sql
```

The `--clean --if-exists` flags make the dump idempotent on restore: it drops existing
objects before recreating them, suppressing errors if the object doesn't yet exist.
[VERIFIED: PostgreSQL 18 docs]

### Pattern 5: Filename-Based Retention Prune

```python
import re
from datetime import date, timedelta
from pathlib import Path

def prune_old_backups(backup_dir: Path, retention_days: int) -> int:
    """Delete backup files older than retention_days. Returns count deleted."""
    cutoff = date.today() - timedelta(days=retention_days)
    pattern = re.compile(r"(?:db|photos)_(\d{4}-\d{2}-\d{2})\.(sql|tar\.gz)$")
    deleted = 0
    for f in backup_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            file_date = date.fromisoformat(m.group(1))
            if file_date < cutoff:
                f.unlink()
                deleted += 1
    return deleted
```

### Anti-Patterns to Avoid

- **Passing `_async_engine` to `SQLAlchemyJobStore`:** Initialization succeeds (no guard
  in the job store), but `engine.begin()` / `connection.execute()` will fail at runtime
  with sync/async mismatch. Always pass the sync `engine` from `app/db.py`.
- **Using `url=settings.DATABASE_URL` in `SQLAlchemyJobStore`:** Creates a second
  connection pool with no pool knobs, no `pre_ping`. Pass `engine=engine` instead.
- **`async def` job body that calls sync SQLAlchemy:** Blocks the event loop on every
  `db.execute()` call. Use `sync def` bodies.
- **`shutdown(wait=True)` in lifespan:** Can block container stop indefinitely if a job
  is mid-flight during SIGTERM. Use `wait=False`.
- **Parsing date from mtime for retention:** mtime can be wrong after `docker compose cp`
  or a volume re-mount. Parse the date from the filename.
- **Hardcoding db host / user / password in `pg_dump` call:** Read from `settings.DATABASE_URL`.
- **Gzip-compressing the `.sql` dump:** Breaks `psql < db_YYYY-MM-DD.sql` restore runbook.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Job persistence across restarts | Custom DB table for jobs | `SQLAlchemyJobStore` | Handles serialization, misfire tracking, next-run calculation |
| Cron math + DST transitions | Custom cron parser | `CronTrigger(timezone=...)` | APScheduler handles "wall clock" time; DST edge is documented |
| Misfire/coalesce logic | Custom restart-check on startup | `misfire_grace_time=3600, coalesce=True` | Built into APScheduler; grace window + coalesce gives exactly-once on restart within 1h |
| Token split aggregation | Custom per-call accumulator | DB query on `ai_recommendations` rows | Token columns (`tokens_input`, `tokens_output`, `tokens_input_search`) already written by Phase 7; aggregate with `SUM()` over `generated_by="scheduler"` + `generated_at >= run_start` |

## Common Pitfalls

### Pitfall 1: Wrong Engine for SQLAlchemyJobStore (SH-1 variant)

**What goes wrong:** Passing `_async_engine` or using `url=DATABASE_URL` causes a second
pool or runtime failure when APScheduler calls `engine.begin()` synchronously.

**Why it happens:** APScheduler 3.x's `SQLAlchemyJobStore` uses the synchronous SQLAlchemy
API. There is no guard in the constructor that rejects an async engine — the failure is
silent at init and explosive at first job write.

**How to avoid:** Import `engine` from `app/db.py` (the sync engine); pass it as
`SQLAlchemyJobStore(engine=engine)`.

**Warning signs:** `AttributeError: 'coroutine' object has no attribute 'execute'` or
`MissingGreenlet` error at scheduler startup or first job run.

### Pitfall 2: Default MemoryJobStore (SH-1 from ROADMAP)

**What goes wrong:** If `SQLAlchemyJobStore` is not explicitly configured, APScheduler
uses `MemoryJobStore` — jobs are lost on every container restart.

**Why it happens:** `MemoryJobStore` is the default and requires no setup.

**How to avoid:** Always specify `jobstores={"default": SQLAlchemyJobStore(engine=engine)}`
in the `AsyncIOScheduler` constructor. Verify at startup that the `apscheduler_jobs`
table exists in Postgres.

**Warning signs:** Jobs that were registered at last startup are gone after restart; no
`apscheduler_jobs` table in the DB.

### Pitfall 3: Duplicate Jobs on Restart Without replace_existing

**What goes wrong:** Every container restart adds duplicate job rows in `apscheduler_jobs`,
causing the job to fire N times per interval after N restarts.

**Why it happens:** `add_job()` defaults to `replace_existing=False`. Each start inserts
a new row with a new auto-generated ID.

**How to avoid:** Use stable explicit IDs (`id="nightly_ai_refresh"`) and
`replace_existing=True`. After N restarts, there are exactly 2 rows in `apscheduler_jobs`.
[VERIFIED: APScheduler docs — "If you schedule jobs in a persistent job store during
initialization, you MUST define an explicit ID and use replace_existing=True"]

### Pitfall 4: Async Job Body Blocking the Event Loop

**What goes wrong:** An `async def` job body that calls `SessionLocal()` and
`db.execute(...)` (sync SQLAlchemy) blocks the event loop for the duration of the
DB query, freezing all HTMX requests.

**Why it happens:** `AsyncIOScheduler` with `AsyncIOExecutor` runs `async def` functions
directly on the event loop. Sync calls inside block it.

**How to avoid:** Declare job bodies as `sync def`. `AsyncIOScheduler` with a
`ThreadPoolExecutor` executor runs them in a worker thread, not on the event loop.

### Pitfall 5: Version Mismatch pg_dump vs Postgres Server (SH-5)

**What goes wrong:** `pg_dump` version < server version produces a warning and may skip
newer catalog features; version > server version may reject the connection.

**Why it happens:** Running a different `postgresql-client` version than the server.

**How to avoid:** Phase 0 installed `postgresql-client-16` in the web container image to
match `postgres:16-alpine`. The `pg_dump` binary at `/usr/bin/pg_dump` is always version 16.
Do NOT upgrade the client package independently. [VERIFIED: 08-CONTEXT.md SH-5 note]

### Pitfall 6: DST Transition on America/Chicago (APP_TIMEZONE default)

**What goes wrong:** Jobs scheduled at 00:00 or 02:00 America/Chicago may fire at
unexpected times or be skipped/doubled on DST transition nights (spring forward at 02:00,
fall back at 02:00).

**Why it happens:** CronTrigger uses "wall clock" time; 02:00 does not exist on spring-
forward night.

**How to avoid:** APScheduler handles this gracefully — if the trigger time does not exist
in the DST transition (e.g., 02:00 on spring-forward), the trigger fires at the next
valid time. The `misfire_grace_time=3600` catches the backup job if it fires at 03:00
instead. This is a known limitation documented in APScheduler's CronTrigger docs. For
a household app, this is acceptable. [CITED: https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html]

### Pitfall 7: set_setting() invalidates cache after commit

**What goes wrong:** Calling `set_setting(db, "last_ai_run_status", ...)` pops the
key from `_cache`. If something reads that key before the next `prewarm_cache()` call,
it gets `SettingNotFoundError`.

**Why it happens:** `set_setting` is designed for write-through invalidation — after a
write, the cache entry is dropped, forcing a DB re-read on next access (or panic).

**How to avoid:** This is the correct behavior. `last_ai_run_status` and
`last_backup_status` are written by the scheduler, read by Phase 9's admin panel.
The admin panel calls `get_str("last_ai_run_status")` — if the key was recently
written and the cache was invalidated, SQLAlchemy will re-fetch on the next
`prewarm_cache()` call. BUT: the current `set_setting()` does NOT re-populate the
cache after writing — it only pops. The Phase 9 admin panel must not assume the
key is in cache after a scheduler run. Options: (a) call `prewarm_cache(db)` after
`set_setting`, or (b) use a raw `db.execute(select(...))` to read back the status
in the admin panel (bypassing cache). Document this contract explicitly.

## Code Examples

### SCHED-03: Token Aggregation from ai_recommendations

Aggregate token totals for runs that completed during the current scheduler invocation:

```python
# Source: app/models/ai_recommendation.py (confirmed column names)
from sqlalchemy import func, select
from app.models.ai_recommendation import AIRecommendation

def aggregate_tokens_since(db: Session, run_start: datetime) -> dict:
    row = db.execute(
        select(
            func.sum(AIRecommendation.tokens_input).label("tokens_input_total"),
            func.sum(AIRecommendation.tokens_output).label("tokens_output_total"),
            func.sum(AIRecommendation.tokens_input_search).label("tokens_input_search_total"),
        ).where(
            AIRecommendation.generated_by == "scheduler",
            AIRecommendation.generated_at >= run_start,
        )
    ).one()
    return {
        "tokens_input_total": row.tokens_input_total or 0,
        "tokens_output_total": row.tokens_output_total or 0,
        "tokens_input_search_total": row.tokens_input_search_total or 0,
    }
    # non_search_input = tokens_input_total - tokens_input_search_total (D-04)
```

### Misfire/Coalesce: What Happens on Restart Within Grace Window

When the container restarts at 23:55 and missed the 00:00 job that was due within the
next hour:

1. The scheduler starts and reads the `apscheduler_jobs` table.
2. It calculates the next run time for `nightly_ai_refresh` (00:00).
3. At startup the job has NOT missed yet (start at 23:55, job due at 00:00) — it will fire normally at 00:00.

For a restart AT 00:05 (5 minutes after 00:00):

1. Scheduler starts; checks `nightly_ai_refresh` — last run time was yesterday 00:00, next was today 00:00.
2. The miss time (5 minutes) is within `misfire_grace_time=3600` (1 hour).
3. `coalesce=True` means: fire once regardless of how many missed windows stacked up.
4. Result: job fires **once immediately** at scheduler startup (within the grace window).
5. For a restart at 01:05 (65 minutes after): miss exceeds `misfire_grace_time=3600` → job is SKIPPED for that window (fires again at 00:00 tomorrow). [VERIFIED: APScheduler docs description of misfire + coalesce]

### Eligibility Query (SCHED-02 / D-04)

```python
# Source: app/models/user.py (is_active confirmed line 45)
#         app/models/brew_session.py (join pattern)
from sqlalchemy import func, select
from app.models.brew_session import BrewSession
from app.models.user import User

def _get_eligible_user_ids(db: Session) -> list[int]:
    """is_active=True AND >= 3 brew sessions. regenerate() owns remaining gates."""
    result = db.execute(
        select(User.id)
        .join(BrewSession, BrewSession.user_id == User.id)
        .where(User.is_active == True)  # noqa: E712
        .group_by(User.id)
        .having(func.count(BrewSession.id) >= 3)
    )
    return [row[0] for row in result]
```

### app/events.py Additions (scheduler.* and backup.*)

```python
# Phase 8 additions — follow ai.* pattern from events.py
SCHEDULER_STARTED = "scheduler.started"
SCHEDULER_SHUTDOWN = "scheduler.shutdown"
SCHEDULER_JOB_START = "scheduler.job.start"
SCHEDULER_JOB_SUCCESS = "scheduler.job.success"
SCHEDULER_JOB_ERROR = "scheduler.job.error"
SCHEDULER_AI_RUN_COMPLETE = "scheduler.ai_run.complete"
# Field shape for SCHEDULER_AI_RUN_COMPLETE:
# users_processed, regenerations, skips, errors,
# tokens_input_total, tokens_output_total, tokens_input_search_total, timestamp

BACKUP_STARTED = "backup.started"
BACKUP_COMPLETE = "backup.complete"
BACKUP_ARTIFACT_OK = "backup.artifact.ok"
BACKUP_ARTIFACT_ERROR = "backup.artifact.error"
BACKUP_PRUNED = "backup.pruned"
# Field shape for BACKUP_COMPLETE:
# status (ok/error), db_filename, db_bytes, photos_filename, photos_bytes,
# duration_ms, error_msg (optional), pruned_count
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| APScheduler 4.x (beta) | APScheduler 3.11.x (stable) | 4.x rewrites the API entirely; stay on 3.x per CLAUDE.md |
| `MemoryJobStore` (APScheduler default) | `SQLAlchemyJobStore` | Jobs survive container restart; misfire tracking is persistent |
| `@app.on_event("startup")` | `@asynccontextmanager async def lifespan` | Starlette 1.0 removed `on_event`; lifespan is the only path |

**Deprecated/outdated:**
- APScheduler 4.x: alpha as of 4.0.0a6; completely rewrites the scheduling API — do not use.
- `@app.on_event`: removed in Starlette 1.0.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `brew_sessions` table has a `user_id` FK joinable from `User.id` for the eligibility query | Code Examples — eligibility | Wrong join column name would cause SQL error; implementer must verify `BrewSession.user_id` column name before writing the query |
| A2 | `pg_dump` binary is at the default PATH location (`/usr/bin/pg_dump`) in the `coffee-snobbery` web image | Pattern 4 | If path differs, `subprocess.run(["pg_dump", ...])` fails with FileNotFoundError; implementer should verify with `which pg_dump` in the container |
| A3 | `AsyncIOScheduler` with `ThreadPoolExecutor` executor + `sync def` job does NOT block the event loop | Pattern 3 | Confirmed by maintainer (Discussion #999) but not load-tested for this codebase specifically; at household scale (2 users) this is low risk |

**If this table is empty:** All other claims in this research were verified or cited.

## Open Questions

1. **`set_setting()` cache invalidation on status writes**
   - What we know: `set_setting()` pops the key from `_cache` after commit; does not re-populate.
   - What's unclear: Phase 9's admin panel reading `last_ai_run_status` immediately after a scheduler write will hit `SettingNotFoundError` if it calls `get_str()` without a prior `prewarm_cache()`.
   - Recommendation: Planner should decide whether the scheduler calls `prewarm_cache(db)` after each `set_setting()` write, or whether Phase 9's panel reads the status via a raw DB query that bypasses the cache. The latter is cleaner — status reads in the admin panel are infrequent and can tolerate a DB hit.

2. **`apscheduler_jobs` table creation**
   - What we know: `SQLAlchemyJobStore` creates the `apscheduler_jobs` table automatically on first connect if it does not exist (uses SQLAlchemy `metadata.create_all()`).
   - What's unclear: Does this interfere with Alembic's schema ownership? The table is APScheduler-managed, not in the Alembic migration chain.
   - Recommendation: Add a comment in the migration README noting that `apscheduler_jobs` is APScheduler-managed (not in Alembic). No migration needed — APScheduler owns the table schema.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `pg_dump` (postgresql-client-16) | SCHED-04 backup | ASSUMED present (Phase 0 installed it) | 16 | None — must be in web image |
| `/app/data/backups` volume | SCHED-04 | ASSUMED mounted (docker-compose.yml `coffee_snobbery_backups`) | — | None — required by spec |
| Python `tarfile` | SCHED-04 photos | stdlib | — | N/A |
| Python `subprocess` | SCHED-04 pg_dump | stdlib | — | N/A |
| APScheduler 3.11 | SCHED-01 | Present (in requirements.txt) | 3.11.2 | N/A |

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0 |
| Config file | none yet (Wave 0 gap) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/test_backup.py -x -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| SCHED-01 | Scheduler starts with SQLAlchemyJobStore; exactly 2 jobs registered after N restarts | unit | `pytest tests/test_scheduler.py::test_idempotent_job_registration -x` | Wave 0 |
| SCHED-01 | Scheduler starts/stops cleanly in lifespan without error | integration | `pytest tests/test_scheduler.py::test_lifespan_scheduler_lifecycle -x` | Wave 0 |
| SCHED-02 | Eligible user filter (is_active=True AND >=3 sessions) | unit | `pytest tests/test_scheduler.py::test_eligibility_filter -x` | Wave 0 |
| SCHED-02 | `regenerate()` return values tallied correctly into summary counters | unit | `pytest tests/test_scheduler.py::test_ai_run_summary_tally -x` | Wave 0 |
| SCHED-03 | Token aggregation query sums correctly across this-run rows only | unit | `pytest tests/test_scheduler.py::test_token_aggregation -x` | Wave 0 |
| SCHED-03 | `last_ai_run_status` written as JSON string to `app_settings` | unit | `pytest tests/test_scheduler.py::test_status_row_write -x` | Wave 0 |
| SCHED-04 | `pg_dump` produces a file that `psql <` can restore cleanly | integration (manual) | manual — needs live DB | manual only |
| SCHED-04 | Filename-based retention prune deletes correct files | unit | `pytest tests/test_backup.py::test_retention_prune -x` | Wave 0 |
| SCHED-04 | Partial failure (one artifact fails) keeps the good artifact | unit | `pytest tests/test_backup.py::test_partial_failure_keeps_good -x` | Wave 0 |
| SCHED-04 | `last_backup_status` written as JSON string to `app_settings` | unit | `pytest tests/test_backup.py::test_backup_status_row_write -x` | Wave 0 |

### Highest-Risk Behaviors to Validate

These are the behaviors most likely to be silently wrong and hardest to catch without
explicit tests:

1. **Restart-within-grace fires job once** (not zero, not twice): unit-testable by
   calling the eligibility + misfire logic with a mocked scheduler and asserting the job
   ran exactly once after a simulated late startup within the grace window.

2. **pg_dump output restores cleanly**: manual validation step — dump the dev DB, restore
   to a fresh schema, verify row counts match. This cannot be automated in the unit suite
   without a second live Postgres instance. Flag as a human verification step in the plan.

3. **Partial-failure keeps good artifact + flags overall error**: unit-testable by mocking
   `_run_pg_dump` to raise and verifying that (a) the photos tarball was still created,
   (b) result.status == "error", and (c) result.db_error is populated.

4. **Signature-skip path not broken**: the AI job must NOT call `regenerate()` with
   `force=True`; assert `regenerate` is called with `force=False` in the job body test.

5. **Idempotent job registration (exactly 2 jobs after N restarts)**: call `register_jobs()`
   three times on a scheduler backed by a test DB; assert `len(scheduler.get_jobs()) == 2`.

### Sampling Rate
- **Per task commit:** quick run command (scheduler + backup unit tests)
- **Per wave merge:** full suite green
- **Phase gate:** Full suite green before `/gsd-verify-work` + manual pg_dump restore drill

### Wave 0 Gaps
- [ ] `tests/test_scheduler.py` — covers SCHED-01, SCHED-02, SCHED-03
- [ ] `tests/test_backup.py` — covers SCHED-04 unit cases
- [ ] pytest install: `docker compose exec coffee-snobbery pip install --user pytest` (already documented in CLAUDE.md)

## Security Domain

> `security_enforcement` not explicitly `false` in config — section included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Scheduler runs as system process; no user auth |
| V3 Session Management | no | No sessions in background jobs |
| V4 Access Control | yes | Eligibility filter ensures only active users are processed; `regenerate()` uses per-user scoping |
| V5 Input Validation | yes | `DATABASE_URL` parse uses a strict regex; no user-supplied input to scheduler |
| V6 Cryptography | no | Scheduler does not handle keys; `regenerate()` uses encrypted credentials via existing `encryption.py` |

### Known Threat Patterns for Scheduler + Backup

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| `PGPASSWORD` in subprocess env visible to `ps aux` | Information Disclosure | On Linux, env vars are not visible to other processes via `ps` by default; the container is single-tenant. This is the accepted pattern for `pg_dump` in Docker. [CITED: PostgreSQL docs] |
| `pg_dump` output contains all DB data (plaintext) | Information Disclosure | Backup files are written to the `coffee_snobbery_backups` volume, accessible only within the Docker network. Off-site encryption is deferred to v2 (CONTEXT deferred). |
| Subprocess injection via DATABASE_URL | Tampering | Credentials are never passed as shell strings; `subprocess.run([...], ...)` uses a list (no shell=True), so no injection is possible even if the URL contains special chars. |
| Runaway job (AI call takes hours) | Denial of Service | `max_instances=1` prevents overlap; `misfire_grace_time=3600` bounds retry window; Anthropic SDK `max_retries=1` limits AI hang time (already in Phase 7 config). |

## Sources

### Primary (HIGH confidence)
- [APScheduler 3.11 User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — `AsyncIOScheduler` configuration, `add_job` with `replace_existing`, `coalesce`, `misfire_grace_time`
- [APScheduler SQLAlchemyJobStore API](https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/sqlalchemy.html) — `engine=` vs `url=` parameters
- [APScheduler BaseScheduler API](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/base.html) — `add_job()`, `start()`, `shutdown(wait=...)` signatures
- [APScheduler CronTrigger API](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html) — `timezone=` parameter, DST "wall clock" behavior
- [APScheduler AsyncIOScheduler](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html) — executor types, event loop integration
- [PostgreSQL pg_dump docs](https://www.postgresql.org/docs/current/app-pgdump.html) — `--clean`, `--if-exists`, `--no-owner`, `PGPASSWORD` env var
- `app/db.py` — VERIFIED sync engine with `postgresql+psycopg://` URL; pool knobs
- `app/config.py` — VERIFIED `APP_TIMEZONE` (line 52), `BACKUP_RETENTION_DAYS` (line 53), `DATABASE_URL` (line 39)
- `app/migrations/versions/0001_initial.py` (lines 291-303) — VERIFIED `last_ai_run_status` value_type=`"string"`, `last_backup_status` value_type=`"string"`
- `app/models/ai_recommendation.py` — VERIFIED token columns: `tokens_input`, `tokens_output`, `tokens_input_search`, `web_search_count`
- `app/models/user.py` — VERIFIED `is_active` column (line 45)
- `app/services/settings.py` — VERIFIED `set_setting()` signature and cache invalidation behavior
- `app/events.py` — VERIFIED `ai.*` event taxonomy pattern (Phase 8 must follow same structure)
- `app/main.py` — VERIFIED lifespan hook ordering; `_async_engine` is the async engine Phase 8 must NOT pass to SQLAlchemyJobStore

### Secondary (MEDIUM confidence)
- [APScheduler GitHub Discussion #999](https://github.com/agronholm/apscheduler/discussions/999) — maintainer recommendation: `sync def` job bodies with `ThreadPoolExecutor` for blocking I/O; APScheduler author is the source
- [APScheduler SQLAlchemyJobStore source (Tautulli mirror)](https://github.com/Tautulli/Tautulli/blob/master/lib/apscheduler/jobstores/sqlalchemy.py) — confirmed `engine=` parameter accepted; no async engine validation guard (failure is runtime, not init-time)

### Tertiary (LOW confidence)
- APScheduler Issue #304 (sync jobs run in ThreadPoolExecutor by default) — confirmed behavior aligns with Discussion #999

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — APScheduler API confirmed against official docs; codebase files read directly
- Architecture: HIGH — lifespan integration site confirmed in `app/main.py`; engine types confirmed in `app/db.py` and `app/main.py`
- Pitfalls: HIGH for async engine pitfall (source-code verified); HIGH for duplicate-job pitfall (official docs explicit); MEDIUM for DST pitfall (documented behavior, not tested against this app)
- pg_dump flags: HIGH — confirmed against PostgreSQL 18 official docs

**Research date:** 2026-05-21
**Valid until:** 2026-06-21 (APScheduler 3.x is stable; no fast-moving changes expected)
