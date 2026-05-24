---
phase: quick-260524-hg6
plan: 01
subsystem: middleware / exception-handling
tags: [auth, redirect, htmx, exception-handler]
dependency_graph:
  requires: [app/dependencies/auth.py (raises 401)]
  provides: [browser redirect to /login on 401, HX-Redirect on HTMX 401]
  affects: [every require_user-gated route]
tech_stack:
  added: []
  patterns: [StarletteHTTPException handler, http_exception_handler delegation]
key_files:
  created:
    - tests/middleware/test_unauthorized_redirect.py
  modified:
    - app/main.py
decisions:
  - "Single global handler on StarletteHTTPException (not FastAPI's HTTPException) catches both; branches only on status_code==401; all other statuses delegate to the default handler unchanged — 403 admin no-leak is intentionally untouched"
  - "HTMX branch: 401 + HX-Redirect header (client-side redirect, no DOM swap) — uses status 401 not 204 so the HTMX client knows auth failed before navigating"
  - "Accept header detection via 'text/html' in request.headers.get('accept','') — consistent with fragment_cache.py idiom; TestClient default */* falls into the JSON branch, preserving all existing test_home.py 401 assertions"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-24"
  tasks: 2
  files: 2
---

# Phase quick-260524-hg6 Plan 01: Redirect Unauthenticated Requests to /login Summary

**One-liner:** Single StarletteHTTPException handler in app/main.py redirects unauthenticated browser requests to /login (303 full-page or HX-Redirect for HTMX), while preserving JSON 401 for API clients and leaving all non-401 statuses unchanged.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add StarletteHTTPException handler + registration in app/main.py | 60482d0 | app/main.py |
| 2 | Add focused tests covering three 401 branches + non-regression | 1b8c648 | tests/middleware/test_unauthorized_redirect.py |

## What Was Done

**Task 1 — app/main.py:**
- Added imports: `Request` (extended existing FastAPI import), `RedirectResponse`, `Response` (extended existing responses import), `http_exception_handler` (from fastapi.exception_handlers), `StarletteHTTPException` (from starlette.exceptions).
- Defined `async def unauthorized_redirect_handler(request, exc)` with a three-branch 401 dispatch: HTMX -> 401+HX-Redirect, browser Accept:text/html -> 303 RedirectResponse, else -> default handler delegation.
- Non-401 statuses immediately delegate via `await http_exception_handler(request, exc)`.
- Registered via `app.add_exception_handler(StarletteHTTPException, unauthorized_redirect_handler)` inside `create_app()`, after `register_rate_limiter(app)`, mirroring the rate_limit.py idiom exactly.

**Task 2 — tests/middleware/test_unauthorized_redirect.py:**
- 5 tests: browser 303, HTMX HX-Redirect 401, JSON client 401, unknown-path 404 (non-401 delegation), healthz 200.
- Uses `_require_postgres()` skip gate mirroring test_home.py.
- `follow_redirects=False` on all navigation tests so 303s are asserted, not followed.

## Verification Results

**ruff format + ruff check:** Clean on both files.

**pytest result (host):** `6 skipped in 11.55s` — the host lacks `email-validator`, so the conftest `app` fixture takes its ImportError skip path. Skips, not passes: NOT acceptable as verification on their own.

**pytest result (container — canonical gate, orchestrator-run after a `docker compose build coffee-snobbery-test` to bake in the 2 new files):**
```
docker compose run --rm coffee-snobbery-test \
  tests/middleware/test_unauthorized_redirect.py tests/routers/test_home.py -rs --tb=short
==> 30 passed, 2 warnings in 10.00s
```
- 5 new tests + all 25 in `tests/routers/test_home.py` (incl. the `test_home_unauthenticated_returns_401` regression guard) **passed, 0 skipped, 0 failed.**
- `test_home_unauthenticated_returns_401` uses TestClient's default `*/*` Accept (no text/html), which falls into the JSON-client branch and still returns 401 JSON — the existing assertion is preserved exactly as intended. Regression confirmed clear.

**Staged file discipline:**
- Task 1 commit: `git diff --cached --name-only` showed only `app/main.py`. Unrelated changes (`.claude/settings.local.json`, `docs/DEPLOY.md`) were never staged.
- Task 2 commit: `git diff --cached --name-only` showed only `tests/middleware/test_unauthorized_redirect.py`.

## Deviations from Plan

None — plan executed exactly as written. Both files match the plan's scope lock. No router, dependency, or auth file was touched.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The handler only rewrites the presentation of 401 responses already raised by existing `require_user` dependencies. Threat mitigations T-hg6-01, T-hg6-02, T-hg6-03 are satisfied:
- Redirect target is hardcoded `/login` — no request data in Location/HX-Redirect value.
- Handler never grants access, never sets sessions, never bypasses auth.
- Standard Response/RedirectResponse objects traverse the existing middleware stack unchanged.
