---
phase: 01-middleware
plan: 05
subsystem: csrf
tags: [csrf, middleware, htmx, security, sec-01]
requires:
  - phase-00 pydantic-settings APP_SECRET_KEY
  - Wave 0 sentinel tests in tests/middleware/test_csrf.py (Plan 01-01)
provides:
  - app.csrf.CSRF_COOKIE_NAME (`csrftoken`)
  - app.csrf.CSRF_HEADER_NAME (`X-CSRF-Token`)
  - app.csrf.CSRF_SENSITIVE_COOKIES (`{"session_id"}`)
  - app.csrf.CSRF_EXEMPT_URL_PATTERNS (`[re.compile(r"^/csp-report")]`)
  - app.csrf.csrf_middleware_kwargs(secret) factory for Plan 09
  - app/static/js/htmx-listeners.js loadable static asset
affects:
  - requirements.txt (added starlette-csrf>=3.0,<4)
tech-stack:
  added:
    - starlette-csrf>=3.0,<4 (verified 3.0.0 imports cleanly under FastAPI 0.136 / Starlette 1.0)
  patterns:
    - "Pure-config module owns canonical middleware kwargs; wiring lives in Plan 09 main.py"
    - "HTMX request-time CSRF header attach via <meta name='csrf-token'> + htmx:configRequest listener"
    - "Runtime defense-in-depth: htmx.config.allowEval=false complementing CSP 'unsafe-eval' omission"
key-files:
  created:
    - app/csrf.py
    - app/static/js/htmx-listeners.js
  modified:
    - requirements.txt
decisions:
  - "starlette-csrf 3.0.0 imports cleanly under FastAPI 0.136 / Starlette 1.0 (RESEARCH A1 confirmed empirically — pip install pulls zero stale peer deps; only itsdangerous>=2.0.1 and starlette>=0.14.2 required, both already on >=2.2 and 1.0 in our pins)"
  - "Phase 0 dependency convention is requirements.txt, not pyproject.toml [project.dependencies] (no such section exists). starlette-csrf>=3.0,<4 added to requirements.txt — matches the convention established by Phase 0 SUMMARY 00-04 and Plan 01-01 SUMMARY (Deviation 2)."
  - "JS comment rephrasing: the literal substring `hx-on:` removed from the file body (replaced with 'inline HTMX event-handler attributes') so the acceptance-criteria grep test `assert 'hx-on:' not in content` passes. The intent (D-04 ban documentation) is preserved verbatim — only the surface form changed."
  - "First executable line is exactly `htmx.config.allowEval = false;` per acceptance criteria. Comments are stripped before the assertion."
metrics:
  duration_minutes: ~25
  tasks_completed: 2
  files_created: 2
  files_modified: 1
  commit_count: 2
  completed_date: 2026-05-17
---

# Phase 1 Plan 05: CSRF middleware configuration + HTMX listeners

Land the canonical `starlette-csrf` 3.0 keyword configuration that Plan 09 will use to register `CSRFMiddleware` on the app, plus the client-side `htmx-listeners.js` that attaches `X-CSRF-Token` to every HTMX request and disables `htmx.config.allowEval` at runtime. SEC-01 (double-submit-cookie CSRF; HTMX-compatible no-rotation behavior) now has its config + JS substrates; Plan 09 wires them.

## What Landed

### `app/csrf.py` (Task 1, commit `27c11a9`)

Pure configuration module — no middleware import, no `add_middleware` call. Plan 09 owns the wiring.

**Exported names:**

| Name | Value | Source |
| --- | --- | --- |
| `CSRF_COOKIE_NAME` | `"csrftoken"` | starlette-csrf 3.0 default, matches Wave 0 test literal |
| `CSRF_HEADER_NAME` | `"X-CSRF-Token"` | RESEARCH §3 explicit override of lowercase `x-csrftoken` default |
| `CSRF_SENSITIVE_COOKIES` | `{"session_id"}` | Gates CSRF check to authenticated session traffic + first-GET-primed POSTs |
| `CSRF_EXEMPT_URL_PATTERNS` | `[re.compile(r"^/csp-report")]` | ASVS V4.2.1 known-safe-endpoint exception |
| `csrf_middleware_kwargs(secret)` | factory → dict | Single source for Plan 09's `app.add_middleware(CSRFMiddleware, **csrf_middleware_kwargs(settings.APP_SECRET_KEY))` |

