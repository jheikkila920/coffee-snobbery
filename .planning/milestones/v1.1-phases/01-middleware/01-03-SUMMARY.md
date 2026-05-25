---
phase: 01-middleware
plan: 03
subsystem: middleware
tags: [middleware, csp, security-headers, csp-report, rate-limit, wave-1]
requires:
  - phase-00 FastAPI factory (app.main)
  - phase-00 structlog (configure_logging, _redact_sensitive_keys)
  - phase-01-plan-02 RequestContextMiddleware (mints scope["state"]["csp_nonce"])
  - phase-01-plan-07 slowapi pin in requirements.txt (replaces rate_limit stub)
  - phase-01-plan-09 main.py middleware + router wiring
provides:
  - app/middleware/security_headers.py SecurityHeadersMiddleware (pure ASGI)
  - app/middleware/security_headers.py CSP_TEMPLATE, CSP_FALLBACK, STATIC_HEADERS module constants
  - app/middleware/__init__.py re-exports SecurityHeadersMiddleware
  - app/routers/csp_report.py router with POST /csp-report (dual content-type)
  - app/events.py CSP_VIOLATION event constant (D-14 taxonomy)
  - app/rate_limit.py TEMPORARY no-op limiter stub (Plan 07 replaces)
affects:
  - app/middleware/__init__.py (package docstring + __all__)
  - app/routers/__init__.py (package docstring)
tech-stack:
  added:
    - structlog (already pinned in Phase 0; this plan adds new usage sites)
  patterns:
    - "Pure ASGI middleware: send_wrapper closure intercepts http.response.start; body chunks pass through untouched"
    - "Defensive scope-state read: scope.get('state', {}).get('csp_nonce', '') with fail-closed fallback"
    - "Module-load security invariants: raise RuntimeError on policy regression (survives python -O)"
    - "Stub-with-fallback: try real slowapi; except ImportError use no-op shim with identity decorator"
    - "Dual content-type CSP report normalisation: legacy hyphenated keys preferred, modern camelCase as fallback"
key-files:
  created:
    - app/middleware/security_headers.py
    - app/routers/csp_report.py
    - app/rate_limit.py
    - app/events.py
    - .planning/phases/01-middleware/01-03-SUMMARY.md
  modified:
    - app/middleware/__init__.py
    - app/routers/__init__.py
decisions:
  - "Ship app/events.py here (Rule 3 - blocking) rather than wait for Plan 02. CSP_VIOLATION is the only constant introduced; later Wave 1 plans add their event names to the same module."
  - "Make app/rate_limit.py a self-sufficient stub that falls through to slowapi when present (try/except ImportError). slowapi is not yet pinned in requirements.txt; pinning is Plan 07's responsibility."
  - "Reorder import: starlette.types Message is included alongside ASGIApp/Receive/Scope/Send for the send_wrapper signature type-hint. Plan text said 'typing Any' for the message; Starlette already exports the canonical Message type so we use that directly."
  - "Replace module-load `assert` checks with `if not ...: raise RuntimeError` to satisfy ruff S101 and survive python -O (asserts are stripped under -O; security invariants must not be)."
metrics:
  duration_minutes: ~35
  tasks_completed: 2
  files_created: 5
  files_modified: 2
  test_count_added: 0
  commit_count: 2
  completed_date: 2026-05-17
---

# Phase 1 Plan 03: Response-header layer (CSP + standard headers + /csp-report) Summary

Ship the response-header layer locked in CONTEXT D-05: a pure ASGI `SecurityHeadersMiddleware` that appends CSP (nonce-aware), the four standard hardening headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy), and the modern `Reporting-Endpoints` header on every HTTP response. Plus `POST /csp-report` — a log-only endpoint per D-06 handling both legacy `application/csp-report` and modern `application/reports+json` bodies, rate-limited 30/min/IP via a temporary stub that Plan 07 will replace with real slowapi wiring.

Net result: SEC-02 (nonce-based CSP, no `'unsafe-eval'`, no `'unsafe-inline'` for scripts), SEC-03 (full hardening header set), and D-06 (log-only violation endpoint) are all delivered as code. Wave 0 tests collect cleanly; full green flip requires Plan 09 (which wires the middleware + router into `app/main.py`).

## What Landed

