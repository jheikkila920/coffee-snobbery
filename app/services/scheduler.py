"""APScheduler integration — owned by Phase 8.

Two nightly jobs:
- ``nightly_ai_refresh`` @ 00:00 APP_TIMEZONE — SCHED-01/02/03
- ``nightly_backup``     @ 02:00 APP_TIMEZONE — SCHED-04

APScheduler 3.11 wired with SQLAlchemyJobStore backed by the SYNC engine
from ``app.db`` (not ``_async_engine`` — that would silently fail at
runtime; see Pitfall 1 in 08-RESEARCH.md). The ``apscheduler_jobs`` table
is APScheduler-managed (auto-created by ``SQLAlchemyJobStore`` on first
connect via ``metadata.create_all``); it is NOT part of the Alembic
migration chain. No migration needed.
"""

# IMPORTANT: This module — and the uvicorn process hosting it — MUST run as a
#   single worker (uvicorn flag: --workers 1). APScheduler is in-process;
#   module-level AI locks live in this process. A future `--workers 4` would
#   fire every nightly job 4x and bill 4x the AI cost
#   (PROJECT.md row 16; CONTEXT.md <specifics>).
#
# This file is location #2 of three places that loudly state the single-worker
# rule. The other two are:
#   (1) entrypoint.sh — comment block above the uvicorn invocation
#   (3) README.md     — deployment section
#
# Anyone trying to add `--workers 4` trips over this note three times before
# they succeed. If you remove or weaken this comment, restore one of the other
# two locations to compensate so the count of warnings stays at three.

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, engine  # SYNC engine — required by SQLAlchemyJobStore
from app.events import (
    SCHEDULER_AI_RUN_COMPLETE,
    SCHEDULER_JOB_ERROR,
    SCHEDULER_JOB_START,
    SCHEDULER_JOB_SUCCESS,
    SCHEDULER_SHUTDOWN,
    SCHEDULER_STARTED,
)

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Scheduler factory + module-level singleton
# ---------------------------------------------------------------------------