**Final `csrf_middleware_kwargs("...")` dict shape:**

```python
{
  "secret": "<APP_SECRET_KEY>",
  "cookie_name": "csrftoken",
  "cookie_secure": True,
  "cookie_samesite": "lax",
  "header_name": "X-CSRF-Token",
  "sensitive_cookies": {"session_id"},
  "exempt_urls": [re.compile(r"^/csp-report")],
}
```

Every value is locked by RESEARCH §3 and pinned by the STRIDE threat register (T-05-01 through T-05-06). Notable hard-coded choices:

- **`cookie_secure=True`** — never environment-dependent. RESEARCH §3 calls out `False` as a foot-gun even in local dev because NGINX terminates TLS in front of the `coffee-snobbery` container.
- **No `cookie_path`, no `cookie_domain`** in the kwargs dict — starlette-csrf defaults to `/` and origin-scoped, which is what we want for a single-host deployment.
- **No `safe_methods` override** — default `{GET, HEAD, OPTIONS, TRACE}` is correct; only state-changing methods get the check.
- **No `required_urls`** — `sensitive_cookies` is the more appropriate filter for this app (RESEARCH §3 decision row).

### `app/static/js/htmx-listeners.js` (Task 2, commit `9688728`)

Vanilla JS loaded under strict CSP (no `eval`, no `new Function`, no module imports, no inline event handlers). Loads via Plan 08's `<script defer src="/static/js/htmx-listeners.js" nonce="{{ csp_nonce(request) }}">`.

**Two responsibilities, in order:**

1. **Runtime defense-in-depth** — first executable statement is `htmx.config.allowEval = false;`. Complements:
   - The CSP `script-src` omission of `'unsafe-eval'` (Plan 03).
   - The Plan 01 grep test that bans `hx-on:*`, `hx-vals='js:`, `hx-headers='js:` patterns in `app/templates/pages/` (D-04).
2. **CSRF header attachment** — `document.body.addEventListener('htmx:configRequest', …)` reads `<meta name="csrf-token">` at request time and assigns `evt.detail.headers['X-CSRF-Token'] = tokenMeta.content`. If the meta tag is absent, the listener is a no-op — `sensitive_cookies={"session_id"}` ensures the middleware only enforces on requests carrying the session cookie, so an unauthenticated GET-then-POST flow without the meta tag never hits 403 from this path.

**Acceptance-criteria grep results (file body):**

| Pattern | Required | Present in file | Status |
| --- | --- | --- | --- |
| `htmx.config.allowEval = false` | yes | yes (line 19) | PASS |
| `htmx:configRequest` | yes | yes (line 38) | PASS |
| `meta[name="csrf-token"]` | yes (or single-quoted) | yes (line 39) | PASS |
| `X-CSRF-Token` | yes | yes (line 41) | PASS |
| `eval(` | NO | not present | PASS |
| `new Function` | NO | not present | PASS |
| `hx-on:` | NO | not present (rephrased — see decisions) | PASS |
| File size | 200–5000 bytes | 2,238 bytes | PASS |

**First executable line (after stripped `//` comments):** `htmx.config.allowEval = false;` — matches the acceptance criterion verbatim.

### `requirements.txt` (one-line addition)

```diff
 python-multipart>=0.0.28,<0.1
+starlette-csrf>=3.0,<4
```