### `app/middleware/security_headers.py` (Task 1)

Pure ASGI `SecurityHeadersMiddleware`. Key shape:

- `__init__(self, app: ASGIApp)` — stateless; stores downstream app reference.
- `async def __call__(self, scope, receive, send)`:
  - Lifespan + websocket scopes pass through unchanged.
  - HTTP scopes: wraps `send` so `http.response.start` carries the headers; body chunks untouched.
  - Reads `scope.get("state", {}).get("csp_nonce", "")` — Plan 02's contract.
  - Nonce present: substitutes via `CSP_TEMPLATE.format(nonce=...)`.
  - Nonce absent: uses `CSP_FALLBACK` (`script-src 'self'` with no nonce term — fails closed, blocking all inline scripts) AND emits a `csp.nonce_missing` WARNING with `path` + `method` context.

Module constants (verifiable from tests without instantiating the middleware):

| Constant | Type | Purpose |
| --- | --- | --- |
| `CSP_TEMPLATE` | `str` (f-string-ready) | D-05 directive list with `{nonce}` placeholder |
| `CSP_FALLBACK` | `str` | Same directives minus nonce terms; used when state is empty |
| `STATIC_HEADERS` | `tuple[tuple[bytes, bytes], ...]` | 5 entries: X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, Reporting-Endpoints |

Module-load invariants raise `RuntimeError` if `'unsafe-eval'` appears in `CSP_TEMPLATE` or `'unsafe-inline'` escapes the `style-src-attr` directive. Implemented as `raise` not `assert` so they survive `python -O`.

### Final `CSP_TEMPLATE` value (for ADR cross-reference in Plan 10)

```
default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src-elem 'self' 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; report-uri /csp-report; report-to csp-report
```

13 directives, `; ` separator, no trailing semicolon. Both `report-uri` (legacy) and `report-to` (modern Reporting API) ship together so we collect reports from both old and new browsers concurrently per D-05.

### `app/routers/csp_report.py` (Task 2)

`router = APIRouter()` exposing `POST /csp-report` decorated with `@limiter.limit("30/minute")`. Returns 204 unconditionally — even on malformed JSON or unknown body shape — because browsers don't read the body and a non-204 risks retry amplification (pitfall §13.5).

Dispatch logic:

| Content-Type | Body shape | Action |
| --- | --- | --- |
| `application/reports+json` + `isinstance(raw, list)` | `[{"type": "csp-violation", "body": {...}}, ...]` | One `_log_csp_violation(report["body"], ip)` per array element |
| `dict` with `"csp-report"` key | `{"csp-report": {...}}` | One `_log_csp_violation(raw["csp-report"], ip)` |
| Other | anything | One low-severity info-level event with `shape="unknown"` |
| Malformed JSON | n/a (caught at `await request.json()`) | Silent — return 204 without logging |

`_log_csp_violation(payload, ip)` normalises both key vocabularies to four fields:

| Field | Legacy key | Modern key |
| --- | --- | --- |
| `blocked_uri` | `blocked-uri` | `blockedURL` |
| `violated_directive` | `violated-directive` | `effectiveDirective` |
| `line` | `line-number` | `lineNumber` |
| `source_file` | `source-file` | `sourceFile` |

All other browser-supplied keys are silently dropped (threat T-03-07 — Referer URLs can carry tokens). The fifth field `ip` comes from `request.client.host` (post `--proxy-headers` rewrite); `"unknown"` substitution when client is missing.

Logged event name is `CSP_VIOLATION` from `app.events` — no literal `"csp.violation"` string anywhere in the router.

### `app/rate_limit.py` (Task 2 — TEMPORARY stub)

Self-sufficient module that:

1. Tries `from slowapi import Limiter; from slowapi.util import get_remote_address` and constructs a real `Limiter` if present.
2. Falls through to a `_NoOpLimiter` shim on `ImportError` that exposes one method: `.limit(rate_str)` returning an identity decorator.

API surface locked to `limiter.limit(rate_str)` so Plan 07's swap-in is mechanical — `csp_report.py` does NOT change when Plan 07 lands. `test_rate_limit` Wave 0 test remains red until Plan 07 (because the no-op shim serves every request) — by design.

### `app/events.py` (Task 1 — new module)

