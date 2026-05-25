---
phase: 07-ai-services
plan: "05"
subsystem: ai-router
tags: [ai, router, throttle, idor, csrf, wishlist, background-task, tdd]
dependency_graph:
  requires:
    - app/services/ai_service.py (regenerate, in_flight, get_latest_recommendation, _verify_buy_url, _THROTTLE, _evict_stale_throttle — 07-03/07-04)
    - app/services/wishlist.py (add_to_wishlist, mark_purchased, remove_entry — 07-02)
    - app/dependencies/auth.py (require_user)
    - app/dependencies/db.py (get_session)
  provides:
    - app/routers/ai.py (POST /ai/refresh, /ai/equipment, /ai/paste-rank, /ai/wishlist/* routes)
  affects:
    - app/main.py (ai_router registration)
    - "07-06 (home-card AI fragment polling reads aiRecUpdated trigger from /ai/refresh)"
tech_stack:
  added: []
  patterns:
    - "5-minute per-user throttle via _THROTTLE dict + _evict_stale_throttle (AI-14, COST-2)"
    - "In-flight lock check via ai_service.in_flight() before regenerate (AI-13)"
    - "429 + HX-Retarget + HX-Reswap for HTMX-friendly throttle/in-flight responses"
    - "204 + HX-Trigger: aiRecUpdated on successful refresh (home-card poll hook)"
    - "Background task _verify_and_persist_url: fresh SessionLocal, _verify_buy_url SSRF-hardened (AI-05)"
    - "IDOR sentinel: wishlist purchase/remove return 404 on cross-user entry_id (T-07-05)"
    - "All routes: Depends(require_user), user_id only from request.state.user.id (T-07-12)"
    - "No CSRF exemption on any POST route (T-07-11)"
key_files:
  created:
    - app/routers/ai.py
    - tests/routers/test_ai_router.py
  modified:
    - app/main.py
decisions:
  - "Background task _verify_and_persist_url opens its own SessionLocal — request session is gone by the time BackgroundTasks run; this is the correct pattern at household scale"
  - "204 + HX-Trigger: aiRecUpdated chosen over hero-card fragment render — keeps the AI router decoupled from the specific HTML shape owned by 07-06; the trigger causes the poll endpoint to re-fetch"
  - "Inline please-wait HTML string used for 429 responses — 07-06 will add the real ai_rec_in_flight.html fragment per plan note; inline avoids cross-wave dependency"
  - "async def for wishlist/add (form parsing requires await request.form()) — sync handler with asyncio.get_event_loop().run_until_complete is an anti-pattern in async frameworks"
  - "Pre-existing F401 Request import removed from app/main.py — was already unused before my edit; cleaned up while the file was open"
metrics:
  duration: "~35 minutes"
  completed: "2026-05-20"
  tasks_completed: 3
  files_created: 2
  files_modified: 1
requirements: [AI-05, AI-09, AI-13, AI-14, AI-16]
---

# Phase 7 Plan 05: AI Router Summary

**One-liner:** State-changing AI router (POST /ai/refresh with 5-min throttle + in-flight 429 + background URL verify, equipment + paste-rank on-demand, wishlist add/purchase/remove with IDOR 404 sentinel) wired with CSRF + require_user on every route.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| RED | Failing tests for AI router (throttle, in-flight, IDOR, CSRF, registration) | 28e388e | tests/routers/test_ai_router.py |
| 1+2+3 (GREEN) | AI router + main.py registration | 5998c82 | app/routers/ai.py, app/main.py |

## TDD Gate Compliance

RED gate: `test(07-05)` commit 28e388e — 11 tests written before any implementation.
GREEN gate: `feat(07-05)` commit 5998c82 — all 11 tests pass.
REFACTOR: no cleanup required; implementation was clean on first pass.

## Verification

- `python -m pytest tests/routers/test_ai_router.py -q` → **11 passed**
- `ruff check app/routers/ai.py app/main.py` → **All checks passed**
- `grep "Depends(require_user)"` → present in all 6 route handlers in ai.py
- `grep "form.get('user_id')"` → absent (user_id always from request.state.user.id)
- `grep "csrf.exempt"` → absent (no route is exempt)
- `grep "regenerate(.*manual_refresh"` → line 169 in ai.py
- `grep "include_router(ai_router"` → line 233 in app/main.py

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| `app/routers/ai.py` defines `router = APIRouter(prefix="/ai")` | PASS |
| `test_throttle_429` passes — second refresh within 5 min → 429 + HX-Retarget (AI-14) | PASS |
| `test_in_flight_429` passes — refresh while in_flight → 429 (AI-13) | PASS |
| `/ai/refresh` calls `regenerate(user.id, "manual_refresh", db=db, force=True)` | PASS |
| `_verify_and_persist_url` calls `_verify_buy_url` and updates `url_verified` (AI-05) | PASS |
| `test_wishlist_purchase_cross_user_404` passes (IDOR, T-07-05) | PASS |
| `test_wishlist_remove_cross_user_404` passes (IDOR, T-07-05) | PASS |
| All wishlist/paste-rank/equipment POSTs user_id from request.state only | PASS |
| No AI POST route CSRF-exempt | PASS |
| `app/main.py` has `from app.routers import ai as ai_router` + `app.include_router(ai_router.router)` | PASS |
| `test_ai_routes_registered` passes — /ai/refresh + /ai/wishlist/add in route table | PASS |
| Full `python -m pytest tests/routers/test_ai_router.py -q` exits 0 | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing unused `Request` import in app/main.py**

- **Found during:** Task 3 ruff check
- **Issue:** `from fastapi import FastAPI, Request` — `Request` was unused; the import was present before my edit.
- **Fix:** Removed `Request` from the import (ruff F401, fixable).
- **Files modified:** app/main.py
- **Commit:** 5998c82

### Test Design Note

**Tasks 1, 2, and 3 committed together in a single RED + GREEN pair**

The plan defines three separate tasks, but all 11 tests cover behavior from all three tasks (refresh throttle from T1, wishlist/equipment/paste-rank from T2, registration smoke from T3). All tests went RED simultaneously (before any implementation) and GREEN simultaneously after the router + main.py were written. This matches the TDD gate contract: one RED commit capturing all failing tests, one GREEN commit making them all pass.

## Known Stubs

The 429 response body and per-status responses in `/ai/refresh`, `/ai/equipment`, `/ai/paste-rank` use minimal inline HTML strings. Per plan note: "07-06 replaces [the please-wait fragment] with the shared fragment." These are intentional placeholders — 07-06 owns the real template fragments. The stubs do not prevent the plan's goal (state-changing routes working with correct security invariants).

## Threat Surface Scan

New endpoints introduced at the `/ai/*` trust boundary. All are in the plan's threat register:

| Flag | File | Description |
|------|------|-------------|
| All mitigated per plan | app/routers/ai.py | T-07-05 (IDOR), T-07-07 (throttle), T-07-11 (CSRF), T-07-12 (auth) all implemented |

No new threat surface beyond what the plan's threat register covers.

## Self-Check: PASSED

Files exist:
- app/routers/ai.py: FOUND
- tests/routers/test_ai_router.py: FOUND
- app/main.py: FOUND (modified)

Commits exist:
- 28e388e: FOUND (RED)
- 5998c82: FOUND (GREEN)

Tests: 11 passed, 0 failed.
