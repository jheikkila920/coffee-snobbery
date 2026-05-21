---
phase: 08-scheduler-backups
reviewed: 2026-05-21T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - app/events.py
  - app/services/backup.py
  - app/services/scheduler.py
  - app/main.py
  - tests/conftest.py
  - tests/test_backup.py
  - tests/test_scheduler.py
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-21
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 8 wires APScheduler (two nightly jobs) plus a pg_dump + photos-tarball backup service. The headline concerns from the brief check out **mostly clean**:

- **Subprocess injection (T-08-04):** `_run_pg_dump` uses an argv LIST with `shell=False` — shell metacharacters in `DATABASE_URL` cannot inject. Good.
- **PGPASSWORD handling (T-08-03):** passed via the `env` dict, never as a CLI arg, never logged. Good.
- **sync/async bridge:** `run_nightly_ai_refresh` is a plain `sync def` running in `ThreadPoolExecutor`, and it bridges to the async `regenerate()` via `asyncio.run()` per call. This is the correct pattern — the event loop is never blocked, and a fresh loop is opened/torn down per call.
- **SQLAlchemyJobStore engine:** correctly uses the SYNC `engine` from `app.db`, not the async engine or a second pool. Good.
- **AI cost-control invariant:** `regenerate(uid, "scheduler", db=db, force=False)` is called with `force=False`; the scheduler re-implements NO gating (cold-start, signature, locks, throttle all stay inside `regenerate`). The `mock_regenerate` fixture even asserts `force is False` on every call. Invariant intact.

However, the **`_parse_db_url` regex is the weak point** and contains a real correctness/availability defect (CR-01): it silently mishandles passwords containing reserved URL characters and rejects several legal Postgres URL shapes, which would make the nightly DB backup fail with a misleading error. There are also several robustness and correctness warnings around the AI-run token-aggregation clock source, prune ordering, broad exception swallowing in the backup path, and a couple of test gaps where the "scheduler tally" test re-implements the production logic instead of exercising it.

## Critical Issues

### CR-01: `_parse_db_url` regex breaks on valid passwords / URL shapes, silently failing the nightly backup

**File:** `app/services/backup.py:105-121`
**Issue:**
The connection-string parser is a hand-rolled regex:

```python
m = re.match(r"postgresql\+psycopg://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)", url)
```

This has multiple real failure modes that all surface only at 02:00 when the nightly job runs:

1. **Password with `@` or `:`** — `([^@]+)` for the password stops at the first `@`. A password containing `@` (common in generated secrets) splits at the wrong place and the host/db get garbage, or the match fails entirely → `ValueError` → `pg_dump` artifact recorded as `error` every night. Note `.env.example` / `docker-compose.yml` generate strong random secrets; URL-reserved chars in passwords are a realistic production case.
2. **Password with no `:`/`@` but URL-encoded chars** — `%40` etc. are passed through verbatim to `PGPASSWORD`, not percent-decoded, so the password handed to `pg_dump` differs from the real one → silent auth failure.
3. **Userless or passwordless URLs** — any URL without exactly `user:pass@` (e.g. peer-auth `postgresql+psycopg://host/db`) raises `ValueError` even though it's a legal SQLAlchemy URL.
4. **Query params / extra path** — `?sslmode=require` lands inside the captured dbname group (`(.+)` is greedy), so `pg_dump -d "snobbery?sslmode=require"` fails.

Because `run_backup` wraps `_run_pg_dump` in a broad `except Exception`, none of this crashes the job — it just records `status="error"` in `last_backup_status` and emits a `BACKUP_ARTIFACT_ERROR` warning. A household that isn't watching logs gets **no DB backups and no loud signal**. That is a data-loss-risk class defect (the entire point of Phase 8 is durable backups).

**Fix:** Replace the regex with `sqlalchemy.engine.make_url`, which correctly handles percent-decoding, reserved chars, and optional components:

```python
from sqlalchemy.engine import make_url

def _parse_db_url(url: str) -> dict[str, str]:
    u = make_url(url)  # raises ArgumentError on truly malformed input
    if not u.host or not u.database:
        raise ValueError(f"DATABASE_URL missing host/database for pg_dump: {url!r}")
    return {
        "user": u.username or "",
        "password": u.password or "",  # already percent-decoded
        "host": u.host,
        "port": str(u.port or 5432),
        "dbname": u.database,
    }
```

`make_url` is already a dependency (SQLAlchemy 2.0) and is the canonical way to decompose the project's own `DATABASE_URL`. This removes the regex entirely and fixes all four cases.

## Warnings

### WR-01: Token aggregation mixes app-clock `run_start` with DB-clock `generated_at` — can under/over-count

**File:** `app/services/scheduler.py:265, 312-313` (with `app/services/scheduler.py:182-208`)
**Issue:**
`run_start = datetime.now(UTC)` is the **application process** clock. `aggregate_tokens_since` then filters `AIRecommendation.generated_at >= run_start`, but `generated_at` defaults to `server_default=func.now()` — the **Postgres server** clock, and Postgres `now()` returns *transaction-start* time, not row-insert time. Two consequences:

1. **Clock skew** between the app container and DB container (or just the transaction-start vs wall-clock gap) can place a row's `generated_at` *before* `run_start`, dropping legitimately-this-run rows from the token tally, or pull in a row from a transaction that started before `run_start` but committed after.
2. The summary's token totals are an operator cost-control signal; silently under-counting tokens defeats the "attribute spend" purpose.

**Fix:** Capture `run_start` from the database clock so it's comparable to `generated_at`. Either read `SELECT now()` at the top of the job, or filter on a stable monotonic marker (e.g. the max `id` seen before the run rather than a timestamp). Simplest:

```python
with SessionLocal() as db:
    run_start = db.execute(text("SELECT now()")).scalar_one()
    eligible_user_ids = _get_eligible_user_ids(db)
```

This is household-scale and rarely matters in practice, but it is a correctness bug in the SCHED-03 numbers, not a style nit.

### WR-02: `prune_old_backups` mutates the directory while iterating it

**File:** `app/services/backup.py:215-221`
**Issue:**
The loop calls `f.unlink()` while iterating `Path(backup_dir).iterdir()`:

```python
for f in Path(backup_dir).iterdir():
    m = pattern.match(f.name)
    if m:
        ...
        f.unlink()
```

`iterdir()` returns a lazy generator backed by the OS directory stream. Deleting entries mid-iteration is implementation-defined behavior across platforms/filesystems (entries may be skipped or visited twice). The unit test passes because `tmp_path` is small and the test never asserts deletion under a large set. In production with 14+ days of files this can silently leave files unpruned (disk fills) or, on some FS, raise.

**Fix:** Materialize the listing before mutating:

```python
for f in list(Path(backup_dir).iterdir()):
    m = pattern.match(f.name)
    if m:
        ...
        f.unlink()
```

### WR-03: `prune_old_backups` swallows nothing — an `unlink` failure aborts the whole prune and is uncaught in `run_backup`

**File:** `app/services/backup.py:215-222` and `app/services/backup.py:349-351`
**Issue:**
`prune_old_backups` is called in `run_backup` **outside** any try/except (line 350). If a single `f.unlink()` raises (permission, file held open, FS error), the exception propagates out of `prune_old_backups`, past the artifact try/except blocks (which have already completed), and **out of `run_backup` entirely** — so `last_backup_status` is never written and the scheduler records the whole job as failed, even though both backup artifacts succeeded. The keep-partial design intent (D-03) is broken for the prune step.

**Fix:** Wrap the prune in its own try/except (consistent with the artifact handling) and degrade gracefully:

```python
try:
    pruned_count = prune_old_backups(backup_dir, settings.BACKUP_RETENTION_DAYS, _today=today)
except Exception as exc:
    pruned_count = 0
    log.warning("backup.prune_failed", error_class=type(exc).__name__, error_msg=str(exc))
result.pruned_count = pruned_count
```