Single constant: `CSP_VIOLATION = "csp.violation"`. Plan 02 (request_context), Plan 04 (sessions/csrf), Plan 06 (fragment cache), Plan 07 (rate-limit), Plan 08 (debug proxy) will each add their own event names to this same module per D-14.

Created here (rather than waiting for Plan 02) because Plan 03's csp_report router needs to import `CSP_VIOLATION` and Plan 02 had not landed it under Wave 1 parallelism. See deviation §1 below.

## Verification

All 5 `<verification>` commands from the plan pass:

```text
1. python -c "from app.middleware.security_headers import SecurityHeadersMiddleware, CSP_TEMPLATE; from app.routers.csp_report import router; from app.rate_limit import limiter"      -> exit 0
2. python -m pytest tests/middleware/test_security_headers.py tests/routers/test_csp_report.py --co -q     -> 7 tests collected, exit 0
3. ruff check app/middleware/security_headers.py app/routers/csp_report.py app/rate_limit.py app/routers/__init__.py app/middleware/__init__.py app/events.py     -> exit 0
4. grep -c BaseHTTPMiddleware app/middleware/security_headers.py    -> 0
5. 'unsafe-eval' not in CSP_TEMPLATE; 'unsafe-inline' only in style-src-attr segment      -> OK
```

### Adhoc isolation tests (not in the plan but ran to gain confidence)

Built a minimal Starlette app with `SecurityHeadersMiddleware` + a fake nonce-injector middleware and confirmed:

- CSP includes the per-request nonce in both `script-src` and `style-src-elem` positions.
- `script-src` directive contains neither `'unsafe-eval'` nor `'unsafe-inline'`.
- All 5 STATIC_HEADERS land on the response.
- Without the nonce-injector, the fallback CSP (no nonce term) is emitted and a `csp.nonce_missing` WARNING fires.

Built a minimal FastAPI app with `app.routers.csp_report.router` and confirmed:

- Legacy `application/csp-report` POST returns 204 + emits one structured `csp.violation` event with `blocked_uri` + `violated_directive` from hyphenated keys.
- Modern `application/reports+json` POST (array) returns 204 + emits one event per array element with camelCase keys normalised.
- Malformed JSON returns 204 silently (no log line).
- Unknown body shape returns 204 + emits one info-level `csp.violation` event with `shape="unknown"`.

## Status of Wave 0 tests (security_headers + csp_report)

| Test | Status today | Why | Turns green when |
| --- | --- | --- | --- |
| `test_csp_present` | SKIPPED | `app/main.py` import fails on host (Tailwind CSS hash missing); skip cascades from the `client` fixture | Plan 09 + Docker test run with built Tailwind |
| `test_nonce_uniqueness` | SKIPPED | same | same |
| `test_no_unsafe_eval` | SKIPPED | same | same |
| `test_all_headers` | SKIPPED | same | same |
| `test_legacy_format` | SKIPPED | same | same |
| `test_reporting_api_format` | SKIPPED | same | same |
| `test_rate_limit` | SKIPPED | same; ALSO depends on real slowapi limiter | Plan 07 swaps the stub for real slowapi + Plan 09 wires middleware |

The plan's acceptance criteria explicitly anticipate this: "may still skip if `app.main:app` isn't wired up yet; Plan 09 finalizes — at MINIMUM, the tests must collect and ImportError-skip cleanly here." That minimum is met: all 7 tests collect cleanly and skip with explicit reasons. The router and middleware **work in isolation** (confirmed via adhoc test above) — the test skip is purely a wiring artifact, not a code defect.

## Deviations from Plan

### Auto-fixed / scope-tightened

**1. [Rule 3 - Blocking] Created `app/events.py` here rather than waiting for Plan 02**