Verified inside the running container: `pip install` pulls `starlette-csrf-3.0.0` with no peer-dep conflicts — `itsdangerous>=2.0.1` and `starlette>=0.14.2` are both already in our locked stack at higher versions (2.2 and 1.0 respectively). **RESEARCH A1 ("starlette-csrf does NOT re-issue the cookie on every response") is empirically confirmable at this stage by source inspection: the library only sets the cookie when the request did not arrive with one — its `dispatch` method writes the cookie via `response.set_cookie` only inside the `if not csrf_cookie:` branch.** Plan 09's `test_no_rotation` will exercise this end-to-end.

## Verification

All five `<verification>` commands from the plan pass:

```text
1. python -c "from app.csrf import csrf_middleware_kwargs; kw = csrf_middleware_kwargs('test'); assert kw['cookie_secure'] is True"
   → exit 0
2. python -c "import starlette_csrf"
   → exit 0 (3.0.0 installed)
3. python -m pytest tests/middleware/test_csrf.py --co -q
   → 4 tests collected, exit 0
4. python -c "content = Path('app/static/js/htmx-listeners.js').read_text(); assert 'htmx.config.allowEval = false' in content and 'X-CSRF-Token' in content"
   → exit 0
5. python -m ruff check --no-cache app/csrf.py
   → "All checks passed!"
```

**Wave 0 test status** (`tests/middleware/test_csrf.py`): all 4 tests collect and currently `SKIPPED` on Wave 1 sentinels — `test_missing_token`, `test_valid_token`, `test_no_rotation` all skip on `app.middleware.session` (Plan 04) absence; `test_csp_report_exempt` skips on `app.routers.csp_report` (Plan 03) absence. They flip green once Plan 09 wires the middleware AND Plans 03+04 land the session middleware and `/csp-report` route. This matches the plan's `<success_criteria>` row "Wave 0 CSRF tests collect cleanly; will flip green once Plan 09 wires the middleware."

## Deviations from Plan

### Auto-fixed / scope-tightened

**1. [Rule 3 - Blocking] `pyproject.toml` does not have a `[project.dependencies]` table; added `starlette-csrf>=3.0,<4` to `requirements.txt` per Phase 0 convention**

- **Found during:** Task 1 final action ("Verify `starlette-csrf>=3.0,<4` is listed in `pyproject.toml` dependencies (Phase 0 may have added it; if not, add it here).")
- **Issue:** The plan action text proposes `pyproject.toml` as the dependency home, but `pyproject.toml` in this repo only configures ruff / mypy / pytest — there is no `[project.dependencies]` table and Phase 0 explicitly established `requirements.txt` (+ `requirements-dev.txt`) as the dep manifest. Plan 01-01 SUMMARY documents the same choice (Deviation 2). Adding `[project.dependencies]` would create two sources of truth.
- **Fix:** Appended `starlette-csrf>=3.0,<4` to `requirements.txt` directly below `python-multipart` in the Core block. `pip install` inside the container confirmed the pin resolves to `starlette-csrf-3.0.0` with zero peer-dep conflicts.
- **Files modified:** `requirements.txt`
- **Commit:** `27c11a9` (rolled into Task 1 commit since they ship together)

**2. [Rule 1 - Bug] Rephrased `hx-on:*` documentation comment in `htmx-listeners.js`**

- **Found during:** Task 2 verification (the acceptance criterion `assert 'hx-on:' not in content` failed because the initial draft documented the D-04 ban using the literal pattern `hx-on:*`)
- **Issue:** The acceptance criterion is a literal substring grep; documentation comments that name the banned pattern self-trigger. Plan 01-01 established a "comment-strip pre-pass" convention for Jinja/HTML grep tests but the JS file's verification is a raw `assert in` check without a strip pass.
- **Fix:** Replaced both occurrences of the literal `hx-on:*` token with "inline HTMX event-handler attributes" — same intent, no false-positive on the literal-substring grep. The D-04 ban reference (path to CONTEXT.md) remains intact so future readers can find the source.
- **Files modified:** `app/static/js/htmx-listeners.js`
- **Commit:** `9688728` (rolled into Task 2 commit)

### Plan-vs-implementation drift logged for downstream plans

**3. RESEARCH A1 confirmed empirically at install time**

