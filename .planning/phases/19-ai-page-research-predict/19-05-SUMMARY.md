---
phase: 19-ai-page-research-predict
plan: "05"
subsystem: ai-routes-charts
tags: [ai, sse, quota, charts, tdd, aix-01, aix-03, aix-05, aix-07, aix-12, aix-13, viz-01, d-09, d-12, d-16, d-17]
dependency_graph:
  requires: [19-03 (ai_research.py + ai_quota.py), 19-04 (generate_brew_improvement + ai_service)]
  provides: [POST /ai/research SSE route, GET /ai/research/quota, POST /ai/improve-brew/{id}, GET /ai/coach, GET /ai/charts/*, charts.py]
  affects:
    - app/routers/ai.py (6 new routes added)
    - app/services/charts.py (new: rating_over_time + flavor_distribution)
    - app/templates/fragments/ai/coach_brew_picker.html (new: stub picker template)
    - tests/routers/test_ai_research.py (new)
    - tests/routers/test_ai_improve.py (new)
    - tests/routers/test_ai_charts.py (new)
    - tests/services/test_analytics_perf.py (latency percentile test added)
tech_stack:
  added: []
  patterns: [TDD RED/GREEN, EventSourceResponse+X-Accel-Buffering, 429+HX-Retarget quota gate, IDOR-404 user-scoped session load, per-user JSON chart endpoints]
key_files:
  created:
    - app/services/charts.py
    - app/templates/fragments/ai/coach_brew_picker.html
    - tests/routers/test_ai_research.py
    - tests/routers/test_ai_improve.py
    - tests/routers/test_ai_charts.py
  modified:
    - app/routers/ai.py (6 new routes + import block)
    - tests/services/test_analytics_perf.py (latency percentile test appended)
decisions:
  - "Routes kept in app/routers/ai.py (not split to ai_research.py) — file is 650 lines, still readable; splitting deferred unless 19-06 pushes it past 800"
  - "POST /ai/research cold-start gate returns 403 with inline HTML fragment (not redirect) — consistent with other gate patterns in the codebase"
  - "POST /ai/improve-brew/{session_id} IDOR check raises HTTPException(404) before EventSourceResponse starts — 404 before SSE is correct (session not found = non-existence response, not a streaming error)"
  - "charts.py uses raw SQL with text() + bound :user_id param (T-19-18) — avoids ORM JOIN complexity for the UNION unnest pattern (mirrors analytics.py precedent)"
  - "GET /ai/coach returns TemplateResponse (not JSONResponse) — coach_brew_picker.html stub is functional; 19-06 will refine the template"
metrics:
  duration: "~18 minutes"
  completed: "2026-05-28"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 19 Plan 05: Routes + Charts Wiring Summary

Six Phase 19 HTTP routes wired to the service layer built in plans 19-03/19-04, plus the VIZ-01 chart query helpers in a new `charts.py`. TDD RED/GREEN throughout.

## What Was Built

### Task 1: POST /ai/research + GET /ai/research/quota (AIX-01/03/05/07/D-09/D-16)

- **`POST /ai/research`**: Gate ordering enforced before `EventSourceResponse` starts:
  1. Cold-start gate closed → 403 HTML fragment (AIX-03)
  2. Quota exhausted → 429 + `HX-Retarget="#research-card"` + `HX-Reswap="outerHTML"` (AIX-05/D-09)
  3. `compute_input_signature` for prediction versioning
  4. `EventSourceResponse(generate_coffee_research(...), headers={"X-Accel-Buffering": "no"})` (AIX-07/D-16/T-19-20)
  5. BackgroundTask: `_verify_and_persist_url` for buy_url SSRF check (T-19-11)
  - `user_id` only from `request.state.user.id` (T-19-16)
  - CSRF via `CSRFMiddleware` (T-07-11)

- **`GET /ai/research/quota`**: Renders `{remaining}/{cap} research calls remaining today` or `Resets in Hh Mm` as an HTML `<span id="research-quota">`. Reads `ai_quota.remaining` + `get_quota_reset_time`.

**Test results:** 6 passed (test_ai_research.py)

### Task 2: POST /ai/improve-brew/{session_id} + GET /ai/coach (AIX-12/D-12)

- **`POST /ai/improve-brew/{session_id}`**: Gate ordering:
  1. `brew_sessions_service.get_brew_session(db, session_id=..., by_user_id=user_id)` → `HTTPException(404)` on cross-user (T-19-17/IDOR — existence non-leak, not 403)
  2. Quota check on `brew_improvement` bucket → 429 on exhaustion (separate from research, D-08)
  3. `EventSourceResponse(generate_brew_improvement(...), headers={"X-Accel-Buffering": "no"})` (D-16/T-19-20)

- **`GET /ai/coach`**: Returns `TemplateResponse("fragments/ai/coach_brew_picker.html")` with the user's last 20 brew sessions (`list_brew_sessions(db, by_user_id=user_id)[:20]`). User-scoped only (T-19-17).

- **`app/templates/fragments/ai/coach_brew_picker.html`**: Stub picker template listing sessions as links to `/brew/{id}/edit`. Full hx-trigger wiring is in plan 19-06.

**Test results:** 5 passed (test_ai_improve.py)

### Task 3: Chart JSON routes + charts.py + latency query (VIZ-01/AIX-13/D-17)

- **`app/services/charts.py`**:
  - `rating_over_time(db, user_id)`: raw SQL UNION of `brew_sessions.rating` + `cafe_logs.rating`, last 90 days, ordered by date. Returns `[{date: str, rating: float}]`.
  - `flavor_distribution(db, user_id)`: raw SQL UNION of `flavor_note_ids_observed` + `flavor_note_ids` unnested, JOINed to `flavor_notes`, top-15 by count, NO rating floor. Returns `[{descriptor: str, count: int}]`.
  - Both use bound `:user_id` parameter (T-19-18, no string interpolation).

- **`GET /ai/charts/rating-over-time`**: Returns `JSONResponse(charts.rating_over_time(db, user.id))`.
- **`GET /ai/charts/flavor-distribution`**: Returns `JSONResponse(charts.flavor_distribution(db, user.id))`.

- **`test_latency_percentile_query`** (appended to test_analytics_perf.py): `PERCENTILE_CONT(0.50)` and `PERCENTILE_CONT(0.95)` WITHIN GROUP query over `ai_recommendations.duration_ms` grouped by `recommendation_type`, last 30 days. Verifies the query runs without error (AIX-13/D-15).

**Test results:** 3 passed (test_ai_charts.py) + 1 passed (test_latency_percentile_query)

**Combined: 15 passed, 0 skipped.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Async generator mock needed `return_value` not `AsyncMock(side_effect=...)`**
- **Found during:** Task 1 TDD GREEN — `test_research_cache_hit_no_quota_decrement` failing with `TypeError: 'coroutine' object is not iterable`
- **Issue:** `generate_coffee_research` is an `async def` generator (returns an async generator object when called). `AsyncMock(side_effect=fn)` treats `fn` as a coroutine factory and awaits it, but async generators aren't awaitable.
- **Fix:** Changed all test mocks to `MagicMock().return_value = _gen()` — calling the generator function at setup time to produce the async generator object as the return value.
- **Files modified:** `tests/routers/test_ai_research.py`, `tests/routers/test_ai_improve.py`
- **Commit:** 3d3f59c (fixed inline before GREEN commit)

**2. [Rule 2 - Missing] Removed unused imports from charts.py (ruff F401)**
- `func`, `select` from SQLAlchemy, `BrewSession`, `CafeLog`, `FlavorNote` from models — all unused since charts.py uses raw SQL `text()` not ORM constructs.
- **Fix:** Cleaned up to only import `text`, `Row`, `Session`.
- **Commit:** 3d3f59c

### Style fixes (ruff)

- `I001` import sorting in charts.py and all test files
- `F401` unused imports in test files (AsyncMock, MagicMock, json)
- `F841` unused local variables (mock_ai_service, mock_research, mock_analytics)
- `E501` long line in test docstrings and assert messages

## Known Stubs

- `GET /ai/coach` returns `fragments/ai/coach_brew_picker.html` — the template is a functional stub (renders session list as edit links). Plan 19-06 will wire `hx-trigger="load"` on the edit page and the full Alpine x-show expand pattern.
- `POST /ai/research` and `POST /ai/improve-brew/{id}` stream via `generate_coffee_research` / `generate_brew_improvement` from plans 19-03/19-04. Those service functions have their own stubs for `_render_research_result` (returns minimal HTML). Plan 19-06 wires the real Jinja2 templates.

## Threat Surface Scan

Reviewing against plan's threat register — all mitigations applied:

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-19-16 | Quota check keyed to `request.state.user.id`; DB-backed; checked BEFORE `EventSourceResponse` starts |
| T-19-17 | `get_brew_session(db, session_id=..., by_user_id=user_id)` → `HTTPException(404)` on None |
| T-19-18 | Both chart queries use bound `:user_id` parameter; no cross-user leakage |
| T-19-19 | `generate_coffee_research` / `generate_brew_improvement` emit short user-facing string on error (implemented in 19-03/04); routes don't add new error surfaces |
| T-19-20 | `EventSourceResponse(..., headers={"X-Accel-Buffering": "no"})` on all SSE responses |

No new network endpoints beyond what the plan specified.

## Self-Check: PASSED

Files exist:
- `app/routers/ai.py` — FOUND (POST /ai/research, GET /ai/research/quota, POST /ai/improve-brew/{id}, GET /ai/coach, GET /ai/charts/rating-over-time, GET /ai/charts/flavor-distribution)
- `app/services/charts.py` — FOUND
- `app/templates/fragments/ai/coach_brew_picker.html` — FOUND
- `tests/routers/test_ai_research.py` — FOUND (6 tests)
- `tests/routers/test_ai_improve.py` — FOUND (5 tests)
- `tests/routers/test_ai_charts.py` — FOUND (3 tests)
- `tests/services/test_analytics_perf.py` — FOUND (test_latency_percentile_query appended)

Source assertions:
- `grep -n "X-Accel-Buffering" app/routers/ai.py` → "no" header on all SSE EventSourceResponse calls FOUND
- `grep -n "EventSourceResponse" app/routers/ai.py` → POST /ai/research + POST /ai/improve-brew FOUND
- `grep -n "rating_over_time" app/services/charts.py` → FOUND
- `grep -n "HTTPException(status_code=404" app/routers/ai.py` → IDOR guard FOUND

Commits exist:
- b435d34: test(19-05): add failing tests for research/improve/charts routes (RED)
- 3d3f59c: feat(19-05): wire research/improve/charts routes + charts.py (GREEN)
