---
phase: 02-auth
plan: 04
subsystem: csrf
tags: [csrf, asgi, middleware, wave-1, d-15, starlette-csrf]

# Dependency graph
requires:
  - phase: 01-middleware
    provides: starlette-csrf 3.0 wired via app.csrf.csrf_middleware_kwargs (Plan 01-05); pure-ASGI middleware shape established by app.middleware.fragment_cache.FragmentCacheHeadersMiddleware
  - phase: 02-auth
    provides: tests/conftest.py fixtures landed in Plan 02-01 (this plan does not consume them — its tests are self-contained against a Starlette echo app)
provides:
  - "app.csrf.CSRFFormFieldShim — pure-ASGI middleware that hoists the X-CSRF-Token form field into scope['headers'] before downstream starlette-csrf CSRFMiddleware sees the request"
  - "tests/middleware/test_csrf_form_shim.py — five D-15 integration cases (header passthrough, form-field hoist, multipart body preservation, GET passthrough, JSON passthrough) running against a contained Starlette echo app"
  - "app.csrf.__all__ — newly added public symbol list including CSRFFormFieldShim alongside the existing constants and csrf_middleware_kwargs"
affects: [phase 02 plan 02-10 (main.py wiring will mount the shim), phase 02 plans 02-06/02-07/02-08 (the auth routes' form POSTs will now successfully carry CSRF tokens once Plan 02-10 lands)]

# Tech tracking
tech-stack:
  added: [urllib.parse.parse_qsl for form-body token extraction, starlette.types ASGIApp/Message/Receive/Scope/Send for pure-ASGI signature]
  patterns:
    - "ASGI receive-replay: buffer http.request events into list[tuple[bytes, bool]] preserving body chunks AND more_body flags; rebuild a fresh receive() that pops in original order"
    - "Pure-ASGI middleware shell (mirrors fragment_cache.FragmentCacheHeadersMiddleware): gate on scope['type'] != 'http' first, then scope-header inspection via raw byte keys"
    - "Multipart token extraction without instantiating Starlette's MultiPartParser: boundary-aware byte-scan (name=\"X-CSRF-Token\"\\r\\n\\r\\n needle) against the already-buffered body"

key-files:
  created:
    - "tests/middleware/test_csrf_form_shim.py — 189 lines; five D-15 cases against a contained Starlette echo app; lazy-import Wave-1 skip for app.csrf.CSRFFormFieldShim"
  modified:
    - "app/csrf.py — APPENDED CSRFFormFieldShim class (lines 93-274) + __all__ (lines 277-284) + two imports (parse_qsl, starlette.types); existing constants and csrf_middleware_kwargs (lines 38-90) byte-identical to pre-plan state"

key-decisions:
  - "Used byte-scan (not MultiPartParser) for multipart token extraction: the body is already buffered, scanning bytes for `name=\"X-CSRF-Token\"\\r\\n\\r\\n` followed by the boundary marker is O(n) and exact. Starlette's parser is async-iterator-based and would consume the body again, defeating the buffer-and-replay invariant."
  - "Kept disconnect handling defensive (not strict): if the first message after gating is not http.request (disconnect, malformed client), re-emit it and exit. ASGI contract guarantees http.request first, but defensiveness costs nothing and avoids an exception path."
  - "Wrapped both token-extraction branches in try/except → token=None: a malformed body must NEVER raise into the middleware stack. When parsing fails the shim is a no-op and CSRFMiddleware will 403 as expected — the double-submit pattern still holds, just via the strict fail-closed path."

requirements-completed: [AUTH-03, AUTH-07]

# Metrics
duration: 4min
completed: 2026-05-18
---

# Phase 02-auth Plan 04: CSRFFormFieldShim ASGI Middleware Summary

**Pure-ASGI middleware that hoists the `X-CSRF-Token` hidden form field into `scope['headers']` so classic HTML form POSTs at `/setup`, `/login`, `/logout` clear the downstream `starlette-csrf` 3.0 CSRFMiddleware header check (D-15).**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-18T00:57:36Z
- **Completed:** 2026-05-18T01:00:58Z
- **Tasks:** 2 (1 RED test gate + 1 GREEN implementation gate)
- **Files modified:** 2 (1 created, 1 appended)

## Accomplishments

- D-15 resolved: classic-HTML-no-JS auth POSTs can now carry the CSRF token through to downstream `CSRFMiddleware` without requiring a JS fetch shim (D-05's locked direction).
- Five D-15 verification rows from `02-VALIDATION.md` lines 67-71 satisfied with executable tests; all PASS.
- `app/csrf.py` body-replay machinery is generic enough that future Phase-4 photo uploads (multipart with CSRF token) inherit it for free.
- `app/csrf.py` `__all__` introduced as a side-benefit: explicit public surface for downstream consumers.
- No regression: existing `tests/middleware/test_csrf.py` continues to skip cleanly (its xfail / Wave-1 skip semantics are preserved).

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Add failing tests for CSRFFormFieldShim** — `a9ccf65` (test)
2. **Task 2 (TDD GREEN): Append CSRFFormFieldShim to app/csrf.py** — `69b5000` (feat; bundled the ruff-format follow-up that removed one redundant blank line from the test file)

## Files Created/Modified

- `tests/middleware/test_csrf_form_shim.py` — NEW, 189 lines.
  - Five integration tests (`test_get_passthrough`, `test_header_passthrough`, `test_form_field_hoisted`, `test_multipart_body_preserved`, `test_json_passthrough`) against a contained Starlette echo app wrapped by `CSRFFormFieldShim`.
  - Wave-1 lazy-import skip via `_require_shim()` so the file is collectable before Task 2 lands.
  - Module-level `CAPTURE` dict cleared at the top of each test to keep ordering deterministic; cannot use a fixture because the echo endpoint must be a module-level callable that Starlette can resolve by name.
- `app/csrf.py` — APPENDED 189 lines (Task 2). Pre-plan lines 1-87 are byte-identical except for:
  - Added imports at lines 34-36: `from urllib.parse import parse_qsl`, `from starlette.types import ASGIApp, Message, Receive, Scope, Send`.
  - Added `CSRFFormFieldShim` class (lines 93-274).
  - Added `__all__` (lines 277-284).

## Decisions Made

- **Byte-scan multipart parsing, not Starlette `MultiPartParser`:** the buffered body is already in memory; a needle scan for `name="X-CSRF-Token"\r\n\r\n` plus a boundary-aware end marker is O(n), zero allocations beyond the slice, and immune to whatever async-consumption semantics `MultiPartParser` uses. The library parser would require re-feeding the body through a SpooledTemporaryFile pathway, defeating the buffer-and-replay invariant.
- **`try/except` on both token-extraction branches → `token = None`:** a malformed urlencoded or multipart body must never crash the middleware. When parsing fails the shim is a no-op; CSRFMiddleware then 403s on the missing header. This preserves the double-submit fail-closed property.
- **`__all__` newly introduced:** the plan instructed to add it. Sorted lexically (`CSRF_COOKIE_NAME, CSRF_EXEMPT_URL_PATTERNS, CSRF_HEADER_NAME, CSRF_SENSITIVE_COOKIES, CSRFFormFieldShim, csrf_middleware_kwargs`).
- **Test app self-contained, not the FastAPI app:** the plan explicitly recommends this; isolates the shim's behavior from anything else in `app/main.py`. The actual mounting + cross-stack verification happens in Plan 02-10.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test-file import block formatting**

- **Found during:** Task 2 verification (`ruff check`)
- **Issue:** `ruff check` flagged `I001` (unsorted imports) on `tests/middleware/test_csrf_form_shim.py` due to a redundant blank line between the `import os` block and `import pytest`. CLAUDE.md requires "treat warnings as errors" for ruff.
- **Fix:** Ran `ruff check --fix tests/middleware/test_csrf_form_shim.py` which removed one blank line. Test still passes (no semantic change).
- **Files modified:** `tests/middleware/test_csrf_form_shim.py` (bundled into Task 2 commit `69b5000`).
- **Verification:** `ruff check app/csrf.py tests/middleware/test_csrf_form_shim.py` → All checks passed.

**2. [Rule 1 - Bug] `app/csrf.py` ruff format**

- **Found during:** Task 2 verification (`ruff format --check`)
- **Issue:** `ruff format --check` flagged `app/csrf.py` because the appended class used a one-line function-default expression that ruff prefers wrapped across lines. CLAUDE.md requires `ruff format` clean before commit.
- **Fix:** Ran `ruff format app/csrf.py` to apply the canonical formatting. Pre-existing lines 1-90 untouched.
- **Files modified:** `app/csrf.py` (bundled into Task 2 commit `69b5000`).
- **Verification:** `ruff format --check app/csrf.py` → already formatted.

**Total deviations:** 2 auto-fixed (both formatting; zero behavior change).
**Impact on plan:** None — both are lint/format hygiene caught by CLAUDE.md's "treat warnings as errors" gate. The functional behavior is identical to the plan's spec.

## Issues Encountered

- **Docker compose stack not bound to worktree code:** identical issue as documented in Plan 02-01 SUMMARY — the running `coffee-snobbery` container is from the main repo's image, not this worktree's tree. The plan's verification commands (`docker compose exec coffee-snobbery pytest ...`) would run against the wrong tree. Worked around by running `python -m pytest` directly on the host. Host has Python 3.14.5 + pytest 9.0.3 + starlette 1.0 + pytest-asyncio 1.3 installed and resolves `app.csrf` from the worktree's `app/` directly.
- **Mypy unavailable on host AND in container image:** CLAUDE.md §2 lists mypy as a recommended dev dep but it's not in `requirements.txt` and not in the running image. The success criterion "`mypy app/csrf.py` clean" can only be verified once a dev-image with mypy installed exists. The shim's signature uses explicit `ASGIApp / Scope / Receive / Send / Message` types imported from `starlette.types` (the same types the existing `fragment_cache.FragmentCacheHeadersMiddleware` uses cleanly), so the type-check would pass by inspection.
- **Pre-existing `slowapi` `DeprecationWarning`:** Python 3.14 surfaces `asyncio.iscoroutinefunction` deprecation noise from slowapi 0.1.9. Not caused by this plan; will be fixed when slowapi ships a 3.14-compatible release (or we monkey-patch / vendor). Logged for future hygiene.

## User Setup Required

None. The shim is library code with no environment, secrets, or new env vars. Plan 02-10 will wire it into `app/main.py`; until then it sits in `app.csrf` as dead-but-tested code.

## Next Phase Readiness

- **Plan 02-10** (`app/main.py` middleware mounting) can now `from app.csrf import CSRFFormFieldShim` and call `app.add_middleware(CSRFFormFieldShim)` at the position locked by D-15: AFTER `CSRFMiddleware`, BEFORE `FragmentCacheHeadersMiddleware` (Starlette's reverse-of-add order puts the shim OUTSIDE / BEFORE CSRFMiddleware on the request path).
- **Plans 02-06 / 02-07 / 02-08** (the `/setup`, `/login`, `/logout` routes) can render the canonical `<input type="hidden" name="X-CSRF-Token" value="...">` form pattern without a JS fetch shim. The classic-HTML-no-JS path now works end-to-end (once Plan 02-10 lands).
- **Phase 4** (photo upload) inherits multipart-safe body buffering by virtue of mounting through this shim — the byte-for-byte body-preservation guarantee carries over.

## Self-Check: PASSED

**Created files verified:**
- `tests/middleware/test_csrf_form_shim.py` — FOUND (189 lines, 5 tests, all passing).
- `.planning/phases/02-auth/02-04-SUMMARY.md` — FOUND (this file).

**Modified files verified:**
- `app/csrf.py` — FOUND (extended; AST imports cleanly; `from app.csrf import CSRFFormFieldShim` succeeds; existing `csrf_middleware_kwargs` still callable and unchanged).

**Commits verified:**
- `a9ccf65` — FOUND in `git log --oneline -3` (Task 1, test).
- `69b5000` — FOUND in `git log --oneline -3` (Task 2, feat).

**Verification automation:**
- `python -m pytest -x tests/middleware/test_csrf_form_shim.py -v` → 5 passed in 6.52s.
- `python -m pytest tests/middleware/test_csrf.py -v` → 4 skipped (Wave-1 deps not landed); no errors.
- `python -m ruff check app/csrf.py tests/middleware/test_csrf_form_shim.py` → All checks passed.
- `python -m ruff format --check app/csrf.py tests/middleware/test_csrf_form_shim.py` → 2 files already formatted.

## TDD Gate Compliance

- **RED gate:** commit `a9ccf65` is `test(02-04): add failing tests for CSRFFormFieldShim (D-15)` — adds 5 tests that SKIP cleanly because `CSRFFormFieldShim` does not yet exist.
- **GREEN gate:** commit `69b5000` is `feat(02-04): add CSRFFormFieldShim ASGI middleware per D-15` — adds the class; the 5 tests now PASS.
- **REFACTOR gate:** not required (the implementation is the minimum to pass the tests; no refactor commit emitted).

Sequence verified: `test(...)` → `feat(...)` in `git log --oneline -3`.

---
*Phase: 02-auth*
*Completed: 2026-05-18*
