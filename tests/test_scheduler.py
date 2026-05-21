"""Wave 0 test stubs for Phase 8 scheduler requirements (SCHED-01/02/03).

All tests are marked xfail(strict=False) until Plans 08-02 and 08-03 land
the scheduler implementation. The stub body encodes the intended assertion
shape as a comment so the implementing plan only removes the xfail marker.

Per 08-VALIDATION.md §"Per-Task Verification Map":
- SCHED-01: test_idempotent_job_registration, test_lifespan_scheduler_lifecycle
- SCHED-02: test_eligibility_filter, test_ai_run_summary_tally
- SCHED-03: test_token_aggregation, test_status_row_write
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# SCHED-01 — Scheduler registration + lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=False, reason="Plan 08-03 implements register_jobs()")
def test_idempotent_job_registration() -> None:
    """Exactly 2 jobs registered after N register_jobs() calls — no duplicates.

    Highest-risk behavior #5 per 08-VALIDATION.md: calling register_jobs()
    multiple times (i.e., on every container restart) must not add duplicate
    rows in apscheduler_jobs. Stable explicit job IDs + replace_existing=True
    is the mechanism (08-RESEARCH.md Pitfall 3).

    Intended assertion (remove xfail when Plan 08-03 lands):

        from app.services.scheduler import build_scheduler, register_jobs
        from apscheduler.jobstores.memory import MemoryJobStore

        sched = build_scheduler()
        # Override to in-memory job store so no live DB needed
        sched._jobstores = {"default": MemoryJobStore()}
        sched.start()
        try:
            register_jobs(sched)
            register_jobs(sched)
            register_jobs(sched)
            jobs = sched.get_jobs()
            assert len(jobs) == 2
            job_ids = {j.id for j in jobs}
            assert job_ids == {"nightly_ai_refresh", "nightly_backup"}
        finally:
            sched.shutdown(wait=False)
    """
    try:
        from app.services import scheduler as _sched_mod  # noqa: F401
    except ImportError:
        pytest.skip("app.services.scheduler not yet implemented (Plan 08-03)")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-03 lands")


@pytest.mark.xfail(strict=False, reason="Plan 08-03 implements lifespan scheduler wiring")
def test_lifespan_scheduler_lifecycle() -> None:
    """Scheduler starts and stops cleanly in the FastAPI lifespan.

    Verifies SCHED-01: AsyncIOScheduler with SQLAlchemyJobStore starts on
    app startup and shuts down (wait=False) on SIGTERM without blocking.

    Intended assertion (remove xfail when Plan 08-03 lands):

        from fastapi.testclient import TestClient
        # TestClient triggers lifespan enter/exit
        with TestClient(app) as client:
            resp = client.get("/healthz")
            assert resp.status_code == 200
        # If we get here the scheduler started and stopped without raising
    """
    try:
        from app.main import app as _app  # noqa: F401
    except (ImportError, RuntimeError):
        pytest.skip("app.main not importable (Tailwind CSS missing or Phase 8 not wired)")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-03 lands")


# ---------------------------------------------------------------------------
# SCHED-02 — Nightly AI refresh eligibility + status tally
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=False, reason="Plan 08-03 implements _get_eligible_user_ids()")
def test_eligibility_filter(sync_db: Any) -> None:
    """Eligibility filter: is_active=True AND >= 3 brew sessions.

    regenerate() owns all remaining gating (cold-start, sig-check, locks).
    The scheduler's pre-filter is cheap and defined by D-04.

    Intended assertion (remove xfail when Plan 08-03 lands):

        from app.services.scheduler import _get_eligible_user_ids
        # Seed: user_a active + 3 sessions, user_b active + 2 sessions,
        #       user_c inactive + 5 sessions
        eligible = _get_eligible_user_ids(sync_db)
        assert user_a.id in eligible
        assert user_b.id not in eligible   # < 3 sessions
        assert user_c.id not in eligible   # inactive
    """
    if sync_db is None:
        pytest.skip("sync_db not available")

    try:
        from app.services.scheduler import _get_eligible_user_ids  # noqa: F401
    except ImportError:
        pytest.skip("app.services.scheduler._get_eligible_user_ids not yet implemented")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-03 lands")


@pytest.mark.asyncio
@pytest.mark.xfail(strict=False, reason="Plan 08-03 implements run_nightly_ai_refresh()")
async def test_ai_run_summary_tally(mock_regenerate: Any) -> None:
    """regenerate() return values are tallied correctly; force=False is enforced.

    Verifies SCHED-02 summary counters and the highest-risk behavior #4
    from 08-VALIDATION.md: the scheduler MUST call regenerate() with
    force=False (never True) to preserve the signature cost-control.
    The mock_regenerate fixture asserts force=False on every call.

    Intended assertion (remove xfail when Plan 08-03 lands):

        patch = mock_regenerate({"1": "generated", "2": "skipped", "3": "error"})
        # Call the job body with a mock eligible user list
        summary = run_nightly_ai_refresh_for_users([1, 2, 3])
        assert summary["regenerations"] == 1
        assert summary["skips"] == 1
        assert summary["errors"] == 1
        assert summary["users_processed"] == 3
        # mock_regenerate's side-effect asserts force=False on every call
        assert patch.call_count == 3
    """
    if mock_regenerate is None:
        pytest.skip("mock_regenerate not available")

    try:
        from app.services import scheduler as _sched_mod  # noqa: F401
    except ImportError:
        pytest.skip("app.services.scheduler not yet implemented (Plan 08-03)")

    # Prove the mock is awaitable (acceptance criterion from Task 2)
    _mock_fn = mock_regenerate("generated")
    result = await _mock_fn(1, "scheduler", db=object())
    assert result == "generated"

    pytest.fail("xfail stub — remove marker and fill full assertion when Plan 08-03 lands")


# ---------------------------------------------------------------------------
# SCHED-03 — Run summary token aggregation + status row write
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=False, reason="Plan 08-03 implements token aggregation query")
def test_token_aggregation(sync_db: Any) -> None:
    """Token aggregation sums this-run rows only; web-search split is correct.

    The scheduler aggregates token totals from ai_recommendations rows
    written during the current run (generated_by="scheduler",
    generated_at >= run_start). Only rows from THIS run are summed —
    earlier scheduler runs are excluded. The web-search split:
    non_search_input = tokens_input_total - tokens_input_search_total.

    Intended assertion (remove xfail when Plan 08-03 lands):

        from app.services.scheduler import aggregate_tokens_since
        from datetime import datetime, timezone

        run_start = datetime.now(timezone.utc)
        # Seed 2 ai_recommendation rows: one with web-search, one without
        # (tokens_input=100, tokens_input_search=20 for the search row)
        totals = aggregate_tokens_since(sync_db, run_start)
        assert totals["tokens_input_total"] == 150
        assert totals["tokens_input_search_total"] == 20
        assert totals["tokens_output_total"] == 80
    """
    if sync_db is None:
        pytest.skip("sync_db not available")

    try:
        from app.services.scheduler import aggregate_tokens_since  # noqa: F401
    except ImportError:
        pytest.skip("app.services.scheduler.aggregate_tokens_since not yet implemented")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-03 lands")


@pytest.mark.xfail(strict=False, reason="Plan 08-03 implements last_ai_run_status write")
def test_status_row_write(sync_db: Any) -> None:
    """last_ai_run_status is written as a valid JSON string to app_settings.

    Verifies SCHED-03: the scheduler calls set_setting(db, "last_ai_run_status",
    json.dumps(summary), by_user_id=None). The stored value must parse as
    JSON (value_type="string" row stores a JSON-encoded string per D-04 and
    the set_setting() contract from 08-RESEARCH.md Pitfall 7).

    Intended assertion (remove xfail when Plan 08-03 lands):

        import json
        from app.services.settings import get_setting
        # Trigger the scheduler's status-write path with a fixed summary dict
        write_ai_run_status(sync_db, summary_dict)
        row = get_setting(sync_db, "last_ai_run_status")
        parsed = json.loads(row.value)  # must not raise
        assert "users_processed" in parsed
        assert "timestamp" in parsed
    """
    if sync_db is None:
        pytest.skip("sync_db not available")

    try:
        from app.services.scheduler import write_ai_run_status  # noqa: F401
    except ImportError:
        pytest.skip("app.services.scheduler.write_ai_run_status not yet implemented")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-03 lands")
