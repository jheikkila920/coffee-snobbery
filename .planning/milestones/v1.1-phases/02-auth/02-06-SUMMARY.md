---
phase: 02-auth
plan: 06
subsystem: middleware
tags: [middleware, session, auth, d-09, d-10, fail-closed, wave-3]

# Dependency graph
requires:
  - phase: 01-middleware
    provides: app.middleware.session.SessionMiddleware (Phase 1 stub shape), app.services.sessions.delete_session, app.signing.load_session_id
  - phase: 02-auth
    plan: 01
    provides: tests/conftest.py::seeded_admin_user + seeded_regular_user fixtures, tests/conftest.py::fresh_db autouse fixture
provides:
  - "request.state.user is now a SQLAlchemy User ORM row (was {'user_id': int} dict)"
  - "request.state.session is now the matching Session row when authenticated"
  - "D-10 fail-closed: deactivated/deleted user => session row DELETEd + clear-cookie + state.user=None"
  - "test_state_user_shape — D-09 contract assertion (User instance, not dict)"
  - "test_deactivated_user_fail_closed — D-10 inactive-user branch (clear-cookie + DELETE + state.user=None)"
affects:
  - "phase 02 plan 07 (/login can read .username/.is_admin/.email directly)"
  - "phase 02 plan 08 (/admin require_admin reads request.state.user.is_admin)"
  - "phase 02 plan 09 (/debug/proxy admin-gate consumes the new shape)"
  - "phase 02 plan 10 (index template footer renders {{ user.username }})"
  - "phase 04+ catalog routes (will read .username / .email directly)"

# Tech tracking
tech-stack:
  added:
    - "sqlalchemy.select used inside SessionMiddleware (was previously imported only by app/services/sessions.py)"
  patterns:
    - "Function-local model imports inside middleware (defends cyclic-import risk per RESEARCH Open Q6)"
    - "Fail-closed branching: delete_session + clear_cookie=True + state.user=None as a shared idiom across expired/invalid/inactive/deleted paths"
    - "Hand-rolled ASGI scope for middleware unit tests — bypasses FastAPI route mounting, lets tests inspect captured scope['state'] directly"

key-files:
  created:
    - ".planning/phases/02-auth/02-06-SUMMARY.md (this file)"
  modified:
    - "app/middleware/session.py — module docstring updated + sqlalchemy.select import added + lines 177-183 stub branch replaced with D-09 User lookup + D-10 fail-closed (49 insertions, 18 deletions)"
    - "tests/middleware/test_session.py — three new tests appended (183 insertions, 0 deletions)"

key-decisions:
  - "Function-local 'from app.models.user import User' inside the else: branch — RESEARCH Open Q6's conservative recommendation. Cold-import smoke test (from app.main import app) confirms no circular import; module-top import would also work but offers no benefit, so leave the conservative choice in place."
  - "test_deleted_user_fail_closed left as a documented pytest.skip. The FK ON DELETE CASCADE on sessions.user_id makes the 'orphaned session row pointing at a non-existent user' state unreachable in normal operation. The same code branch (user_row is None) shares its fail-closed code path with the inactive-user leaf which test_deactivated_user_fail_closed asserts. Skip text explains the rationale and points at the schema change that would convert it to a real test."
  - "Tests drive SessionMiddleware directly via a hand-rolled ASGI scope rather than mounting a debug route on the FastAPI app. Lets us capture scope['state']['user'] in a closure and assert its concrete type — impossible through TestClient without an extra debug surface that would itself be Phase-2 untouched scaffolding."

patterns-established:
  - "Phase 2+ middleware tests that need to inspect scope['state'] use the 'driver pattern': construct the middleware with a real session_factory, hand-roll a minimal ASGI scope with the required cookie header, capture state in a closure inner-app, await mw(scope, receive, send), assert. Avoids the TestClient-cookie-deprecation warning and the need for ad-hoc debug routes."
  - "Defensive fail-closed branching idiom: any 'session no longer valid' condition (signature tampered, row missing, row expired, user deactivated, user deleted) emits the SAME three actions: delete_session() if there is a row to delete, clear_cookie=True, scope['state']['user']=None + scope['state']['session']=None. The shared shape makes Phase 9 admin tooling (revoke session, deactivate user) trivially correct — every code path the admin can trigger ends in the same SessionMiddleware-cleansed state on the user's next request."

requirements-completed: [AUTH-09]

# Metrics
duration: 12min
completed: 2026-05-18
---

# Phase 02 Plan 06: SessionMiddleware D-09/D-10 Upgrade Summary

D-09 swap of the Phase 1 `{"user_id": int}` stub for a real `User` ORM row + D-10 fail-closed branching that deletes orphaned sessions and clears cookies when the User row is missing or `is_active=false`.

## What changed

