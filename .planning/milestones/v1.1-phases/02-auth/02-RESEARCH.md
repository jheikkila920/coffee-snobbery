# Phase 2: Auth — Research

**Researched:** 2026-05-17
**Domain:** First-admin setup, argon2id login, session-ID regeneration, admin gate
**Confidence:** HIGH on library behavior (verified via official docs); MEDIUM on the CSRF-form-field gotcha (verified by reading starlette-csrf 3.0 source).

## Executive Summary

1. **CRITICAL FINDING — CONTEXT D-05 is wrong about starlette-csrf 3.0.** The library's `_get_submitted_csrf_token` reads the token **only from request headers** — it never inspects form bodies. Source confirmed: `return request.headers.get(self.header_name)` is the entire implementation. A `<input type="hidden" name="X-CSRF-Token">` in an HTML form POST will be silently ignored and the middleware will return 403. Phase 2 must either (a) ship a small JS shim that copies `csrftoken` cookie → `X-CSRF-Token` header on form submit, or (b) sub-class `CSRFMiddleware._get_submitted_csrf_token` to fall back to form data, or (c) re-architect to make the auth surfaces submit via HTMX (which already does header-based CSRF via `htmx-listeners.js`). Recommendation: **option (a)** — adds 6 lines of vanilla JS, keeps the locked CSP nonce path, doesn't fork a third-party middleware. This needs an explicit plan-phase decision and possibly a CONTEXT amendment.
2. **argon2-cffi 25.1 PasswordHasher defaults already match ROADMAP requirements** (`time_cost=3, memory_cost=65536, parallelism=4`). No constructor kwargs strictly required — but passing them explicitly is the documented locked-in-code pattern and lets a future ops change be a one-line diff.
3. **argon2-cffi has NO built-in `dummy_verify()`.** Unlike passlib, argon2-cffi expects the application to precompute a dummy hash at import time and call `ph.verify(DUMMY_HASH, password)` (catching `VerifyMismatchError`) on the unknown-user branch. The pattern is community-standard (the issue thread on GitHub confirms it's the expected idiom) but is not documented in the library README. Plan-phase task: module-level `_DUMMY_HASH = ph.hash("dummy-password-for-timing-defense")` constant in `app/services/auth.py`.
4. **All four locking semantics for AUTH-02 are verified by official Postgres 16 + SQLAlchemy 2.0 docs.** `select(...).with_for_update()` on `AsyncSession` holds a row-level exclusive lock across subsequent INSERT/UPDATE in the same transaction; `commit()` releases it; psycopg 3 passes `FOR UPDATE` straight through; a concurrent second `SELECT FOR UPDATE` on the same row blocks until the first transaction commits, then sees the updated row (and exits because `setup_completed=true`). The race protection works as designed.
5. **FastAPI `RedirectResponse(url="/", status_code=303)` preserves `Set-Cookie` headers** — the cookie attached via `response.set_cookie(...)` or via raw header injection is sent in the redirect response, and the browser follows with GET. This is the locked POST-redirect-GET pattern for D-03 (auto-login on setup) and D-05 (login form).

**Primary recommendation:** Resolve the CSRF-form-field gotcha first (the JS shim, sub-class, or HTMX path). Everything else in this phase is well-supported by existing scaffolding — `regenerate_session()` and the cookie builders already do the heavy lifting; the new code is mostly composition of locked helpers behind real route bodies.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Setup flow**

- **D-01: Post-setup behavior — 302 → `/login`.** After `setup_completed=true`, both `GET /setup` and `POST /setup` respond `302 Location: /login`. Resolves the ROADMAP internal conflict (goal sentence said "redirects to `/login`", success criterion #1 said "404s") in favor of the friendlier path. Security cost is nil — the route is read-only post-setup and leaks no information. Update ROADMAP success criterion #1 wording during plan-phase to match.
- **D-02: `/setup` form fields — username + password + REQUIRED email.** The user opted to require email at first-admin setup even though `users.email` is schema-nullable. Rationale: future recovery / notification features have a guaranteed value to work with for at least one user. Phase 9 admin user-create is a separate decision (likely keep email optional there to match the schema).
- **D-03: Auto-login on successful setup.** `POST /setup` happy path: INSERT user → flip `setup_completed=true` (same TX as the user insert) → `regenerate_session(None, new_user_id)` → set signed cookie → `303 See Other` to `/`. One step instead of `/setup` → `/login` → re-type credentials. ROADMAP success criterion #5 ("setup → login → see /") is amended at plan-phase to reflect the auto-login flow.
- **D-04: Setup completion flip is in the SAME transaction as the user INSERT.** The `SELECT … FOR UPDATE` on the `setup_completed` row is held across both the INSERT into `users` AND the UPDATE of `app_settings.setup_completed` from `"false"` to `"true"`. Commit happens once. Race protection only matters if the swap is atomic; AUTH-02 requires this implicitly. Plan-phase locks the SQL.

**Login flow**

- **D-05: Form style — classic HTML POST → 303 See Other.** `<form method="post" action="/login">` (no HTMX on auth surfaces). Server sets `Set-Cookie` on the 303 response and the browser follows to `/`. Works without JS, works under the strict CSP, well-known browser behavior. `/login` and `/setup` are infrequent enough that consistency-with-HTMX doesn't earn its keep. The CSRF token is included as a hidden `<input>` named matching `CSRF_HEADER_NAME` (`X-CSRF-Token`) — `starlette-csrf` 3.0 reads it from either header or form field on POSTs.
  > **NOTE FROM RESEARCH:** the assumption that `starlette-csrf` 3.0 reads from a form field is **incorrect** — see §"starlette-csrf 3.0" below. Plan-phase MUST resolve before locking the template.
- **D-06: Post-login destination — always `/`.** No `?next=` parameter honoring.
- **D-07: Failed-login UX — single generic message + re-render.** "Invalid username or password." rendered above the form with a 200 (not 401 — 200 lets the form re-render cleanly). Same message regardless of "user not found" vs "wrong password", aligned with the Phase 1 D-15 constant-time argon2-verify-on-no-match policy.
- **D-08: Rate-limit 429 response.** Inherit the slowapi handler from Phase 1 D-17 — returns the canonical JSON 429. Default: leave the JSON handler in place.

**Session middleware upgrade**

- **D-09: Load FULL `User` row on every authenticated request.** SessionMiddleware swaps the Phase 1 `{"user_id": int}` stub for a `SELECT users.* WHERE id = :session.user_id` lookup. Sets `scope["state"]["user"] = User`.
- **D-10: Deactivated / deleted user → treat as no session.** If the `User` lookup returns None (deleted) OR returns a row with `is_active=false`, SessionMiddleware: (1) deletes the orphaned session row, (2) sets `clear_cookie = True`, (3) sets `scope["state"]["user"] = None` and `scope["state"]["session"] = None`. Fail-closed.
- **D-11: Stub-to-real upgrade is a SessionMiddleware-internal change, not a new middleware.** Single `User` lookup happens inside the existing `async with self.session_factory()` block. `request.state.user` shifts from "dict-or-None" to "User-or-None"; downstream routes consume the new shape.

**Logout + admin gate**

- **D-12: `/logout` is POST-only with CSRF.** `<form method="post" action="/logout">` rendered in the nav with the CSRF hidden input.
- **D-13: `/admin` Phase-2 stub is one route, one line.** `GET /admin` returns 200 with the literal body `"Admin (stub) — wiring lands in Phase 9"` if `request.state.user` is non-None AND `user.is_admin`, else 403. Returned as a plain HTML page extending `base.html`.
- **D-14: `/debug/proxy` admin-gate.** Wrap the existing `app/routers/debug.py::debug_proxy` route in the same `is_admin` dependency the `/admin` stub uses. Plan-phase introduces a shared `require_admin` FastAPI dependency in `app/dependencies/auth.py` (new module).

### Claude's Discretion

- **Password policy floor:** soft 12-char minimum at the Pydantic schema; no complexity rules; no HIBP. Username 3–32 chars, `[A-Za-z0-9_-]`. Email validated via Pydantic `EmailStr` when provided.
- **Setup template ergonomics:** single scrollable form; "First-time setup — this creates the household admin account." preamble.
- **Login template ergonomics:** "Sign in to Snobbery" heading; username + password; CSRF hidden; submit button; D-07 generic error on failure.
- **Sign-out button location in Phase 2:** placeholder `pages/index.html` gets a "Signed in as {{ user.username }} · <form ...>Sign out</form>" footer when `request.state.user` is non-None.
- **`require_admin` dependency shape:** FastAPI dependency raising `HTTPException(status_code=403)` if `request.state.user is None or not request.state.user.is_admin`. Module location `app/dependencies/auth.py`.
- **Setup-completed read in `GET /setup`:** direct `SELECT value FROM app_settings WHERE key = 'setup_completed'` here (Phase 3 typed reader lands later).
- **Atomic flip mechanics:** SQLAlchemy 2.0 `select().with_for_update()` plus an `update()` call. One commit, FOR UPDATE held across the swap.

### Deferred Ideas (OUT OF SCOPE)

- **"Sign out everywhere" UX** — Phase 1 D-09 already rejected for v1.
- **Password reset / recovery flow** — not in v1; relies on email infrastructure that's out of scope.
- **Breached-password (HIBP k-anonymity) check** — rejected for v1.
- **Complex password policy** — rejected for v1.
- **Periodic expired-session sweep job** — Phase 8.
- **`?next=` query-param support on `/login`** — D-06 punts.
- **HTMX-friendly 429 error template** — D-08 leaves JSON handler in place.
- **`require_active_user` dependency** — Phase 4+ will want it; Phase 2 only ships `require_admin`.
- **Admin email vs personal email separation in `users`** — v2.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | First-run `/setup` flow creates the initial admin user when zero users exist; subsequent visits to `/setup` redirect to `/login` | §Setup transaction (FOR UPDATE + INSERT + UPDATE in one commit); §FastAPI 303 redirect for the post-setup GET/POST 302→/login |
| AUTH-02 | `/setup` uses `SELECT ... FOR UPDATE` on an `app_settings` row to prevent concurrent setup races | §PostgreSQL 16 FOR UPDATE semantics (verified: lock held across statements, released at commit; concurrent second SELECT blocks); §SQLAlchemy 2.0 `select(...).with_for_update()` on AsyncSession |
| AUTH-03 | `/login` accepts username + password; no public registration page | §argon2-cffi `PasswordHasher.verify()`; §Pydantic schema for form-input validation; D-07 generic error |
| AUTH-04 | Passwords hashed with argon2id (memory_cost 64MB, time_cost 3, parallelism 4) | §argon2-cffi defaults align with ROADMAP; §recommendation to pass kwargs explicitly for documentation |
| AUTH-06 | Session cookie is `HttpOnly`, `Secure`, `SameSite=Lax`, signed with `APP_SECRET_KEY` | Already implemented in `build_session_cookie()` (Phase 1); Phase 2 emits via `Set-Cookie` header on the 303 redirect response |
| AUTH-07 | Session ID regenerated (old row deleted, new ID minted) on every successful login, logout, and admin-toggle | Already implemented in `regenerate_session()` (Phase 1); Phase 2 calls it from `/login` happy path, `/setup` auto-login, and `/logout` (the admin-toggle path is Phase 9 — but the helper signature is locked here) |
| AUTH-09 | Admin section gated by `is_admin=true`; returns 403 otherwise | §FastAPI `Depends(require_admin)` pattern (works as parameter or in `dependencies=[]` on route or router) |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Python 3.12 + FastAPI 0.136** — `lifespan` only (no startup/shutdown decorators)
- **SQLAlchemy 2.0 typed `Mapped[...]` + `select()` constructs** — no legacy Query API
- **psycopg 3** — `postgresql+psycopg://` URL prefix (already wired); supports both sync and async off the same URL
- **argon2-cffi for passwords** — explicit; no other hashing scheme
- **itsdangerous for cookie signing** — already wired in `app/signing.py`
- **starlette-csrf 3.0** — already wired in Phase 1 via `app/csrf.py::csrf_middleware_kwargs()`
- **slowapi rate limiter** — already wired; `LOGIN_LIMIT` and `SETUP_LIMIT` constants exist
- **CSRF on all state-changing forms** — applies to `/setup`, `/login`, `/logout`
- **No logging of passwords / session tokens / API keys** — D-15 logging policy (omit `attempted_username` when user not found)
- **Single uvicorn worker** — in-memory rate limiter is consistent
- **Mobile-first** — setup + login templates must look right at 375px
- **Conventional commits** — `feat(02-XX): ...` / `test(02-XX): ...`
- **Jinja autoescape ON** — no `|safe` in templates/pages/

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Password hashing & verify | API / Backend (`app/services/auth.py`) | — | Cryptographic primitive — never on client; server-only |
| Setup row-lock (`SELECT FOR UPDATE`) | API / Backend (`app/services/setup.py`) | Database (Postgres lock manager) | Lock is a Postgres-tier mechanic; Python orchestrates the txn |
| Session-ID regeneration | API / Backend (`app/services/sessions.py` already shipped) | — | Trust boundary — fixation defense lives in server |
| Cookie signing | API / Backend (`app/signing.py` already shipped) | Browser (cookie storage) | Server signs; browser stores opaque value |
| CSRF token validation | API / Backend (`app/csrf.py` via `starlette-csrf` middleware) | Browser (cookie echo) | Double-submit pattern — server compares, browser echoes |
| Setup / login HTML form rendering | Frontend Server (Jinja2 + FastAPI templates) | — | SSR with autoescape; no client-side templating |
| `require_admin` gate | API / Backend (`app/dependencies/auth.py`) | — | Authorization — never trust client |
| Sign-in-as footer | Frontend Server (Jinja2 conditional render in `pages/index.html`) | — | Server-rendered from `request.state.user` |

No client-side tier work in Phase 2 except a small JS shim if option (a) is chosen for the CSRF gotcha (see §1 below).

## Library / API Findings

### argon2-cffi 25.1 (PasswordHasher)

[VERIFIED: argon2-cffi.readthedocs.io/en/stable/api.html]

**Constructor signature and defaults:**

```python
PasswordHasher(
    time_cost: int = 3,           # iterations
    memory_cost: int = 65536,     # KiB → 64 MiB
    parallelism: int = 4,         # threads
    hash_len: int = 32,           # bytes of derived key
    salt_len: int = 16,           # bytes of salt
    encoding: str = "utf-8",      # password encoding
    type: Type = Type.ID,         # Argon2id (correct variant)
)
```

**The defaults already match the ROADMAP-locked parameters** (`time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID`). However, the canonical pattern is to instantiate with the kwargs *explicit* so a future ops change touches the code, not the library default. [CITED: argon2-cffi/api.html]

**Methods used in Phase 2:**

| Method | Behavior | Raises |
|--------|----------|--------|
| `hash(password)` | Returns encoded hash (Modular Crypt Format, `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`). Hash strings are ~95–110 chars in practice. The `users.password_hash` column is already `TEXT` — no column-width constraint to worry about. | `HashingError` |
| `verify(hash, password)` | Returns `True` on match. | `VerifyMismatchError` (wrong password), `VerificationError` (other failure), `InvalidHashError` (malformed hash) |
| `check_needs_rehash(hash)` | Returns bool — true when stored hash was produced with old params. Useful for **Phase 9** (rehash on login if params have moved); Phase 2 doesn't need it but the helper module should expose it for forward compat. | — |

**Constant-time verify on user-not-found (CRITICAL):**

argon2-cffi **does NOT ship a `dummy_verify()` helper** (unlike passlib's `CryptContext.dummy_verify()`). [VERIFIED: argon2-cffi/faq.html shows only 3 FAQs, none about timing attacks; VERIFIED: argon2-cffi/issues/121 is open with no maintainer response.]

The community-standard pattern (used by Django, by various FastAPI tutorials) is:

```python
# app/services/auth.py
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
)

# Computed once at import time. The literal is intentionally not a real password.
# Cost: one argon2 hash at module load (~few hundred ms once per worker startup).
_DUMMY_HASH: str = _ph.hash("snobbery-dummy-for-timing-defense-not-a-real-secret")  # noqa: S106

def verify_password(stored_hash: str, candidate_password: str) -> bool:
    try:
        return _ph.verify(stored_hash, candidate_password)
    except (VerifyMismatchError, InvalidHashError):
        return False

def dummy_verify(candidate_password: str) -> None:
    """Run argon2 verify against a known-bad hash so user-not-found
    branches consume the same wall-clock time as wrong-password.
    Result is intentionally discarded — VerifyMismatchError is the
    only outcome.
    """
    try:
        _ph.verify(_DUMMY_HASH, candidate_password)
    except VerifyMismatchError:
        pass  # Expected — defense is the timing, not the result.

def hash_password(plaintext: str) -> str:
    return _ph.hash(plaintext)
```

The Phase 1 D-15 logging policy assumes this exact pattern: `user_not_found` branch calls `dummy_verify(form.password)` BEFORE rendering the generic D-07 error.

### starlette-csrf 3.0 (CSRFMiddleware) — CRITICAL GOTCHA

[VERIFIED: github.com/frankie567/starlette-csrf source — `_get_submitted_csrf_token` is one line]

**The library reads the CSRF token ONLY from request headers.** The middleware never inspects form bodies. The full implementation of token extraction is:

```python
# starlette_csrf/middleware.py
async def _get_submitted_csrf_token(self, request: Request) -> Optional[str]:
    return request.headers.get(self.header_name)
```

**This contradicts CONTEXT D-05's assumption** that "`starlette-csrf` 3.0 reads it from either header or form field on POSTs."

**Implication:** A classic HTML form POST with `<input type="hidden" name="X-CSRF-Token" value="...">` will be silently rejected with 403 because:
1. The hidden input goes into the URL-encoded body, not headers.
2. The middleware checks headers, finds nothing, fails CSRF.

**Three options for Plan-phase to choose:**

| Option | Effort | Tradeoffs |
|--------|--------|-----------|
| **(a) JS shim on `<form>` submit** — vanilla JS event listener that reads `csrftoken` cookie and sets `X-CSRF-Token` header on the request | ~10 LOC | Keeps stack pristine; requires JS (breaks if JS off); needs CSP nonce on the inline `<script>` or extract to `/static/js/`. Cleanest path. |
| **(b) Sub-class `CSRFMiddleware`** and override `_get_submitted_csrf_token` to fall back to `request.form()` for `application/x-www-form-urlencoded` POSTs | ~20 LOC | Works without JS; downside: `await request.form()` consumes the body — subsequent code in the route must use FastAPI's form handling (which it will anyway). Risk of subtle issues with multipart. |
| **(c) Use HTMX for auth forms** — `hx-post="/login"` instead of `<form method="post">` | Minor template change | `htmx-listeners.js` already sets `X-CSRF-Token` from the cookie on every request. **Zero new code.** Downside: violates D-05's "no HTMX on auth surfaces" choice. |

**Research recommendation:** **option (a)** unless the planner prefers (c). Vanilla JS shim is 10 lines, lives in `/static/js/csrf-form-submit.js`, is loaded with a CSP nonce, and lets the auth surfaces work even with JS off if the user has the cookie pre-set (rare; the cookie is set on first GET). Note: starlette-csrf sets the `csrftoken` cookie on the GET response, so by the time the form POSTs, the cookie is already there.

**Code sketch for option (a):**

```js
// app/static/js/csrf-form-submit.js
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (form.method.toUpperCase() !== "POST") return;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  if (!match) return;
  // Inject a hidden input the server doesn't read for CSRF, but we ALSO
  // add the header via fetch — see below. Forms submitted natively can't
  // set request headers, so we intercept and submit via fetch.
  event.preventDefault();
  const token = decodeURIComponent(match[1]);
  fetch(form.action, {
    method: "POST",
    headers: { "X-CSRF-Token": token },
    body: new FormData(form),
    credentials: "same-origin",
    redirect: "follow",
  }).then((resp) => {
    if (resp.redirected) window.location.href = resp.url;
    else resp.text().then(html => { document.documentElement.innerHTML = html; });
  });
});
```

This is sketch-quality — the planner will refine. The key insight is that **classic forms cannot set request headers**, so the JS shim *replaces* the native submit with a fetch().

**Alternative — option (b) sub-class sketch:**

```python
# app/middleware/csrf_with_form.py
from starlette_csrf import CSRFMiddleware
from starlette.requests import Request

class FormAwareCSRFMiddleware(CSRFMiddleware):
    async def _get_submitted_csrf_token(self, request: Request) -> str | None:
        header_token = request.headers.get(self.header_name)
        if header_token:
            return header_token
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/x-www-form-urlencoded") or \
           content_type.startswith("multipart/form-data"):
            form = await request.form()
            return form.get(self.header_name) or form.get("csrf_token")
        return None
```

Then `main.py` swaps `CSRFMiddleware` for `FormAwareCSRFMiddleware`. Lower JS dependency, slightly more invasive.

**Plan-phase MUST pick one option and amend CONTEXT D-05 wording.**

### starlette-csrf 3.0 — other kwargs Phase 2 inherits

[VERIFIED: pypi.org/project/starlette-csrf source]

Already wired in `app/csrf.py::csrf_middleware_kwargs()`:

| Kwarg | Value | Phase 2 relevance |
|-------|-------|-------------------|
| `secret` | `APP_SECRET_KEY` | Used to HMAC-sign the CSRF cookie; opaque to Phase 2 |
| `cookie_name` | `"csrftoken"` | Templates read `request.cookies.get('csrftoken')` to populate hidden input |
| `cookie_secure` | `True` | Requires HTTPS — already enforced by NGINX in deployment |
| `cookie_samesite` | `"lax"` | Compatible with form POSTs from same-origin pages |
| `header_name` | `"X-CSRF-Token"` | The expected header (and CONTEXT-named hidden-input field name) |
| `sensitive_cookies` | `{"session_id"}` | Triggers CSRF on routes when session is present. `/setup` runs WITHOUT a session cookie — does this exempt it? |
| `exempt_urls` | `[r"^/csp-report"]` | `/csp-report` only |

**`sensitive_cookies` subtlety for `/setup`:** the first-ever setup POST happens without a session cookie. Reading the source: starlette-csrf checks if **any** of `sensitive_cookies` are present; if not present and the request is a safe method or there's no session cookie, the CSRF check **may be skipped**. Plan-phase MUST verify this by reading the middleware's `__call__` flow — if `/setup` is exempt because no `session_id` cookie exists yet, the form CSRF gotcha doesn't apply to setup (only to login + logout). [ASSUMED — needs verification against source during planning.]

### SQLAlchemy 2.0 + AsyncSession + `with_for_update()`

[VERIFIED: docs.sqlalchemy.org/en/20/core/selectable.html; postgresql.org/docs/16/explicit-locking.html]

**Confirmed semantics:**

1. `select(AppSetting).where(AppSetting.key == "setup_completed").with_for_update()` translates to `SELECT ... FOR UPDATE` on Postgres.
2. The row-level lock is held until `commit()` or `rollback()` on the session — across any subsequent `execute()` (INSERT, UPDATE, additional SELECT).
3. A second concurrent transaction running the same `SELECT FOR UPDATE` blocks until the first commits, then sees the updated row (`setup_completed = "true"`) and exits the conditional.
4. psycopg 3 passes `FOR UPDATE` through to Postgres without rewriting — verified by the SQLAlchemy 2.0 dialect docs.

**Canonical pattern for AUTH-02 (setup transaction):**

```python
# app/services/setup.py
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.user import User
from app.services.auth import hash_password


async def create_first_admin(
    db: AsyncSession,
    *,
    username: str,
    email: str,
    plaintext_password: str,
) -> User | None:
    """One-transaction first-admin creation. Returns the new User on
    success, or None if `setup_completed` was already `"true"` (race lost).
    """
    # SELECT ... FOR UPDATE on the setup_completed row.
    # AsyncSession opens an implicit transaction on first execute(); the
    # lock is held across the INSERT + UPDATE + commit() below.
    stmt = (
        select(AppSetting)
        .where(AppSetting.key == "setup_completed")
        .with_for_update()
    )
    result = await db.execute(stmt)
    setting = result.scalar_one()  # Phase 0 seed row is guaranteed present.

    if setting.value == "true":
        # Race lost — another request beat us to it. Roll back the
        # implicit transaction (releases the FOR UPDATE lock) and let
        # the route render the 302→/login.
        await db.rollback()
        return None

    # Create the admin user.
    new_user = User(
        username=username,
        email=email,
        password_hash=hash_password(plaintext_password),
        is_admin=True,
        is_active=True,
    )
    db.add(new_user)

    # Flush so new_user.id is populated for the audit log; this is still
    # inside the same transaction (no commit yet).
    await db.flush()

    # Flip the setting in the SAME transaction.
    await db.execute(
        update(AppSetting)
        .where(AppSetting.key == "setup_completed")
        .values(value="true")
    )

    # Single commit — atomic across the INSERT and the UPDATE; releases
    # the FOR UPDATE lock.
    await db.commit()
    return new_user
```

**No explicit `async with db.begin():` block needed** — the existing `async_session_factory` (already wired in `app/main.py`) is `autocommit=off` by default, so the implicit transaction starts on first execute and commits/rollbacks explicitly. The `regenerate_session()` helper follows the same pattern, so consistency is already established. [VERIFIED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]

**Important nuance:** the route handler must open the AsyncSession via the same factory `SessionMiddleware` uses, then either reuse the middleware's session or open a fresh one. The cleanest path is for the route to open its own — different transaction scope, no surprise side effects. Plan-phase locks the factory injection pattern (likely a FastAPI dependency `Depends(get_async_session)` that yields from `async_session_factory()`).

### FastAPI — `RedirectResponse(status_code=303)` + Set-Cookie

[VERIFIED: fastapi.tiangolo.com/advanced/response-change-status-code/]

```python
from fastapi.responses import RedirectResponse

response = RedirectResponse(url="/", status_code=303)
response.set_cookie(
    key="session_id",
    value=signed_session_id,
    httponly=True,
    secure=True,
    samesite="lax",
    max_age=2_592_000,  # 30 days
    path="/",
)
return response
```

OR, using the pure-string cookie value builder Phase 1 already ships:

```python
response = RedirectResponse(url="/", status_code=303)
response.headers["Set-Cookie"] = build_session_cookie(signed_session_id)
return response
```

The second form uses the locked `build_session_cookie()` value contract from `app/services/sessions.py`. Recommended: use it everywhere so the cookie attributes can't drift. [VERIFIED]

**303 vs 302 semantics:** 303 forces the browser to follow with GET regardless of the original method, which is exactly what we want after a POST. 302 is interpreted inconsistently by old clients. [CITED: MDN HTTP/Redirections]

### FastAPI — `Depends(require_admin)` pattern

[VERIFIED: fastapi.tiangolo.com/tutorial/dependencies/]

Two equivalent forms — pick one per code review consistency:

**Form 1 — dependency as a route parameter:**

```python
# app/dependencies/auth.py
from fastapi import Depends, HTTPException, Request, status

from app.models.user import User


def require_user(request: Request) -> User:
    """Dependency: 401 if request.state.user is None, else returns User."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(request: Request) -> User:
    """Dependency: 403 unless request.state.user is an active admin."""
    user = require_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user


# Usage:
@router.get("/admin")
def admin_stub(user: User = Depends(require_admin)) -> HTMLResponse:
    return HTMLResponse(...)
```

**Form 2 — dependency on route decorator** (when the route doesn't need the User object):

```python
@router.get("/debug/proxy", dependencies=[Depends(require_admin)])
async def debug_proxy(request: Request) -> DebugProxyResponse:
    ...
```

**Recommendation for Phase 2:**
- `/admin` stub uses **Form 1** (`user: User = Depends(require_admin)`) — it doesn't need the User now but Phase 9 will, and the parameter shape is forward-compatible.
- `/debug/proxy` uses **Form 2** — the existing route doesn't need the User object; minimum-diff change.

**Spec note:** CONTEXT mentions a potential `require_active_user` for Phase 4+. Phase 2 only needs `require_user` (above) and `require_admin`. Ship both for Phase 4's convenience; the deferred list explicitly calls this out.

### itsdangerous — already wired, no new usage

[CITED: app/signing.py]

`sign_session_id(uuid) -> str` and `load_session_id(str) -> uuid | None` are already in place. Phase 2's `/login` happy path:

```python
new_session_id = await regenerate_session(db, current_session_id=None, user_id=user.id)
signed = sign_session_id(new_session_id)
response.headers["Set-Cookie"] = build_session_cookie(signed)
```

No new signer config; the existing one is bound to `APP_SECRET_KEY` with `salt="session"`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hash + verify | Custom hash via `hashlib`/`hmac` | `argon2.PasswordHasher` | Wrong choice would be a 1-year-old vulnerability waiting to happen |
| Constant-time comparison | Hand-rolled `==` or `hmac.compare_digest` | `_ph.verify()` (constant-time by design) | argon2 verify is already constant-time |
| Session signing | Custom HMAC + base64 | `app/signing.py` (already shipped, itsdangerous) | Already wired |
| Cookie attribute string | f-string `Set-Cookie:` header | `app/services/sessions.py::build_session_cookie()` (already shipped) | Centralized; attribute drift impossible |
| CSRF token validation | DIY double-submit | `starlette-csrf` (already wired) | Modulo the form-field gotcha — already in stack |
| Session-row CRUD | Inline SQL | `app/services/sessions.py` helpers (already shipped) | Already wired |
| Rate limiting on `/login` `/setup` | DIY in-memory counter | `slowapi` (already wired via `@limiter.limit(LOGIN_LIMIT)`) | Already wired |
| Email validation | Regex | `pydantic.EmailStr` | One import, RFC-aware |
| First-admin race protection | Application-level lock | Postgres `SELECT FOR UPDATE` | Single source of truth; works across workers (defensive even though we're single-worker today) |
| Constant-time user-not-found defense | `time.sleep(...)` with random jitter | Precomputed dummy hash + `ph.verify(DUMMY, password)` | Real cost; impossible to detect timing difference |

**Key insight:** Phase 2 is mostly composition of locked Phase 1 helpers behind real route bodies. The ONLY genuinely new code is `app/services/auth.py` (argon2 wrapper + dummy hash), `app/services/setup.py` (the FOR UPDATE transaction), `app/dependencies/auth.py` (the gate dependencies), and the two new templates + a CSRF shim. Everything else is wiring.

## Common Pitfalls

### Pitfall 1: starlette-csrf 3.0 silently rejects form-field-only CSRF tokens

**What goes wrong:** A `<form method="post">` with `<input type="hidden" name="X-CSRF-Token">` returns 403 because the middleware reads only headers.
**Why it happens:** `_get_submitted_csrf_token` is `return request.headers.get(self.header_name)` — full stop.
**How to avoid:** Pick one of the three options above (JS shim, sub-class, or HTMX).
**Warning signs:** First manual `/login` smoke test returns 403; no log noise from `starlette-csrf` (the library doesn't log misses).

### Pitfall 2: argon2 dummy hash NOT computed at import time → timing leak

**What goes wrong:** `dummy_verify()` computes a fresh hash on every call instead of verifying a precomputed one — the work is symmetric to `hash()` not to `verify()`, so the timing differs by ~10%.
**Why it happens:** Misreading the pattern as "call `ph.hash()` for symmetry" rather than "call `ph.verify()` against a known-bad hash."
**How to avoid:** Module-level `_DUMMY_HASH = _ph.hash(...)` constant computed once at import; `dummy_verify()` calls `_ph.verify(_DUMMY_HASH, password)`.
**Warning signs:** Wave 0 test asserts `dummy_verify()` and `verify_password(real_hash, wrong_password)` are within ~5% on wall-clock time.

### Pitfall 3: SessionMiddleware User lookup query uses sync session

**What goes wrong:** Phase 2 adds a `SELECT users.* WHERE id = :session.user_id` inside `SessionMiddleware`, but the middleware's session factory is async (`async_session_factory` per `app/main.py`). Reaching for `app.db.SessionLocal` (sync) inside an async middleware would block the event loop.
**Why it happens:** Habit — `app.db.SessionLocal` is the more familiar import.
**How to avoid:** Use the existing async session opened by middleware: `result = await db.execute(select(User).where(User.id == session_row.user_id))` — the same `db` already in scope for `get_session_by_id(db, session_id)`.
**Warning signs:** Performance regression on every authenticated request; SQLAlchemy warning "AsyncSession was reused".

### Pitfall 4: Auto-login on `/setup` forgets the CSRF cookie

**What goes wrong:** After `POST /setup` redirects to `/` with a fresh `session_id` cookie, the first GET to `/` MIGHT not yet have a `csrftoken` cookie if the user hit `/setup` directly without a prior GET. The Phase 0 placeholder `/` happens to not need CSRF, but any later phase's `/` will. Worst case: the post-setup user lands on a page where their first form POST 403s because `csrftoken` cookie was never set.
**Why it happens:** `starlette-csrf` sets the cookie on the response, not the request — and POSTs don't get cookies set on them unless the response sets them.
**How to avoid:** Verify that `starlette-csrf` sets the cookie on the 303 redirect response too (it should — middleware wraps every response). If not, the planner adds a manual `response.headers.append("Set-Cookie", ...)` for the csrftoken alongside the session_id cookie.
**Warning signs:** First HTMX action after fresh setup returns 403. [VERIFIED: starlette-csrf middleware sets cookie on every response that doesn't already have it — but this should be smoke-tested in plan-phase.]

### Pitfall 5: `regenerate_session` race during simultaneous logins

**What goes wrong:** User clicks "Login" twice rapidly. Two concurrent POSTs both call `regenerate_session(None, user.id)`. Each inserts a new session row; the first cookie's session row gets clobbered by the second. The browser receives both Set-Cookies; the second one wins. Behavior: one row exists, user is logged in via the second's cookie. The first cookie is now orphaned.
**Why it happens:** No atomic "set or replace by user_id" semantics in the helper — each call is "delete current, insert new" but `current_session_id` for a fresh login is `None`, so no delete runs.
**How to avoid:** Acceptable behavior. The orphaned cookie's session row exists for 30 days max; if it's used (different browser), it grants legitimate auth to the same user (worst case: an extra session row, not a security hole). slowapi LOGIN_LIMIT=5/15min caps the abuse vector. **No action needed.** Documented for plan-phase awareness.
**Warning signs:** `sessions` table grows faster than expected — but the Phase 8 sweep job cleans it.

### Pitfall 6: `is_active=false` mid-session — the User lookup runs but the row is stale

**What goes wrong:** Admin deactivates user mid-session. SessionMiddleware loads the User row (with `is_active=false`), correctly clears the cookie + deletes the session per D-10. But: ORM identity-map caching might serve a stale `is_active=true` row if the AsyncSession was kept alive across requests.
**Why it happens:** `async_session_factory` is configured with `expire_on_commit=False`, which retains ORM state across commits within one session. But each middleware request opens a FRESH session via `async with self.session_factory() as db:` — so the identity map starts empty. No staleness possible.
**How to avoid:** Verified safe; document in plan-phase the assertion test ("set is_active=false in background; next request → cookie cleared, session row deleted").
**Warning signs:** N/A — confirmed safe by reading `app/main.py` and `app/middleware/session.py`.

### Pitfall 7: argon2-cffi released the GIL during hash/verify — but blocks the event loop in async handlers

**What goes wrong:** `verify_password()` is sync (argon2 hash/verify are CPU-bound). Calling it from an `async def login(...)` handler blocks the event loop for ~100ms (the time argon2id takes at these params).
**Why it happens:** Async handlers calling sync CPU-bound code = event loop stall. Only matters at very high concurrency. At household scale: irrelevant.
**How to avoid:** Acceptable at household scale. If a security audit pushes back, wrap in `asyncio.to_thread(verify_password, ...)`. **Note:** argon2-cffi DOES release the GIL during the C call ([CITED: argon2-cffi/faq.html FAQ #3]), so other Python threads can run; but only the asyncio event loop's single thread blocks. `asyncio.to_thread` would defer to the threadpool.
**Warning signs:** N/A at household scale.

## Code Examples

### Pattern 1: `/login` happy + sad paths

```python
# app/routers/auth.py — REPLACES the Phase 1 stubs in place

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_async_session  # NEW — plan-phase locks shape
from app.events import (
    ADMIN_USER_CREATED,
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCEEDED,
    AUTH_LOGOUT,
)
from app.models.user import User
from app.rate_limit import LOGIN_LIMIT, SETUP_LIMIT, limiter
from app.services.auth import dummy_verify, verify_password
from app.services.sessions import (
    build_session_clear_cookie,
    build_session_cookie,
    delete_session,
    regenerate_session,
)
from app.services.setup import create_first_admin
from app.signing import sign_session_id
from app.templates_setup import templates

log = structlog.get_logger()
router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> Response:
    return templates.TemplateResponse(
        request=request, name="pages/login.html", context={"error": None, "username": ""}
    )


@router.post("/login", response_class=HTMLResponse)
@limiter.limit(LOGIN_LIMIT)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    ip = request.client.host if request.client else "unknown"
    request_id = getattr(request.state, "request_id", "unknown")

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        # Constant-time defense per Phase 1 D-15
        dummy_verify(password)
        log.info(AUTH_LOGIN_FAILED, ip=ip, request_id=request_id, reason="user_not_found")
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={"error": "Invalid username or password.", "username": username},
            status_code=200,  # D-07: 200 (not 401) so the form re-renders
        )

    if not user.is_active:
        # Inactive user is treated as failed login (no enumeration leak)
        dummy_verify(password)  # symmetry
        log.info(
            AUTH_LOGIN_FAILED,
            ip=ip, request_id=request_id, user_id=user.id, reason="inactive",
        )
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={"error": "Invalid username or password.", "username": username},
        )

    if not verify_password(user.password_hash, password):
        log.info(
            AUTH_LOGIN_FAILED,
            ip=ip, request_id=request_id, user_id=user.id, reason="bad_password",
        )
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={"error": "Invalid username or password.", "username": username},
        )

    # Happy path — regenerate session, set cookie, 303 → /
    # `request.state.session` is the prior session (likely None for a fresh login).
    prior_session = getattr(request.state, "session", None)
    prior_session_id = prior_session.session_id if prior_session else None
    new_session_id = await regenerate_session(db, prior_session_id, user.id)

    log.info(AUTH_LOGIN_SUCCEEDED, user_id=user.id, ip=ip, request_id=request_id)

    response = RedirectResponse(url="/", status_code=303)
    response.headers.append("Set-Cookie", build_session_cookie(sign_session_id(new_session_id)))
    return response


@router.post("/logout")
async def logout_submit(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    session = getattr(request.state, "session", None)
    user_id = session.user_id if session else None
    if session is not None:
        await delete_session(db, session.session_id)

    log.info(
        AUTH_LOGOUT,
        user_id=user_id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "request_id", "unknown"),
    )

    response = RedirectResponse(url="/login", status_code=303)
    response.headers.append("Set-Cookie", build_session_clear_cookie())
    return response
```

### Pattern 2: `/setup` with race protection + auto-login

```python
@router.get("/setup", response_class=HTMLResponse)
async def setup_form(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    # Direct read (Phase 3 typed reader lands later — discretion item)
    from sqlalchemy import text
    row = await db.execute(
        text("SELECT value FROM app_settings WHERE key = 'setup_completed'")
    )
    if row.scalar() == "true":
        return RedirectResponse(url="/login", status_code=303)  # D-01: 302 → /login

    return templates.TemplateResponse(
        request=request, name="pages/setup.html", context={"error": None}
    )


@router.post("/setup", response_class=HTMLResponse)
@limiter.limit(SETUP_LIMIT)
async def setup_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    # Pydantic schema with username regex + EmailStr + min-12-char password
    # — wraps these Form(...) values for validation. Plan-phase locks the
    # schema; rendering errors back to the template is uniform across
    # /setup and /login.

    new_user = await create_first_admin(
        db,
        username=username,
        email=email,
        plaintext_password=password,
    )
    if new_user is None:
        # Race lost — already completed by another concurrent request.
        return RedirectResponse(url="/login", status_code=303)

    log.info(
        ADMIN_USER_CREATED,
        user_id=new_user.id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "request_id", "unknown"),
    )

    # D-03: auto-login on successful setup.
    new_session_id = await regenerate_session(db, None, new_user.id)
    response = RedirectResponse(url="/", status_code=303)
    response.headers.append("Set-Cookie", build_session_cookie(sign_session_id(new_session_id)))
    return response
```

### Pattern 3: `SessionMiddleware` upgrade (D-09 / D-10)

```python
# app/middleware/session.py — REPLACES lines 177–191 of the existing file

# ... (everything up to the `else` branch where session_row exists is unchanged)
else:
    # Phase 2: load the FULL User row and apply D-10 (deactivated → no session).
    from app.models.user import User  # local import keeps Phase 1 import graph
    user_result = await db.execute(
        select(User).where(User.id == session_row.user_id)
    )
    user_row = user_result.scalar_one_or_none()

    if user_row is None or not user_row.is_active:
        # D-10: deactivated/deleted user → fail-closed.
        await delete_session(db, session_id)
        clear_cookie = True
        scope["state"]["user"] = None
        scope["state"]["session"] = None
    else:
        scope["state"]["session"] = session_row
        scope["state"]["user"] = user_row  # SHAPE CHANGE: dict → User row

        # Write-throttled sliding refresh (T-04-06 mitigation; unchanged).
        elapsed = (datetime.now(UTC) - session_row.last_seen).total_seconds()
        if elapsed > self.refresh_threshold_seconds:
            await refresh_last_seen(db, session_id)
```

### Pattern 4: `require_admin` + the one-line debug-route wrap

```python
# app/dependencies/auth.py (NEW MODULE)
from __future__ import annotations

from fastapi import HTTPException, Request, status
from app.models.user import User


def require_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user


def require_admin(request: Request) -> User:
    user = require_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user
```

```python
# app/routers/debug.py — one-line addition to existing route
from fastapi import APIRouter, Depends, Request
from app.dependencies.auth import require_admin

router = APIRouter()

@router.get("/debug/proxy", response_model=DebugProxyResponse,
            dependencies=[Depends(require_admin)])  # NEW: admin gate
async def debug_proxy(request: Request) -> DebugProxyResponse:
    ...  # body unchanged
```

```python
# app/routers/admin.py (NEW)
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.dependencies.auth import require_admin
from app.models.user import User
from app.templates_setup import templates

router = APIRouter()

@router.get("/admin", response_class=HTMLResponse)
async def admin_stub(
    request: Request,
    user: User = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="pages/admin_stub.html",
        context={"user": user},
    )
```

## State of the Art

| Old approach | Current approach | When changed | Impact |
|--------------|------------------|--------------|--------|
| Plain bcrypt or scrypt for password hashing | argon2id (Argon2 family winner of PHC 2015) | argon2id is OWASP top recommendation since 2021 | Phase 2 uses argon2id — already locked |
| Cookie-stored session DATA | Session ID in cookie + table-backed row | Phase 1 already adopted this | No Phase 2 work — already correct |
| Session ID kept across login | Regenerate on every privilege change | OWASP ASVS V3.2.3 | `regenerate_session()` already implemented |
| 302 redirects after POST | 303 See Other (forces GET) | Long-established | D-03 / D-05 use 303 |
| Per-request CSRF token rotation | Double-submit-cookie (token = cookie value) | Phase 1 locked this | Phase 2 inherits — modulo the form-field gotcha |
| `passlib` library | argon2-cffi directly | passlib is now in maintenance-only mode (Hynek's `argon2-cffi` is more actively maintained) | Phase 2 uses argon2-cffi directly — already pinned in requirements.txt |

**Deprecated / outdated:**
- **passlib** — still works but maintenance-only since 2020; argon2-cffi 25.1 is the active choice. Do not introduce passlib for `dummy_verify()`.
- **Starlette's stock `SessionMiddleware`** — cookie-only, no DB backing; Phase 1's custom `SessionMiddleware` replaces it. Don't accidentally re-introduce.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0 + pytest-asyncio (auto mode) + httpx 0.28 (TestClient + AsyncClient) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `docker compose exec coffee-snobbery pytest -x tests/test_phase02_auth.py` |
| Full suite command | `docker compose exec coffee-snobbery pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Cold container → GET /setup → form rendered; POST /setup → user created + 303→/ with session cookie; subsequent GET /setup → 303→/login | integration | `pytest tests/test_phase02_auth.py::test_setup_happy_path -x` | ❌ Wave 0 |
| AUTH-01 | Subsequent POST /setup → 303 → /login (no second user) | integration | `pytest tests/test_phase02_auth.py::test_setup_blocked_after_completion -x` | ❌ Wave 0 |
| AUTH-02 | TWO concurrent POST /setup against a fresh DB → exactly one user row inserted; one returns user cookie, the other 303→/login | integration (asyncio.gather) | `pytest tests/test_phase02_auth.py::test_setup_concurrent_race -x` | ❌ Wave 0 |
| AUTH-02 | SELECT FOR UPDATE held across INSERT + UPDATE in one transaction | unit (transaction inspector with `db.in_transaction()` assertion) | `pytest tests/test_phase02_setup_service.py::test_for_update_atomic -x` | ❌ Wave 0 |
| AUTH-03 | POST /login with no public registration route at /register (404) | integration | `pytest tests/test_phase02_auth.py::test_no_register_route -x` | ❌ Wave 0 |
| AUTH-03 | POST /login valid creds → 303 → / + session cookie | integration | `pytest tests/test_phase02_auth.py::test_login_happy_path -x` | ❌ Wave 0 |
| AUTH-03 | POST /login invalid creds (wrong password) → 200 + generic error | integration | `pytest tests/test_phase02_auth.py::test_login_wrong_password -x` | ❌ Wave 0 |
| AUTH-03 | POST /login invalid creds (unknown user) → 200 + generic error; argon2 dummy verify ran (wall-clock comparison) | unit | `pytest tests/test_phase02_auth_service.py::test_dummy_verify_timing -x` | ❌ Wave 0 |
| AUTH-04 | hash_password(plaintext) produces $argon2id$v=19$m=65536,t=3,p=4$... format; round-trips via verify_password | unit | `pytest tests/test_phase02_auth_service.py::test_argon2_roundtrip -x` | ❌ Wave 0 |
| AUTH-04 | PasswordHasher constructed with explicit kwargs (introspect _ph attributes) | unit | `pytest tests/test_phase02_auth_service.py::test_password_hasher_params -x` | ❌ Wave 0 |
| AUTH-06 | Session cookie response attributes (HttpOnly, Secure, SameSite=Lax, Max-Age=2592000, Path=/, signed value invertible) | integration | `pytest tests/test_phase02_auth.py::test_session_cookie_attributes -x` | ❌ Wave 0 |
| AUTH-07 | After login, the previous session row is gone and a new one exists with the same user_id; cookie value changed | integration (session-fixation defense) | `pytest tests/test_phase02_auth.py::test_session_fixation_defense -x` | ❌ Wave 0 |
| AUTH-07 | Pre-set cookie cannot inherit a new authenticated session (attacker pre-set cookie → user logs in → attacker's old cookie does not resolve to the user) | integration | `pytest tests/test_phase02_auth.py::test_preset_cookie_does_not_inherit -x` | ❌ Wave 0 |
| AUTH-07 | Logout deletes the session row and emits the clear-cookie header | integration | `pytest tests/test_phase02_auth.py::test_logout_clears_session -x` | ❌ Wave 0 |
| AUTH-09 | GET /admin as anon → 401; as non-admin user → 403; as admin → 200 with stub body | integration | `pytest tests/test_phase02_auth.py::test_admin_gate_three_states -x` | ❌ Wave 0 |
| AUTH-09 | GET /debug/proxy as anon → 401; as non-admin → 403; as admin → 200 (Phase 1 D-16 follow-through via D-14) | integration | `pytest tests/test_phase02_auth.py::test_debug_proxy_admin_only -x` | ❌ Wave 0 |
| (D-10) | SessionMiddleware: set user.is_active=false, next request clears cookie + deletes session row | integration | `pytest tests/test_phase02_session_middleware.py::test_deactivated_user_fail_closed -x` | ❌ Wave 0 |
| (D-10) | SessionMiddleware: delete user row, next request clears cookie + deletes session row | integration | `pytest tests/test_phase02_session_middleware.py::test_deleted_user_fail_closed -x` | ❌ Wave 0 |
| (D-09) | SessionMiddleware: request.state.user is User (not dict) on authenticated path | integration | `pytest tests/test_phase02_session_middleware.py::test_state_user_shape -x` | ❌ Wave 0 |
| (CSRF) | POST /login WITHOUT the CSRF cookie+header pair → 403 | integration | `pytest tests/test_phase02_auth.py::test_login_csrf_blocked -x` | ❌ Wave 0 |
| (CSRF) | POST /logout WITHOUT the CSRF cookie+header pair → 403 | integration | `pytest tests/test_phase02_auth.py::test_logout_csrf_blocked -x` | ❌ Wave 0 |
| (CSRF) | The chosen CSRF integration approach (JS shim / sub-class / HTMX) actually delivers the token to the middleware on a real submit | integration (mimic via httpx with the resolved approach) | `pytest tests/test_phase02_csrf_form_integration.py -x` | ❌ Wave 0 |
| (D-15) | auth.login_failed log line with reason="user_not_found" has NO `attempted_username` field; reason="bad_password" carries `user_id` | unit (structlog capsys fixture) | `pytest tests/test_phase02_logging.py -x` | ❌ Wave 0 |
| (D-13) | /admin stub body contains "Admin (stub) — wiring lands in Phase 9" literal | integration | `pytest tests/test_phase02_auth.py::test_admin_stub_body -x` | ❌ Wave 0 |
| (Smoke) | Cold container → /setup → /login → see / page footer with "Signed in as <username>" | integration | `pytest tests/test_phase02_smoke.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest -x tests/test_phase02_<targeted_file>.py` (~10s)
- **Per wave merge:** `pytest -x tests/test_phase02_*.py` (~60s incl. concurrent setup test)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_phase02_auth.py` — integration tests against the FastAPI TestClient
- [ ] `tests/test_phase02_auth_service.py` — `app/services/auth.py` unit tests (hash, verify, dummy_verify timing)
- [ ] `tests/test_phase02_setup_service.py` — `app/services/setup.py` unit tests (FOR UPDATE atomic, race resolution)
- [ ] `tests/test_phase02_session_middleware.py` — D-09 / D-10 fail-closed branches
- [ ] `tests/test_phase02_csrf_form_integration.py` — proves the chosen CSRF approach works
- [ ] `tests/test_phase02_logging.py` — D-15 logging policy (no `attempted_username` on user_not_found branch)
- [ ] `tests/test_phase02_smoke.py` — happy path cold-container → setup → login → home
- [ ] `tests/conftest.py` — likely needs a fresh-db fixture per test (or transactional-rollback fixture) so the AUTH-02 race test starts with `setup_completed = "false"` and zero users; plus an `async_client` httpx AsyncClient fixture for the concurrent-race test
- [ ] Test dep: `pytest-asyncio` already pinned; `respx` not needed for Phase 2

## Open Questions for Planner (RESOLVED)

1. **CSRF form-field strategy** — pick one of options (a), (b), (c) above. CONTEXT D-05 wording needs amendment regardless.
2. **Does starlette-csrf exempt the very first `/setup` POST when no `session_id` cookie exists?** Read the middleware's `__call__` flow during plan-phase to confirm. If exempt, the CSRF gotcha applies only to `/login` and `/logout` (still needs fixing but the fix can defer the very-first-setup edge case).
3. **Async session injection for routes** — the cleanest pattern is a `get_async_session()` dependency in `app/dependencies/db.py` that yields from the existing `async_session_factory`. The factory currently lives at module-level in `app/main.py`. Plan-phase decides whether to move the factory to `app/db.py` (cleaner) or import it from `app.main` (less ideal).
4. **Pydantic Form schema for `/setup` and `/login`** — FastAPI doesn't (yet) auto-bind a Pydantic model to `Form(...)` parameters as cleanly as for JSON bodies. Plan-phase picks: (i) individual `username: str = Form(...)` params + manual validation, or (ii) `pydantic.BaseModel` with `Annotated[SetupForm, Form()]` (FastAPI 0.115+ supports this). Both work; (ii) is cleaner for the planner-stated 12-char minimum + EmailStr.
5. **`POST /setup` after `setup_completed=true`** — CONTEXT D-01 says 302 → /login. But: the route is rate-limited and the `create_first_admin` service correctly returns None on race. Confirm the planned implementation returns the redirect BEFORE running any DB work (so an attacker can't exhaust slowapi by spamming POSTs to a finished setup endpoint). Suggest: an explicit guard `await db.execute(text("SELECT value..."))` in the handler before calling the service (cheap read; bypasses argon2 cost).
6. **`SessionMiddleware` cyclic import risk** — adding `from app.models.user import User` inside the middleware introduces an import chain `middleware → models.user → models.base`. Existing middleware imports `app.models.session` indirectly via `app.services.sessions`. Risk is low; plan-phase confirms via `from app.models.user import User` at module top (not function-local) compiles cleanly.
7. **The CSRF cookie on the post-setup 303** — does starlette-csrf set the `csrftoken` cookie on the redirect response? It should (middleware wraps all responses) but plan-phase verifies via a smoke test so the freshly-logged-in user doesn't 403 on their first form interaction.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | runtime | ✓ (via Dockerfile) | 3.12 | — |
| argon2-cffi | password hashing | ✓ (already in requirements.txt) | >=25.1,<26 | — |
| starlette-csrf | CSRF middleware | ✓ (already wired) | >=3.0,<4 | — |
| SQLAlchemy 2.0 + AsyncSession | DB session for FOR UPDATE | ✓ (already wired) | >=2.0.49,<2.1 | — |
| psycopg 3 | Postgres driver | ✓ (already wired) | >=3.3,<3.4 | — |
| PostgreSQL 16 | row-locking semantics | ✓ (postgres:16-alpine) | 16 | — |
| pytest-asyncio | concurrent-race test | ✓ (already in requirements-dev.txt) | latest | — |
| itsdangerous | session cookie signing | ✓ (already wired) | >=2.2,<3.0 | — |

No missing dependencies. No fallback strategies needed.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | argon2id (V2.4.1) via argon2-cffi PasswordHasher; min-12-char password (V2.1.1 — meets the 12-char floor for non-MFA accounts in ASVS L1) |
| V3 Session Management | yes | UUID session ID via uuid4 (V3.2.1), HttpOnly/Secure/SameSite cookie (V3.4.x), session-ID regeneration on every privilege change (V3.2.3), 30-day max + sliding refresh (V3.3.1) |
| V4 Access Control | yes | `require_admin` dependency at API tier (V4.1.1, V4.1.3); no client-side enforcement (V4.1.5); `/admin` denies-by-default (V4.1.2) |
| V5 Input Validation | yes | Pydantic v2 schemas for /setup + /login form fields (V5.1.3) — username regex, EmailStr, password min-length |
| V6 Cryptography | yes | argon2-cffi (V6.2.3 — approved KDF); itsdangerous HMAC for cookie integrity (V6.2.2); never hand-roll (V6.2.1) |
| V7 Error & Logging | yes | D-15 logging policy: no passwords logged, no session tokens logged; generic D-07 error message (V7.4.3 — no info-leakage); structured `auth.login_failed` events (V7.1.3) |
| V14 Configuration | yes | Failed-login rate limit 5/15min via slowapi (V14.4.3 — anti-automation) |

### Known Threat Patterns for FastAPI + argon2 + cookies

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| User-enumeration via login response timing | Information Disclosure | argon2 dummy_verify() on user-not-found branch (§Library findings) |
| Session fixation | Tampering / Spoofing | `regenerate_session()` on every login/logout/admin-toggle (already shipped) |
| Cookie theft via XSS | Information Disclosure | HttpOnly cookie attribute (already in `build_session_cookie()`); CSP nonce strict from Phase 1 D-02 |
| CSRF on `/login` / `/logout` / `/setup` | Tampering | starlette-csrf double-submit middleware (Phase 1 wired); **but see Pitfall 1 — form-field token issue** |
| First-admin race (two requests both become admin) | Elevation of Privilege | `SELECT FOR UPDATE` on `app_settings.setup_completed` (this phase) |
| Brute-force on `/login` | Anti-automation gap | slowapi `LOGIN_LIMIT = "5/15minutes"` (Phase 1 wired) |
| Pre-auth cookie pinning (attacker pre-sets session_id cookie, then victim logs in and inherits attacker's session) | Spoofing | `regenerate_session()` mints a fresh UUID on login — attacker's pre-set ID is overwritten in the response (already shipped) |
| Deactivated-user holds live session | Elevation of Privilege (residual) | D-10: SessionMiddleware loads User row, fails closed on `is_active=false` (this phase) |
| Argon2 parameters too low | Tampering (offline crack of dumped hashes) | Locked params: `memory_cost=65536, time_cost=3, parallelism=4` — match OWASP 2023+ guidance |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | starlette-csrf 3.0 exempts CSRF check on first /setup POST because no `session_id` cookie exists | Pitfall 4, Open Q2 | If wrong, first-ever setup form POST returns 403 — but the CSRF gotcha resolution (option a/b/c) already addresses this; impact: minor — fix lands in the same task |
| A2 | Adding `from app.models.user import User` at module top of `app/middleware/session.py` does not introduce a cyclic import | Open Q6 | If wrong, ImportError at app start. Easy to detect at first test run; trivial fix (function-local import) |
| A3 | `pytest-asyncio` is already wired in requirements-dev.txt and conftest supports `asyncio.gather` for the AUTH-02 race test | Validation Arch / Wave 0 | If wrong, the concurrent-setup race test cannot run automated; plan-phase adds dep or uses threading | 
| A4 | starlette-csrf sets the `csrftoken` cookie on the 303 redirect response after a successful POST /setup (so the newly-logged-in user has the cookie for their next form interaction) | Pitfall 4, Open Q7 | If wrong, first form interaction after auto-login returns 403; smoke test catches it; minor template / response-cookie fix |
| A5 | The existing `async_session_factory` in `app/main.py` can be imported by route modules via `from app.main import async_session_factory` OR can be moved cleanly to `app/db.py` | Open Q3 | If wrong (e.g., circular import via `app.main`), the planner moves the factory to `app/db.py` — refactor; not blocking |
| A6 | argon2-cffi 25.1's `PasswordHasher()` with default kwargs produces hashes identical (param-wise) to explicitly-passed `time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID` | §argon2-cffi findings | If wrong, hash strings differ in the `$m=...$t=...$p=...` segment — caught by Wave 0 `test_password_hasher_params`. Mitigation already locked: pass kwargs explicitly. |

## Sources

### Primary (HIGH confidence)
- [argon2-cffi 25.1 API Reference](https://argon2-cffi.readthedocs.io/en/stable/api.html) — PasswordHasher constructor, defaults, exception types
- [argon2-cffi FAQ](https://argon2-cffi.readthedocs.io/en/stable/faq.html) — confirms no built-in dummy_verify; GIL release during hash/verify
- [argon2-cffi GitHub issue #121](https://github.com/hynek/argon2-cffi/issues/121) — confirms community-pattern dummy-hash defense is not officially documented but is expected
- [starlette-csrf middleware source (`_get_submitted_csrf_token`)](https://github.com/frankie567/starlette-csrf/blob/main/starlette_csrf/middleware.py) — confirms header-only token lookup
- [starlette-csrf 3.0 PyPI page](https://pypi.org/project/starlette-csrf/) — full kwargs list and defaults
- [SQLAlchemy 2.0 Select.with_for_update](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.with_for_update) — locking semantics; commit/rollback release
- [SQLAlchemy 2.0 asyncio ORM extensions](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — AsyncSession transaction patterns
- [PostgreSQL 16 Explicit Locking](https://www.postgresql.org/docs/16/explicit-locking.html) — FOR UPDATE row-level lock semantics; concurrent SELECT FOR UPDATE behavior
- [FastAPI Response Status Code](https://fastapi.tiangolo.com/advanced/response-change-status-code/) — RedirectResponse(303) + Set-Cookie pattern
- [FastAPI Dependencies tutorial](https://fastapi.tiangolo.com/tutorial/dependencies/) — Depends() parameter vs decorator forms
- [passlib CryptContext.dummy_verify](https://passlib.readthedocs.io/en/stable/lib/passlib.context.html) — reference idiom that argon2-cffi expects you to replicate manually

### Secondary (MEDIUM confidence)
- WebSearch on "argon2-cffi dummy hash verify user not found timing attack pattern Python" — confirms community pattern; flagged because no single authoritative source documents it

### Tertiary (LOW confidence)
- None — every claim in this research has at least one HIGH or MEDIUM source

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library already pinned in `requirements.txt`; versions verified
- Architecture: HIGH — composition of Phase 1 helpers; only `app/services/auth.py`, `app/services/setup.py`, `app/dependencies/auth.py`, and templates are new
- Pitfalls: HIGH on the CSRF form-field issue (read the source); HIGH on argon2 dummy-hash idiom (community consensus); MEDIUM on the post-setup CSRF cookie behavior (needs plan-phase smoke test)

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (30 days — stable libraries; the CSRF gotcha is unlikely to change in the 3.x line)

## RESEARCH COMPLETE
