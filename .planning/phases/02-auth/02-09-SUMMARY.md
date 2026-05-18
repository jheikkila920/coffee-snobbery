---
phase: 02-auth
plan: 09
subsystem: auth
tags: [fastapi, depends, debug-proxy, admin-gate, require_admin, D-14, AUTH-09]

# Dependency graph
requires:
  - phase: 01-middleware
    provides: "app.routers.debug + /debug/proxy public route + module-level _require_debug_proxy() test helper (D-16 hand-off promise)"
  - phase: 02-auth
    provides: "Plan 02-03 require_admin Depends callable; Plan 02-06 request.state.user as a real User row (D-09); Plan 02-01 seeded_admin_user / seeded_regular_user conftest fixtures"
provides:
  - "Admin-only /debug/proxy (Form 2 — dependencies=[Depends(require_admin)])"
  - "Three-state admin-gate test pattern (anon 401/403, non-admin 403, admin 200) reusable for the new /admin route in Plan 02-08 and any future admin-gated routers"
  - "Updated Phase 1 tests carrying seeded_admin_user signed_cookie for routes that were public in Phase 1 and gated in Phase 2"
affects: [02-08, 02-10, 02-11, future admin-gated routers, operator runbook (curl /debug/proxy now requires admin cookie)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Form 2 admin gate on existing routes: minimum-diff one-line dependencies=[Depends(require_admin)] when the handler does not need the User object"
    - "Three-state test (anon / non-admin / admin) per admin-gated route — anonymous accepts 401 OR 403 to avoid coupling to require_admin's chosen disclosure-minimising 403"

key-files:
  created:
    - .planning/phases/02-auth/02-09-SUMMARY.md
  modified:
    - app/routers/debug.py
    - tests/routers/test_debug_proxy.py

key-decisions:
  - "Form 2 (decorator dependencies=[Depends(require_admin)]) chosen over Form 1 (handler parameter) — the existing debug_proxy handler does not need the User object, so Form 2 is the minimum-diff change per 02-RESEARCH §FastAPI Depends Form 2."
  - "Preserved the existing xfail on test_https_via_proxy_header — the xfail reason (Starlette TestClient does not invoke uvicorn's ProxyHeadersMiddleware) is independent of D-14 and still applies; the test now ALSO carries an admin cookie so it reaches the proxy-header assertion path rather than 403'ing before."
  - "Three-state test asserts anon ∈ {401, 403} (not strictly 403) — require_admin folds anonymous into 403 per CONTEXT D-13 / disclosure-minimisation, but the AUTH-09 VALIDATION row 'anon → 401 OR 403' permits either; tests should not over-constrain that choice."

patterns-established:
  - "Pattern: admin-gating an existing route — three lines of code (import Depends, import require_admin, add dependencies=[...] to decorator) + module docstring refresh."
  - "Pattern: rewriting Phase 1 tests for Phase 2 gates — drop in the seeded_admin_user fixture, pass cookies={'session_id': seeded_admin_user['signed_cookie']}, preserve the existing assertion shape."

requirements-completed:
  - AUTH-09

# Metrics
duration: 4min
completed: 2026-05-17
---

# Phase 02 Plan 09: /debug/proxy Admin Gate Summary

**`/debug/proxy` is now admin-gated via `Depends(require_admin)` (Form 2), closing the Phase 1 D-16 hand-off and exposing the Phase 2 D-14 promise as a three-state pytest assertion.**

## Performance

- **Duration:** 4 min (251 s)
- **Started:** 2026-05-18T01:30:30Z
- **Completed:** 2026-05-18T01:34:41Z
- **Tasks:** 2 / 2
- **Files modified:** 2

## Accomplishments

- Wrapped `/debug/proxy` in `dependencies=[Depends(require_admin)]` — minimum-diff Form 2 change.
- Refreshed `app/routers/debug.py` module docstring to state the route is admin-gated as of Phase 2 D-14.
- Added `test_debug_proxy_admin_only` — three-state assertion (anonymous → 401/403, non-admin → 403, admin → 200 with the four documented body keys).
- Rewrote the two existing tests (`test_default_returns_shape`, `test_https_via_proxy_header`) to seed an admin user and present the `signed_cookie`, so they continue passing after the gate closes.

## Task Commits

Each task was committed atomically:

1. **Task 1: Modify `app/routers/debug.py` — wrap debug_proxy in Depends(require_admin)** — `0c9d4ca` (feat)
2. **Task 2: Extend `tests/routers/test_debug_proxy.py` with three-state admin-gate test + update existing tests for the admin cookie** — `9e98051` (test)

## Files Created/Modified

- `app/routers/debug.py` — added `Depends` + `require_admin` imports, added `dependencies=[Depends(require_admin)]` to the `@router.get("/debug/proxy", ...)` decorator, refreshed module docstring for D-14. Handler body unchanged.
- `tests/routers/test_debug_proxy.py` — added `test_debug_proxy_admin_only`; updated `test_default_returns_shape` and `test_https_via_proxy_header` to use `seeded_admin_user` + cookie. Existing `_require_debug_proxy()` helper reused. xfail on the proxy-header test preserved (independent reason).
- `.planning/phases/02-auth/02-09-SUMMARY.md` — this file.

## Decisions Made

- **Form 2 (`dependencies=[...]`) over Form 1 (handler-parameter `user: User = Depends(require_admin)`)** — `debug_proxy(request)` does not consume the `User` object, so binding it as a handler parameter would add an unused argument. Form 2 is the minimum-diff change per 02-RESEARCH §FastAPI Depends. The threat model (T-02-09-2) is fully covered: `require_admin` raises 403 before the handler runs, regardless of whether the handler binds the return value.
- **Permissive anon assertion** — `r_anon.status_code in (401, 403)` rather than `== 403`. `require_admin` chose 403 for anonymous per CONTEXT D-13 (disclosure-minimisation: 401-then-403 leaks "you're logged in but not admin" on the second response). The VALIDATION map already permits either; the test follows VALIDATION, not implementation.
- **Preserved the xfail on `test_https_via_proxy_header`** — the xfail reason (TestClient bypasses ProxyHeadersMiddleware) is orthogonal to D-14. The test now also carries the admin cookie so it reaches the proxy-header assertion path; the xfail stays in place and is logged in `01-HUMAN-UAT.md` for post-deploy verification via `curl -i https://snobbery.example.com/debug/proxy`.

## Deviations from Plan

None — plan executed exactly as written. The Form 2 decorator-dependencies kwarg was rendered on three lines instead of the single-line form shown in 02-PATTERNS.md §line 459, matching the multi-line form spelled out verbatim in the plan's `<action>` block (lines 116-123 of 02-09-PLAN.md). Both forms parse identically.

## Issues Encountered

None.

## Verification

- `docker compose exec -T coffee-snobbery python -m pytest -x tests/routers/test_debug_proxy.py` → **2 passed, 1 xfailed** (the xfail is the documented proxy-header test).
- `ruff check app/routers/debug.py app/dependencies/` → **All checks passed.**
- `ruff check tests/routers/test_debug_proxy.py` → **All checks passed.**
- Static AST verification: `/debug/proxy` route's `dependencies=[...]` kwarg references `require_admin`. ✓

## Threat Mitigation

| Threat ID | Disposition | Mitigation realised |
|---|---|---|
| T-02-09-1 (InfoDisc: public /debug/proxy leaks proxy config) | mitigate | `Depends(require_admin)` returns 403 for anon and non-admin before the handler runs. `test_debug_proxy_admin_only` asserts all three paths. ASVS V4.1.1 / V4.1.2. |
| T-02-09-2 (EoP: non-admin reads admin diagnostic) | mitigate | Same gate. `require_admin` distinguishes `is_admin=True` from `is_active=True` (Plan 02-03), and Plan 02-06 supplies the real `User` row in `request.state.user` carrying the canonical `is_admin` flag. ASVS V4.1.3. |

No new threats flagged.

## User Setup Required

None.

## Next Phase Readiness

- Plan 02-08 (`/admin` stub) can reuse the same Form 1 / Form 2 choice — for `/admin` the handler will likely WANT the `User` object (to render `current_user.username` in the template), so Form 1 is appropriate there.
- Plan 02-10 (`/login`, `/logout`, `/setup` GET) and Plan 02-11 (`/login`, `/logout`, `/setup` POST) inherit the same `seeded_admin_user` / `seeded_regular_user` conftest fixtures from Plan 02-01 and the same three-state test pattern documented here.
- Operator runbook update needed: post-deploy smoke checks against `/debug/proxy` now require an admin session cookie (or curl via the deployed admin's signed session). Existing `curl https://snobbery.example.com/debug/proxy` from public will return 403 — that's the point.

## Self-Check: PASSED

Verified before SUMMARY commit:
- `app/routers/debug.py` exists and contains `dependencies=[Depends(require_admin)]` on the `/debug/proxy` route. ✓
- `tests/routers/test_debug_proxy.py` exists and contains `test_debug_proxy_admin_only`. ✓
- Task 1 commit `0c9d4ca` reachable on `worktree-agent-a98f2fd3948c6f1d4`. ✓
- Task 2 commit `9e98051` reachable on `worktree-agent-a98f2fd3948c6f1d4`. ✓
- `pytest -x tests/routers/test_debug_proxy.py` → 2 passed, 1 xfailed (matches plan expectation). ✓
- `ruff check` clean on all touched files. ✓

---
*Phase: 02-auth*
*Plan: 09*
*Completed: 2026-05-17*