- **app/middleware/session.py:** Module docstring updated to describe the new `User`-row shape and the D-10 fail-closed semantics. `from sqlalchemy import select` added at module top. The `else:` branch at lines 177-183 (the Phase 1 stub) is replaced with a User-row lookup performed inside the existing `async with self.session_factory() as db:` block. If the User row is missing OR `is_active=false`, the middleware deletes the session row, sets `clear_cookie=True`, and clears `scope["state"]["user"]` / `scope["state"]["session"]`. Otherwise it sets `scope["state"]["user"] = user_row` (the SQLAlchemy ORM instance) and the existing write-throttled `refresh_last_seen` runs unchanged.
- **tests/middleware/test_session.py:** Three tests appended. `test_state_user_shape` asserts D-09 (`request.state.user` is a `User` instance, not a dict). `test_deactivated_user_fail_closed` asserts D-10 for the inactive-user leaf: clear-cookie header injected, session row DELETEd from DB, `state.user` is None. `test_deleted_user_fail_closed` is a documented `pytest.skip` because the FK `sessions.user_id ON DELETE CASCADE` makes the orphan state unreachable; the same `user_row is None` branch is exercised by the inactive-user test.

## Behavior changes downstream consumers see

```python
# BEFORE (Phase 1 stub)
request.state.user: dict | None  # {"user_id": int} or None
request.state.user["user_id"]    # the only field

# AFTER (D-09)
request.state.user: User | None  # SQLAlchemy ORM row or None
request.state.user.username      # CITEXT-cased original
request.state.user.email         # str | None
request.state.user.is_admin      # bool
request.state.user.is_active     # always True when state.user is non-None (D-10)
request.state.user.id            # what the dict used to expose
```

No Phase 1 routes consumed the dict shape (the only intended consumer, `/debug/whoami`, was never landed in Phase 1 per VALIDATION). Phase 2's `/login`, `/admin`, `/debug/proxy`, and the index template footer are the first consumers of the new shape — they land in later 02-auth plans.

## D-10 fail-closed semantics

Three "session no longer valid" conditions now share the same fail-closed actions inside SessionMiddleware:

| Condition | Actions |
|-----------|---------|
| Tampered / wrong-secret cookie | clear_cookie=True; state.user/session=None |
| Session row missing | clear_cookie=True; state.user/session=None |
| Session row expired | delete_session(); clear_cookie=True; state.user/session=None |
| **User row missing (D-10, new)** | **delete_session(); clear_cookie=True; state.user/session=None** |
| **User is_active=false (D-10, new)** | **delete_session(); clear_cookie=True; state.user/session=None** |

ASVS V3.3.2 (immediate session revocation on deactivation) is satisfied: Phase 9's admin "deactivate user" action will log the user out on their next request — no 30-day wait for the cookie to expire.

## Verification

- `python -m pytest tests/middleware/test_session.py` — 3 passed (existing 1 + new 2), 1 skipped (documented deleted-user skip), 2 xfailed (pre-existing).
- `python -m pytest tests/middleware/` — 13 passed, 1 skipped, 7 xfailed, 0 failed. All other middleware suites (CSRF, fragment cache, logging, security headers) continue to pass.
- `from app.main import app; print(app.title, app.version)` — succeeds inside the running container. No circular-import error from the new model lookup in the middleware.

## Deviations from Plan

None — plan executed exactly as written.

The plan offered two implementation options for `test_state_user_shape` (drive the middleware directly with a hand-rolled ASGI scope, vs. mount a debug route and use TestClient). The plan's preferred option (drive the middleware directly) was the one chosen, so this is "plan executed as written," not a deviation.

The plan offered two implementation options for the User import (function-local inside the else: branch, vs. module-top). The plan's preferred option (function-local, defensive against cyclic imports) was the one chosen. Cold-import smoke test confirmed both forms work, so this is also "plan executed as written."

## Threat Flags

None. The plan's `<threat_model>` enumerated five threats and assigned `mitigate` dispositions to T-02-06-01 (admin deactivation → existing session) and T-02-06-02 (deleted user → orphaned session). Both are mitigated by the D-10 fail-closed branch landed in this plan. No new threat surface beyond what the plan enumerated.

## Self-Check: PASSED

- `app/middleware/session.py` — modified (verified via `git diff HEAD~1 HEAD -- app/middleware/session.py`).
- `tests/middleware/test_session.py` — modified (verified via `git diff HEAD~2 HEAD~1 -- tests/middleware/test_session.py`).
- `.planning/phases/02-auth/02-06-SUMMARY.md` — created by this Write step.
- Commit `b88357c` (test, RED) — present in `git log --oneline`.
- Commit `b71dbbc` (feat, GREEN) — present in `git log --oneline`.
- All `python -m pytest tests/middleware/` tests pass with no regressions.