def build_scheduler() -> AsyncIOScheduler:
    """Build an AsyncIOScheduler backed by the sync SQLAlchemyJobStore.

    Uses the SYNC ``engine`` from ``app.db`` — NOT ``_async_engine`` and NOT
    ``url=settings.DATABASE_URL`` (which would create a second pool). See
    08-RESEARCH.md Pitfall 1.

    DST note for America/Chicago (Pitfall 6): a 02:00 fire on spring-forward
    night does not exist; APScheduler fires at the next valid time. The
    misfire_grace_time=3600 catches it — acceptable at household scale.
    """
    jobstores = {
        "default": SQLAlchemyJobStore(engine=engine),
    }
    executors = {
        "default": ThreadPoolExecutor(max_workers=2),
    }
    job_defaults: dict[str, Any] = {
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


# Module-level singleton. Imported by app/main.py lifespan.
scheduler = build_scheduler()


# ---------------------------------------------------------------------------
# Job registration (idempotent — stable IDs + replace_existing=True)
# ---------------------------------------------------------------------------


def register_jobs(sched: AsyncIOScheduler | None = None) -> None:
    """Add both nightly jobs with stable IDs + replace_existing=True.

    Calling this N times produces exactly 2 rows in apscheduler_jobs — no
    duplicates. This is the idempotency guarantee (08-RESEARCH.md Pitfall 3,
    T-08-09 threat mitigation).

    Args:
        sched: The scheduler to register jobs on. Defaults to the module-level
               ``scheduler`` singleton. Tests pass a local instance with an
               in-memory job store.
    """
    target = sched if sched is not None else scheduler
    target.add_job(
        run_nightly_ai_refresh,
        CronTrigger(hour=0, minute=0, timezone=settings.APP_TIMEZONE),
        id="nightly_ai_refresh",
        replace_existing=True,
    )
    target.add_job(
        run_nightly_backup,
        CronTrigger(hour=2, minute=0, timezone=settings.APP_TIMEZONE),
        id="nightly_backup",
        replace_existing=True,
    )


# ---------------------------------------------------------------------------
# Lifecycle helpers (called from app/main.py lifespan)
# ---------------------------------------------------------------------------


def start() -> None:
    """Start the module-level scheduler and register both jobs."""
    scheduler.start()
    register_jobs()
    log.info(SCHEDULER_STARTED)


def shutdown() -> None:
    """Shut down the scheduler without blocking (wait=False).

    Non-blocking so a SIGTERM during a mid-flight pg_dump never blocks
    container stop (08-RESEARCH Pattern 2 rationale).
    """
    scheduler.shutdown(wait=False)
    log.info(SCHEDULER_SHUTDOWN)


# ---------------------------------------------------------------------------
# Eligibility query (SCHED-02 / D-04)
# ---------------------------------------------------------------------------


def _get_eligible_user_ids(db: Session) -> list[int]:
    """Return user IDs that are active AND have >= 3 brew sessions.

    This is the ONLY pre-filter (D-04). regenerate() owns all remaining
    gating: cold-start flavor-note gate (>=5 distinct), signature check,
    in-memory + advisory locks, throttle.
    """
    from app.models.brew_session import BrewSession
    from app.models.user import User

    result = db.execute(
        select(User.id)
        .join(BrewSession, BrewSession.user_id == User.id)
        .where(User.is_active.is_(True))
        .group_by(User.id)
        .having(func.count(BrewSession.id) >= 3)
    )
    return [row[0] for row in result]


# ---------------------------------------------------------------------------
# Token aggregation (SCHED-03)
# ---------------------------------------------------------------------------


def aggregate_tokens_since(db: Session, run_start: datetime) -> dict[str, int]:
    """SUM token columns from ai_recommendations written during this run.

    Filters generated_by='scheduler' AND generated_at >= run_start so that
    prior scheduler runs and manual_refresh rows are excluded (D-04).
    NULL sums are coalesced to 0.

    Phase 9 contract: non_search_input = tokens_input_total - tokens_input_search_total.
    """
    from app.models.ai_recommendation import AIRecommendation

    row = db.execute(
        select(
            func.coalesce(func.sum(AIRecommendation.tokens_input), 0).label(
                "tokens_input_total"
            ),
            func.coalesce(func.sum(AIRecommendation.tokens_output), 0).label(
                "tokens_output_total"
            ),
            func.coalesce(func.sum(AIRecommendation.tokens_input_search), 0).label(
                "tokens_input_search_total"
            ),
        ).where(
            AIRecommendation.generated_by == "scheduler",
            AIRecommendation.generated_at >= run_start,
        )
    ).one()
    return {
        "tokens_input_total": row.tokens_input_total,
        "tokens_output_total": row.tokens_output_total,
        "tokens_input_search_total": row.tokens_input_search_total,
    }


# ---------------------------------------------------------------------------
# Status write helper (SCHED-03)
# ---------------------------------------------------------------------------


def write_ai_run_status(db: Session, summary: dict[str, Any]) -> None:
    """Persist the run summary to app_settings.last_ai_run_status as a JSON string.

    Phase 9 cross-phase contract: the admin API-health panel MUST read
    last_ai_run_status via a raw DB query (not get_str()), because
    set_setting() pops the cache key after every write. Until the next
    prewarm_cache() call, get_str() raises SettingNotFoundError. The admin
    panel reads infrequently and can absorb a DB hit. Do NOT call
    prewarm_cache() here — that would repopulate stale cached values for
    other keys set earlier in the request lifecycle.
    """
    from app.services.settings import set_setting

    set_setting(db, "last_ai_run_status", json.dumps(summary), by_user_id=None)


# ---------------------------------------------------------------------------
# Nightly AI refresh job (SCHED-02, SCHED-03)
# ---------------------------------------------------------------------------


def run_nightly_ai_refresh() -> None:
    """Nightly AI refresh job body — sync def, runs in ThreadPoolExecutor.

    MUST be a plain sync function. AsyncIOScheduler with ThreadPoolExecutor
    runs sync bodies in a worker thread — the event loop is never blocked.
    If declared async def it would run ON the event loop and any sync DB
    call inside would block it (08-RESEARCH Pitfall 4).

    sync→async bridge: regenerate() is async but this job body is sync.
    Each per-user call uses asyncio.run(regenerate(...)) — the same pattern
    as tests/conftest.py _seed_user. asyncio.run opens a fresh event loop
    per call; at household scale (sequential, one user at a time) this is
    correct and low-cost.

    The AI job does NOT implement any new cost ceiling or throttle.
    regenerate() owns: cold-start gate, signature check, in-memory +
    advisory locks, throttle, telemetry writes. This job only pre-filters
    eligibility cheaply and tallies the returned status string.
    """
    from app.services import ai_service

    log.info(SCHEDULER_JOB_START, job_id="nightly_ai_refresh")

    summary: dict[str, Any] = {
        "users_processed": 0,
        "regenerations": 0,
        "skips": 0,
        "errors": 0,
        "tokens_input_total": 0,
        "tokens_output_total": 0,
        "tokens_input_search_total": 0,
    }

    # Step 1: eligibility query — one short session, read eligible IDs.
    # run_start is read from the DB clock (SELECT now()) so it is on the same
    # clock as generated_at (server_default=func.now()), making the
    # aggregate_tokens_since filter comparable (WR-01).
    with SessionLocal() as db:
        run_start: datetime = db.execute(text("SELECT now()")).scalar_one()
        eligible_user_ids = _get_eligible_user_ids(db)

    # Step 2: per-user regenerate — one fresh session per user.
    for uid in eligible_user_ids:
        # NOTE (WR-07): This session exists solely to provide a Session object
        # to regenerate(). It does NOT define the transaction boundary.
        # regenerate() owns its own commit (inside _write_recommendation_row)
        # and acquires pg_try_advisory_xact_lock internally. The advisory lock
        # is released when regenerate() commits -- before this with-block exits.
        # The implicit rollback on __exit__ is therefore a no-op on the generate
        # path (nothing uncommitted remains). Longer-term, the lock-released-
        # by-commit interaction inside regenerate() should be reviewed against
        # Phase 7 (out of Phase 8 scope).
        with SessionLocal() as db:
            try:
                # Bridge sync job body → async regenerate (08-RESEARCH Pattern 3,
                # <critical_implementation_note>). Each asyncio.run opens a fresh
                # event loop in this worker thread and tears it down when done.
                status = asyncio.run(
                    ai_service.regenerate(uid, "scheduler", db=db, force=False)
                )
            except Exception as exc:
                # One user's unexpected raise must not abort the whole run.
                log.warning(
                    SCHEDULER_JOB_ERROR,
                    job_id="nightly_ai_refresh",
                    user_id=uid,
                    error_class=type(exc).__name__,
                    error_msg=str(exc),
                )
                summary["errors"] += 1
                summary["users_processed"] += 1
                continue

        summary["users_processed"] += 1
        if status == "generated":
            summary["regenerations"] += 1
        elif status in ("skipped", "locked", "try_again", "not_configured"):
            summary["skips"] += 1
        else:  # "error"
            summary["errors"] += 1

    # Step 3: token aggregation — SUM ai_recommendations rows from this run.
    with SessionLocal() as db:
        token_totals = aggregate_tokens_since(db, run_start)
        summary.update(token_totals)

        # Overall status: error if any per-user error occurred.
        summary["overall"] = "error" if summary["errors"] > 0 else "ok"
        summary["timestamp"] = datetime.now(UTC).isoformat()

        # Write the SCHED-03 summary to app_settings.
        write_ai_run_status(db, summary)

    # Emit ONE SCHED-03 summary line (not per-user — the per-user events come
    # from regenerate() itself). This is the single SCHEDULER_AI_RUN_COMPLETE line.
    log.info(SCHEDULER_AI_RUN_COMPLETE, **summary)
    log.info(SCHEDULER_JOB_SUCCESS, job_id="nightly_ai_refresh")


# ---------------------------------------------------------------------------
# Nightly backup job wrapper (SCHED-04)
# ---------------------------------------------------------------------------


def run_nightly_backup() -> None:
    """Nightly backup job body — sync def, runs in ThreadPoolExecutor.

    Lazy-imports run_backup to avoid an import-time cycle between
    scheduler.py and backup.py (Plans 08-02 and 08-03 are decoupled by D-03).
    Neither job references the other.
    """
    log.info(SCHEDULER_JOB_START, job_id="nightly_backup")
    try:
        from app.services.backup import run_backup

        run_backup()
        log.info(SCHEDULER_JOB_SUCCESS, job_id="nightly_backup")
    except Exception as exc:
        log.error(
            SCHEDULER_JOB_ERROR,
            job_id="nightly_backup",
            error_class=type(exc).__name__,
            error_msg=str(exc),
        )
        raise
