---
phase: 14-audit-remediation
plan: "04"
subsystem: search
tags: [security, rate-limiting, input-validation, s4]
dependency_graph:
  requires: []
  provides: [SEARCH_LIMIT constant, /search rate limit, /search 100-char cap]
  affects: [app/rate_limit.py, app/routers/search.py, tests/test_search.py]
tech_stack:
  added: []
  patterns: [slowapi per-route limit decorator, raw-q-before-strip cap, autouse limiter reset fixture]
key_files:
  created: []
  modified:
    - app/rate_limit.py
    - app/routers/search.py
    - tests/test_search.py
decisions:
  - "Rate-limit test shipped as automated (deterministic): autouse _reset_rate_limiter fixture in conftest.py clears in-memory limiter before each test; 61 sequential requests reliably hit the 60/minute cap. No manual-verify fallback needed."
  - "100-char cap operates on raw q before .strip() per D-07: a 101-char all-spaces string is also short-circuited."
  - "Decorator order: @router.get outermost, @limiter.limit immediately below (Pitfall 4 / auth.py analog)."
metrics:
  duration: "15 min"
  completed: "2026-05-25"
  tasks: 2
  files: 3
---

# Phase 14 Plan 04: Search Hardening (S4) Summary

One-liner: `/search` gains a 100-char raw-q cap short-circuiting to empty-200, plus a `SEARCH_LIMIT = "60/minute"` slowapi rate limit -- both verified by automated tests with 0 skips.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add SEARCH_LIMIT constant + cap + decorator on /search | 438c796 | app/rate_limit.py, app/routers/search.py |
| 2 | Author over-long-query test + automated rate-limit test | b2b104d | tests/test_search.py |

## What Was Built

**Task 1 (438c796):**
- `app/rate_limit.py`: Added `SEARCH_LIMIT: str = "60/minute"` after `CSP_REPORT_LIMIT`, following the existing typed-string pattern.
- `app/routers/search.py`: Imported `SEARCH_LIMIT, limiter`; added `@limiter.limit(SEARCH_LIMIT)` on the line immediately below `@router.get(...)` (route decorator outermost, limiter next -- matches auth.py Pitfall-4 order); inserted `if len(q) > 100: return HTMLResponse("", status_code=200)` as the first body statement, operating on raw `q` before `.strip()` per D-07.

**Task 2 (b2b104d):**
- `test_long_query_returns_empty`: sends `"a" * 101` as q, asserts `200` + empty body. Mirrors `test_short_query_empty` shape.
- `test_search_rate_limit`: fires 61 sequential GETs to `/search?q=ab`, asserts a `429` appears. Deterministic because the autouse `_reset_rate_limiter` fixture clears slowapi's in-memory storage before each test.

## Verification Results

```
tests/test_search.py -k "long_query or search_rate_limit"   → 2 passed, 0 skipped
Full 4-file gate (test_scheduler, test_admin_users, test_ai_service, test_search) → 91 passed, 0 skipped
ruff check app/ tests/   → All checks passed
ruff format --check app/ tests/   → 197 files already formatted
```

## Rate-Limit Test: Automated (not manual-verify)

The plan offered a manual-verify fallback if the in-process rate-limit test proved flaky. It was not needed: the `_reset_rate_limiter` autouse fixture (conftest.py:186-204) calls `limiter.reset()` between tests, giving each test a clean in-memory bucket. Firing 61 sequential requests deterministically hits the 60/minute cap. This matches the existing `test_rate_limit` in `tests/routers/test_csp_report.py` (CSP_REPORT_LIMIT, 31 requests).

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan adds guards to an existing endpoint.

## Self-Check: PASSED

- app/rate_limit.py: SEARCH_LIMIT constant present at line 44
- app/routers/search.py: @limiter.limit(SEARCH_LIMIT) present; len(q) > 100 cap present before len(q.strip()) < 2
- tests/test_search.py: test_long_query_returns_empty and test_search_rate_limit present
- Commits 438c796 and b2b104d verified in git log