Also consider per-file try/except inside the loop so one undeletable file doesn't stop pruning the rest.

### WR-04: `_tar_photos` follows symlinks and has no path-traversal / size guard

**File:** `app/services/backup.py:169-181`
**Issue:**
`tar.add(photos_path, arcname="photos")` recurses with `tarfile`'s default `follow_symlinks` behavior. If anything ever writes a symlink into `/app/data/photos` (the photos pipeline is user-upload-fed), the backup tarball will dereference it and archive arbitrary host files reachable from the container, bloating the backup and potentially capturing secrets. Even absent a live exploit, archiving symlink targets is a footgun for a backup that may later be shipped off-box.

**Fix:** Add an explicit filter and refuse symlinks:

```python
def _no_symlinks(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
    if ti.issym() or ti.islnk():
        return None  # skip links; archive only regular files/dirs
    return ti

tar.add(photos_path, arcname="photos", filter=_no_symlinks)
```

(Low likelihood today since the photo pipeline writes normal files, hence Warning not Blocker — but it's a cheap, correct hardening for a backup path.)

### WR-05: `run_backup(db=object())` test path and the `_db: Session = db` assignment are type-unsafe and only work by accident

**File:** `app/services/backup.py:380-391` and `tests/test_backup.py:81`
**Issue:**
`run_backup` decides `own_session = db is None`; when a caller passes a non-None `db` it is used directly and **not** closed. The partial-failure test passes `db=object()` and patches `write_backup_status` to a no-op so the bogus session is never touched. That's fragile: any future change that actually uses `_db` before `write_backup_status` (e.g. a status read, a flush) will explode only in the real Phase 9 caller path, never in this test, because the test substitutes a sentinel. The `# type: ignore[assignment]` at line 385 is masking that the contract ("caller may pass a live Session") is untested with a real Session.

**Fix:** Don't assert behavior with a sentinel object. Either (a) have the partial-failure test pass `db=None` and patch `SessionLocal`/`write_backup_status`, or (b) split `run_backup` so the orchestration (artifacts → result dict) is a pure function the test can call without any session at all, and the status write is a thin wrapper. Option (b) also removes the `type: ignore`.

### WR-06: `test_ai_run_summary_tally` re-implements the production tally instead of calling it

**File:** `tests/test_scheduler.py:162-211`
**Issue:**
This test is named for SCHED-02 and the "highest-risk behavior #4" (force=False), but it never calls `run_nightly_ai_refresh`. It manually awaits the mock three times, then **copies** the tally `if/elif/else` block from `scheduler.py` into the test body and asserts on the copy. This proves the test's own copy is correct — it does **not** prove `run_nightly_ai_refresh`'s tally is correct, and it will not catch a regression where someone changes the real status-bucket mapping (e.g. drops `"not_configured"` from the skips set). The force=False guard is genuinely exercised (via the mock side_effect), but the tally coverage is illusory.

**Fix:** Drive the real function. With `mock_regenerate` patching `ai_service.regenerate` and `_get_eligible_user_ids` patched to return `[1, 2, 3]` (plus `write_ai_run_status`/`aggregate_tokens_since` patched or pointed at the test DB), call `run_nightly_ai_refresh()` and assert on the `summary` it produces or the `SCHEDULER_AI_RUN_COMPLETE` log payload. Otherwise this is a tautology test.

### WR-07: AI-refresh per-user session is opened but `regenerate`'s advisory lock + committed writes interact with session teardown

**File:** `app/services/scheduler.py:281-301`
**Issue:**
Each user gets `with SessionLocal() as db:` wrapping `asyncio.run(regenerate(...))`. `regenerate` acquires `pg_try_advisory_xact_lock` (transaction-scoped) and, on the generate path, calls `db.commit()` inside `_write_recommendation_row`. That commit ends the transaction and **releases the advisory lock before the sweet-spots prose write** — and after `regenerate` returns, the `with` block's implicit close issues a rollback on a session whose work was already committed (harmless, but means the per-user transaction boundary is `regenerate`-internal, not scheduler-controlled). The scheduler code is relying on undocumented commit timing inside `regenerate`. This is mostly a Phase 7 concern, but the scheduler is the production caller that makes the lock-release-mid-flight observable under the nightly sequential run.

**Fix (scoped to Phase 8):** Add a short comment at the call site documenting that `regenerate` owns its own transaction/commit boundary and the wrapping `with SessionLocal()` exists only to provide a Session, not to define the txn. Longer term, the advisory-lock-released-by-commit interaction inside `regenerate` should be filed against the AI service (out of this phase's scope) — flag it so it isn't lost.

## Info

### IN-01: `import datetime` inside `run_backup` body is inconsistent with module-level imports

**File:** `app/services/backup.py:362-364`
**Issue:** `datetime` is imported locally inside the function (`import datetime` then `datetime.datetime.now(...)`), while `date` and `timedelta` are imported at module top (line 34). Mixing styles is confusing and the `datetime.datetime` double-qualification reads awkwardly.
**Fix:** Add `datetime` (the class) to the top-level import: `from datetime import date, datetime, timedelta` and use `datetime.now(tz=UTC)`.

### IN-02: Magic numbers for cron hours and timeouts lack named constants

**File:** `app/services/scheduler.py:118, 124`; `app/services/backup.py:163`
**Issue:** `hour=0`, `hour=2`, and `timeout=300` are inline literals. The 02:00 backup vs 00:00 AI ordering is load-bearing (backup should run after the AI refresh settles) but the relationship isn't named.
**Fix:** Hoist to module constants (`AI_REFRESH_HOUR = 0`, `BACKUP_HOUR = 2`, `PG_DUMP_TIMEOUT_S = 300`) with a one-line comment on the ordering rationale.

### IN-03: `BackupResult.timestamp` defaults to `""` and is only populated on the happy path through `run_backup`

**File:** `app/services/backup.py:97, 364`
**Issue:** If `run_backup` ever returns early (it currently can't, but the dataclass default is an empty string), `timestamp` is a non-ISO empty string that the Phase 9 admin panel will try to render. Minor latent footgun.
**Fix:** Default to `None` typed as `str | None`, or set `timestamp` at the very top of `run_backup` so it's always populated.

### IN-04: `summary` dict gains keys (`overall`, `timestamp`) after construction — shape drifts from the documented event field list

**File:** `app/services/scheduler.py:266-274, 316-318` vs `app/events.py:166-169`
**Issue:** `events.py` documents `SCHEDULER_AI_RUN_COMPLETE` fields as `users_processed, regenerations, skips, errors, tokens_*_total, timestamp` — but the runtime `summary` also carries an `overall` key (added at line 317) that isn't in the documented field shape, and `**summary` splats all of it into the log line. Not a bug, but the events.py docstring and the actual emitted payload have drifted.
**Fix:** Add `overall` to the documented `SCHEDULER_AI_RUN_COMPLETE` field list in `events.py`, or drop it from the splat if it's only meant for `last_ai_run_status`.

### IN-05: `run_nightly_backup` logs at `error` and re-raises; `run_nightly_ai_refresh` swallows per-user errors and never re-raises — inconsistent failure semantics

**File:** `app/services/scheduler.py:334-354` vs `app/services/scheduler.py:242-326`
**Issue:** The backup job re-raises on failure (so APScheduler marks the job run failed and the misfire/retry machinery sees it). The AI job never raises — it absorbs everything into the summary and always returns normally, so APScheduler always sees the AI job as "succeeded" even when every user errored. This asymmetry is defensible (different jobs, different intent) but undocumented, and an operator watching APScheduler job-run status will never see an AI-refresh failure surface there.
**Fix:** Document the intentional asymmetry in the `run_nightly_ai_refresh` docstring, or raise when `summary["errors"] == users_processed > 0` (total failure) so a fully-broken AI run is visible to the scheduler, not just to log greppers.

---

_Reviewed: 2026-05-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