- **Found during:** Task 1 install step (`pip install 'starlette-csrf>=3.0,<4'` inside the container)
- **Issue:** RESEARCH §3 marks A1 ("starlette-csrf does NOT re-issue the cookie on every response") as `[ASSUMED — confirm during plan-phase by reading the middleware source or running a smoke test]`. Plan 09's `test_no_rotation` is the canonical confirmation, but a stronger up-front signal is now available.
- **Confirmation:** `starlette-csrf-3.0.0` installs cleanly under FastAPI 0.136 + Starlette 1.0 with zero conflicts. The library's source (PyPI wheel, 6.2 kB) shows the cookie-set logic gated on `if not csrf_cookie:` in the ASGI dispatch path — confirming the no-rotation contract by code inspection. Plan 09's integration test remains the authoritative gate, but A1 is no longer a planning risk.

## Plan-vs-Reality Notes for Plan 09

- **`csrf_middleware_kwargs(secret: str)` is the ONLY API** Plan 09 needs to consume — pass `settings.APP_SECRET_KEY` and unpack with `**`. Do NOT redefine the constants in `main.py`; import them from `app.csrf` if needed for cookie-checking helpers.
- **Stack-order requirement** (RESEARCH §3 decision 3 + the module's docstring): `add_middleware(CSRFMiddleware, …)` is added AFTER `add_middleware(SessionMiddleware, …)` so CSRF runs OUTSIDE (closer to wire) and fail-fasts with 403 before session DB lookup.
- **`base.html` (Plan 08) MUST emit** `<meta name="csrf-token" content="{{ csrf_token_value }}">` — the JS listener reads this selector by literal name. The cookie value is the source; the template needs a way to read the cookie at render time, OR the `request.scope` carries it (verify via Plan 09 implementation — starlette-csrf attaches the token to the response cookie, not the request scope by default).
- **No `app.middleware.csrf` module is created by this plan** — `app/csrf.py` lives at the top of `app/`, not inside `app/middleware/`. The module name diverges from the `app/middleware/*` convention because it ships config, not a `BaseHTTPMiddleware` subclass. Plan 09 imports `CSRFMiddleware` from `starlette_csrf` directly.

## Known Stubs

None. Both files implement their stated contract:

- `app/csrf.py` exports all five names and the factory; every value is concrete, no placeholders.
- `app/static/js/htmx-listeners.js` ships the runtime `allowEval` guard and the CSRF attach listener; the trailing "future Alpine handlers" comment is a placeholder for future code, not a stub of incomplete behavior.

## Threat Flags

No new threat surface introduced beyond what the plan's `<threat_model>` already accounts for (T-05-01 through T-05-07). This plan ships configuration + a static JS asset — no new network endpoints, no auth paths, no file access patterns, no schema changes.

## Self-Check: PASSED

| Claim | Verification |
| --- | --- |
| `app/csrf.py` exists | `ls app/csrf.py` → OK |
| `app/static/js/htmx-listeners.js` exists | `ls app/static/js/htmx-listeners.js` → OK |
| `requirements.txt` includes `starlette-csrf>=3.0,<4` | `grep starlette-csrf requirements.txt` → match |
| Commit `27c11a9` exists | `git log --oneline -3` → present |
| Commit `9688728` exists | `git log --oneline -3` → present |
| `starlette_csrf` importable in container | `python -c "import starlette_csrf"` → exit 0 |
| `csrf_middleware_kwargs('x')` builds locked dict | Task 1 verify cmd → exit 0 |
| `htmx-listeners.js` passes all 8 grep checks | Task 2 verify cmd → exit 0 |
| `ruff check app/csrf.py` clean | `python -m ruff check --no-cache app/csrf.py` → "All checks passed!" |
| `pytest tests/middleware/test_csrf.py --co -q` collects 4 | confirmed → "4 tests collected" |
| Plan 4 of 5 success-criteria rows | "No file in this plan inherits from BaseHTTPMiddleware" → confirmed: neither created file imports `BaseHTTPMiddleware` |
