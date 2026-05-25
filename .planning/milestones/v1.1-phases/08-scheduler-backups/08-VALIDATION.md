---
phase: 8
slug: scheduler-backups
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-21
validated: 2026-05-21
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `08-RESEARCH.md` §"Validation Architecture". Task IDs are filled by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0 (+ pytest-asyncio) |
| **Config file** | none yet — Wave 0 installs into the running container (CLAUDE.md: pytest not baked into the prod image) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/test_scheduler.py tests/test_backup.py -x -q` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Estimated runtime** | ~30 seconds (unit-only; the pg_dump restore drill is manual) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (scheduler + backup unit tests)
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite must be green AND the manual pg_dump restore drill performed once
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

> Plan/task IDs assigned during planning. Requirement→behavior→command rows below are pre-mapped from research; the planner attaches each to the owning task.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-03-T1 | 08-03 | 2 | SCHED-01 | — | Exactly 2 jobs registered after N restarts (no dupes) | unit | `pytest tests/test_scheduler.py::test_idempotent_job_registration -x` | ✅ 08-01 | ✅ green |
| 08-03-T1 | 08-03 | 2 | SCHED-01 | — | Scheduler starts/stops cleanly in lifespan | integration | `pytest tests/test_scheduler.py::test_lifespan_scheduler_lifecycle -x` | ✅ 08-01 | ✅ green |
| 08-03-T2 | 08-03 | 2 | SCHED-02 | T-08 (access control) | Eligibility filter = is_active AND >=3 sessions | unit | `pytest tests/test_scheduler.py::test_eligibility_filter -x` | ✅ 08-01 | ✅ green |
| 08-03-T2 | 08-03 | 2 | SCHED-02 | — | `regenerate()` called with `force=False`; statuses tallied | unit | `pytest tests/test_scheduler.py::test_ai_run_summary_tally -x` | ✅ 08-01 | ✅ green |
| 08-03-T2 | 08-03 | 2 | SCHED-03 | — | Token aggregation sums this-run rows only; web-search split correct | unit | `pytest tests/test_scheduler.py::test_token_aggregation -x` | ✅ 08-01 | ✅ green |
| 08-03-T2 | 08-03 | 2 | SCHED-03 | — | `last_ai_run_status` written as JSON string to `app_settings` | unit | `pytest tests/test_scheduler.py::test_status_row_write -x` | ✅ 08-01 | ✅ green |
| 08-02-T1 | 08-02 | 2 | SCHED-04 | — | Filename-based retention prune deletes the correct files | unit | `pytest tests/test_backup.py::test_retention_prune -x` | ✅ 08-01 | ✅ green |
| 08-02-T2 | 08-02 | 2 | SCHED-04 | — | Partial failure keeps the good artifact + flags overall error | unit | `pytest tests/test_backup.py::test_partial_failure_keeps_good -x` | ✅ 08-01 | ✅ green |
| 08-02-T2 | 08-02 | 2 | SCHED-04 | T-08 (info disclosure) | `last_backup_status` written as JSON string to `app_settings` | unit | `pytest tests/test_backup.py::test_backup_status_row_write -x` | ✅ 08-01 | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_scheduler.py` — covers SCHED-01, SCHED-02, SCHED-03 (idempotent registration, eligibility filter, summary tally, token aggregation, status-row write) [stubs: Plan 08-01]
- [x] `tests/test_backup.py` — covers SCHED-04 unit cases (retention prune, partial-failure, status-row write) [stubs: Plan 08-01]
- [x] `tests/conftest.py` — shared fixtures (sync_db session, mock_regenerate) [Plan 08-01]
- [x] pytest install into the running container: `docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio` (CLAUDE.md) — verified pytest 9.0.3 present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `pg_dump` output restores cleanly | SCHED-04 | Needs a second live Postgres schema; cannot run in the unit suite | Dump the dev DB, restore via `psql ... < db_YYYY-MM-DD.sql` into a fresh schema, verify row counts match the source |
| Restart-within-grace fires the job once | SCHED-01 | Real container restart timing; the unit test simulates this but a true restart drill is the SC-4 acceptance gate | Stop the container at ~23:55, restart so 00:00 lands within the 1h grace window, confirm the AI job ran exactly once (one `last_ai_run_status` update, one summary log line) |

---

## Validation Audit 2026-05-21

Audited the planned map against the running stack. All 9 mapped tests executed in-container (`tests/test_scheduler.py`, `tests/test_backup.py`); 7 were green, 2 silently SKIPPED (pass-by-skip) because the test DB had no `coffee` rows — leaving SCHED-02 (eligibility) and SCHED-03 (token aggregation) unverified despite the plan's "all green" claim.

| Metric | Count |
|--------|-------|
| Gaps found | 2 |
| Resolved | 2 |
| Escalated | 0 |

**Fixes (test-only, no impl changes):**
- `test_eligibility_filter` (SCHED-02) — now self-seeds a `Coffee(name=...)` row instead of skipping when none exists.
- `test_token_aggregation` (SCHED-03) — removed the spurious coffee-lookup skip guard (AIRecommendation has no coffee FK) and backdated `run_start` by 1s so the `func.now()` server-default rows fall inside the `>= run_start` window.

Final result: **9 passed, 0 skipped** (`docker compose exec -T coffee-snobbery python -m pytest tests/test_scheduler.py tests/test_backup.py`).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (`tests/test_scheduler.py`, `tests/test_backup.py`, `tests/conftest.py`) [Plan 08-01]
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-05-21 — 9/9 automated tests green, 0 skipped (plans 08-01..08-03)