- **Found during:** Task 2 (writing `csp_report.py`'s `from app.events import CSP_VIOLATION`)
- **Issue:** Plan 03's `<read_first>` and `<action>` both reference `app/events.py:CSP_VIOLATION`, but Plan 02 (which is the natural home for the events taxonomy module under Wave 1 parallelism) had not landed it yet. The import would fail at module collection time, blocking Task 2.
- **Fix:** Created `app/events.py` with a single constant `CSP_VIOLATION = "csp.violation"` and a module docstring stating that Plan 02 (request_context), Plan 04 (sessions/csrf), Plan 06 (fragment cache), Plan 07 (rate-limit), Plan 08 (debug proxy) each contribute additional constants here per D-14. Plan 02 should add its own constants (likely `REQUEST_START`, `REQUEST_END`, or similar) to the existing file; merge conflict risk is low because each plan adds a new constant, not a rewrite.
- **Files modified:** `app/events.py` (created)
- **Commit:** `1c7ec15`

**2. [Rule 2 - Critical functionality] Switched `assert` -> `raise RuntimeError` for module-load invariants**

- **Found during:** Task 1 lint check
- **Issue:** Initial implementation used `assert "'unsafe-eval'" not in CSP_TEMPLATE` for module-load policy invariants. Ruff S101 fires on `assert` outside test code (correct: `python -O` strips `assert` statements, so the security invariant would silently disappear under production-style optimisation flags).
- **Fix:** Converted both module-load checks to `if <bad-condition>: raise RuntimeError(...)`. This survives `-O` and is the right shape for a security invariant.
- **Files modified:** `app/middleware/security_headers.py`
- **Commit:** `1c7ec15`

**3. [Rule 3 - Blocking] `app/rate_limit.py` made resilient to slowapi absence**

- **Found during:** Task 2 import test
- **Issue:** Plan action proposed `from slowapi import Limiter` at module top. slowapi is not yet pinned in `requirements.txt` (Plan 07 ships the pin). Without slowapi installed, `from app.rate_limit import limiter` would fail at collection time across the entire app, blocking both the csp_report tests and any future router that decorates routes with `@limiter.limit(...)`.
- **Fix:** Wrapped the slowapi import in `try/except ImportError` and provided a `_NoOpLimiter` shim with identity decorator. Plan 07 swaps the file outright when it pins slowapi and adds the 429 handler — the `@limiter.limit("30/minute")` decoration in `csp_report.py` does not change. Tested locally: under the no-op shim, the route function is unmodified (identity decorator); the test of rate limiting (`test_rate_limit`) stays red until Plan 07 lands.
- **Files modified:** `app/rate_limit.py`
- **Commit:** `9280135`

**4. [Rule 2 - Critical functionality] `Message` import from `starlette.types`**

- **Found during:** Task 1 type hints
- **Issue:** Plan action listed `from typing import Any` for the send_wrapper parameter. Starlette already exports a canonical `Message` type; using it gives better type-safety and matches the pattern future middleware in Phase 1 should follow.
- **Fix:** `from starlette.types import ASGIApp, Message, Receive, Scope, Send`; the `send_wrapper` parameter is typed `message: Message`.
- **Files modified:** `app/middleware/security_headers.py`
- **Commit:** `1c7ec15`

### Plan-vs-implementation drift logged for the planner

**5. Plan 07 dependency on slowapi pin in `requirements.txt`**

- **Found during:** Task 2 setup
- **Issue:** `requirements.txt` does NOT yet list `slowapi`. Plan 07's text says it "wires the final limiter" but doesn't explicitly call out pinning slowapi as part of its scope. Suggest Plan 07 explicitly add `slowapi>=0.1.9,<0.2` (per STACK.md) to requirements.txt as its first task, then update `app/rate_limit.py`. Until Plan 07 lands the pin, the stub's `try: from slowapi import Limiter` branch is dead code on the host but harmless (the `_NoOpLimiter` fallback works).

**6. Plan 02 may also need to create `app/events.py`**

- **Found during:** Task 1 / 2 cross-check
- **Issue:** Under Wave 1 parallelism, Plan 02 may also try to create `app/events.py`. The merge conflict will be trivial (two plans adding different constants) but the planner should call this out in Plan 02's `files_modified:` frontmatter (currently it lists files_created only and may not anticipate Plan 03 having pre-shipped the module).

## Known Stubs

**1. `app/rate_limit.py` is a TEMPORARY stub.** Plan 07 replaces it outright with the final slowapi wiring (real `Limiter`, `RateLimitExceeded` handler, `app.state.limiter` registration, `/login` + `/setup` rate-limit decoration). API surface is locked: any consumer using `from app.rate_limit import limiter` and `@limiter.limit("...")` will keep working after the swap. The `test_rate_limit` Wave 0 test (`tests/routers/test_csp_report.py::test_rate_limit`) is the canonical signal that the swap completed: it goes from SKIPPED -> PASSED once Plan 07 lands.

No other stubs. The middleware and `/csp-report` router work end-to-end in isolation (verified via adhoc test above).

## Threat Flags

No new threat surface beyond the plan's `<threat_model>` register. The threat dispositions are honoured as follows:

| Threat ID | Disposition | Implementation |
| --- | --- | --- |
| T-03-01 (XSS via inline scripts) | mitigate | CSP_TEMPLATE: `script-src 'self' 'nonce-{nonce}'`; no `'unsafe-eval'` or `'unsafe-inline'` for scripts |
| T-03-02 (clickjacking) | mitigate | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` (both shipped) |
| T-03-03 (MIME-confusion) | mitigate | `X-Content-Type-Options: nosniff` |
| T-03-04 (Referrer leakage) | mitigate | `Referrer-Policy: strict-origin-when-cross-origin` |
| T-03-05 (Feature abuse) | mitigate | `Permissions-Policy: camera=(self), microphone=(), geolocation=(), interest-cohort=(), payment=(), usb=(), bluetooth=()` |
| T-03-06 (`/csp-report` flood) | mitigate | `@limiter.limit("30/minute")` decoration + no DB writes in handler + malformed-JSON swallow |
| T-03-07 (PII in report bodies) | mitigate | `_log_csp_violation` strips to 4 documented fields only; every other key is dropped before structlog emit |
| T-03-08 (forged Reporting-Endpoints) | accept | Same-origin-only; impossible to redirect off-origin without already controlling the response headers |
| T-03-09 (csp_nonce missing) | mitigate | `CSP_FALLBACK` emits no-nonce `script-src 'self'` + `csp.nonce_missing` WARNING — fails closed |

## Plan-vs-Reality Notes for Plan 04 onward

- **`app/events.py` exists** as of this plan — Plan 02 should add to it rather than replace.
- **`app/rate_limit.py` exists as a stub.** Plan 07 must replace it; the API surface is `limiter.limit(rate_str)` only.
- **`SecurityHeadersMiddleware` is NOT wired in `app/main.py`.** Plan 09 owns the wiring. Until Plan 09 lands, the Wave 0 security_headers + csp_report tests will skip due to `app.main` failing to import (Tailwind CSS hash missing on host; Docker builds work).
- **Plan 02's `RequestContextMiddleware` must set `scope["state"]["csp_nonce"]`** before this middleware runs, OR via Starlette's `request.state` interface (which writes through to `scope["state"]`). Either works — the read side here uses the defensive `scope.get("state", {}).get("csp_nonce", "")` shape.
- **Order matters in Plan 09's middleware stack:** RequestContextMiddleware (Plan 02) must wrap SecurityHeadersMiddleware (Plan 03), so the nonce is in scope state by the time the response.start message fires.

## Self-Check: PASSED

Verified post-write:

| Claim | Verification |
| --- | --- |
| `app/middleware/security_headers.py` exists | `[ -f app/middleware/security_headers.py ]` -> OK |
| `app/routers/csp_report.py` exists | OK |
| `app/rate_limit.py` exists | OK |
| `app/events.py` exists | OK |
| Commit `1c7ec15` exists | `git log --oneline | grep 1c7ec15` -> found |
| Commit `9280135` exists | `git log --oneline | grep 9280135` -> found |
| `pytest --collect-only` on target tests exits 0 | OK (7 collected) |
| `ruff check` on all touched files exits 0 | OK |
| `grep -c BaseHTTPMiddleware app/middleware/security_headers.py` -> 0 | OK |
| `'unsafe-eval' not in CSP_TEMPLATE` | OK |
| `'unsafe-inline'` only in `style-src-attr` segment of `CSP_TEMPLATE` | OK |
| `SecurityHeadersMiddleware` does NOT inherit from `BaseHTTPMiddleware` | OK (pure ASGI shape) |
| `app.middleware.__init__` re-exports `SecurityHeadersMiddleware` in `__all__` | OK |
| `app.routers.csp_report` uses `CSP_VIOLATION` constant (not literal string) | OK (`grep -c 'csp.violation' app/routers/csp_report.py` for literal string -> 0) |
