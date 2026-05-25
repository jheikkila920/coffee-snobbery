# Phase 2: Auth - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the Phase 1 stub auth surfaces with real first-admin setup, argon2id login, session-ID regeneration on every privilege change, and an `is_admin`-gated `/admin` stub. Also: lift `SessionMiddleware`'s `request.state.user` from the Phase 1 stub `{"user_id": int}` to a real `User` row, and wrap the public `/debug/proxy` route behind the admin gate (per Phase 1 D-16).

In scope:
- `POST /setup` (real body) — first-admin creation under `SELECT … FOR UPDATE` on the seeded `app_settings.setup_completed` row (AUTH-02). On success: insert user, flip `setup_completed=true` in the same transaction, mint a session, set the signed cookie, 302 → `/`.
- `GET /setup` — renders the form when `setup_completed=false`; 302 → `/login` when true.
- `POST /setup` (after first admin) — 302 → `/login` (consistent with `GET /setup` behavior).
- `GET /login` — renders the form (always reachable).
- `POST /login` — argon2id verify, atomic session-ID regen, 302 → `/` on success; re-render form with a single generic error on failure.
- `POST /logout` — CSRF-protected form action; deletes the current session row, clears the cookie, 302 → `/login`.
- `GET /admin` — `is_admin` gate; returns 200 with literal "Admin (stub) — wiring lands in Phase 9" or 403 otherwise.
- `SessionMiddleware` real-user upgrade — replace `{"user_id": int}` stub with a full `User` row lookup; treat `is_active=false` or missing-user identically to expired/missing-session (clear cookie + delete row).
- `/debug/proxy` admin-gate wrap (Phase 1 D-16 follow-through).
- Templates: `pages/setup.html` and `pages/login.html` extending `base.html`, both with the CSRF `<input type=hidden>` populated from `request.cookies.get('csrftoken')` per the Phase 1 double-submit pattern.
- argon2-cffi dependency add to `pyproject.toml` with the parameters locked by ROADMAP (`memory_cost=65536, time_cost=3, parallelism=4`).
- Wire the existing `app/events.py` constants (`AUTH_LOGIN_SUCCEEDED`, `AUTH_LOGIN_FAILED`, `AUTH_LOGOUT`, `ADMIN_USER_CREATED`) into the real routes per the Phase 1 D-15 logging policy.

Out of scope (belongs in later phases):
- Admin user-management CRUD (list / create / edit / reset password / toggle admin / deactivate / delete) — Phase 9 (ADMIN-01).
- API-credentials surface — Phase 9 (ADMIN-02).
- `app_settings` editor UI — Phase 9 (ADMIN-03).
- Password reset / recovery flow — not in v1 scope.
- "Sign out everywhere" UX — deferred per Phase 1 D-09.
- Email verification / SMTP plumbing — explicit out-of-scope (PROJECT.md).
- Periodic expired-session sweep job — Phase 8 (per `app/services/sessions.py` TODO note).
- OAuth / SSO / magic links — explicit out-of-scope (PROJECT.md).

7 requirements mapped: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-06, AUTH-07, AUTH-09.

</domain>

<decisions>
## Implementation Decisions

### Setup flow

- **D-01: Post-setup behavior — 302 → `/login`.** After `setup_completed=true`, both `GET /setup` and `POST /setup` respond `302 Location: /login`. Resolves the ROADMAP internal conflict (goal sentence said "redirects to `/login`", success criterion #1 said "404s") in favor of the friendlier path. Security cost is nil — the route is read-only post-setup and leaks no information. Update ROADMAP success criterion #1 wording during plan-phase to match.
- **D-02: `/setup` form fields — username + password + REQUIRED email.** The user opted to require email at first-admin setup even though `users.email` is schema-nullable. Rationale: future recovery / notification features have a guaranteed value to work with for at least one user. Phase 9 admin user-create is a separate decision (likely keep email optional there to match the schema).
- **D-03: Auto-login on successful setup.** `POST /setup` happy path: INSERT user → flip `setup_completed=true` (same TX as the user insert) → `regenerate_session(None, new_user_id)` → set signed cookie → `303 See Other` to `/`. One step instead of `/setup` → `/login` → re-type credentials. ROADMAP success criterion #5 ("setup → login → see /") is amended at plan-phase to reflect the auto-login flow.
- **D-04: Setup completion flip is in the SAME transaction as the user INSERT.** The `SELECT … FOR UPDATE` on the `setup_completed` row is held across both the INSERT into `users` AND the UPDATE of `app_settings.setup_completed` from `"false"` to `"true"`. Commit happens once. Race protection only matters if the swap is atomic; AUTH-02 requires this implicitly. Plan-phase locks the SQL.

### Login flow

- **D-05: Form style — classic HTML POST → 303 See Other.** `<form method="post" action="/login">` (no HTMX on auth surfaces). Server sets `Set-Cookie` on the 303 response and the browser follows to `/`. Works without JS, works under the strict CSP, well-known browser behavior. `/login` and `/setup` are infrequent enough that consistency-with-HTMX doesn't earn its keep. The CSRF token is included as a hidden `<input name="X-CSRF-Token">` populated from `request.cookies.get('csrftoken')`.
  > **AMENDED 2026-05-17 (plan-phase research).** Original wording said "`starlette-csrf` 3.0 reads it from either header or form field on POSTs." That is **incorrect** — source-verified: `starlette-csrf` 3.0's `_get_submitted_csrf_token` reads only `request.headers.get(self.header_name)`. See D-15 for the resolution (`CSRFFormFieldShim` ASGI middleware mounted outside `CSRFMiddleware` that hoists the form field into the header). The hidden-input + works-without-JS property of D-05 is preserved by D-15; no template change vs. the original D-05 intent.
- **D-06: Post-login destination — always `/`.** No `?next=` parameter honoring. `/` is the home page (Phase 0 placeholder now, Phase 6 fills it). Removes the open-redirect attack surface entirely. Phase 4+ "guarded" routes simply 302 anonymous users to `/login` with no return-path memory; they'll land at `/` after auth and can navigate from there. Revisit only if a Phase 4+ flow proves the friction is real.
- **D-07: Failed-login UX — single generic message + re-render.** "Invalid username or password." rendered above the form with a 200 (not 401 — 200 lets the form re-render cleanly). Same message regardless of "user not found" vs "wrong password", aligned with the Phase 1 D-15 constant-time argon2-verify-on-no-match policy. No "your username doesn't exist" leakage. Form re-renders with the username field repopulated (helps real users; the constant-time backend means no enumeration signal).
- **D-08: Rate-limit 429 response.** Inherit the slowapi handler from Phase 1 D-17 — returns the canonical JSON 429. For the form-POST flow specifically, plan-phase decides whether to override the 429 handler to re-render the login template with a "Too many attempts — try again in N minutes" banner. Default: leave the JSON handler in place; users hitting 5/15min during a real attack don't need polish.

### Session middleware upgrade

- **D-09: Load FULL `User` row on every authenticated request.** SessionMiddleware swaps the Phase 1 `{"user_id": int}` stub for a `SELECT users.* WHERE id = :session.user_id` lookup. ~9 columns, indexed PK, sub-millisecond at household scale. Sets `scope["state"]["user"] = User` (the SQLAlchemy model instance) so templates and routers can read `user.username`, `user.is_admin`, `user.email` directly without a second query. Same async DB session the middleware already opens for `get_session_by_id` — no extra round-trip beyond the one extra SELECT.
- **D-10: Deactivated / deleted user → treat as no session.** If the `User` lookup returns None (deleted) OR returns a row with `is_active=false`, SessionMiddleware:
  1. Calls `delete_session(db, session_id)` to remove the orphaned session row.
  2. Sets `clear_cookie = True` so the `send_wrapper` emits the clear-cookie header.
  3. Sets `scope["state"]["user"] = None` and `scope["state"]["session"] = None`.
  This is the same fail-closed path the middleware already uses for expired/missing sessions. Deactivating a user via Phase 9 immediately logs them out on their next request — no waiting for the 30-day cookie expiry. Consistent semantics across all "this session is no longer valid" branches.
- **D-11: Stub-to-real upgrade is a SessionMiddleware-internal change, not a new middleware.** The single `User` lookup happens inside the existing `async with self.session_factory()` block that's already open for `get_session_by_id`. No middleware-order change; no new ASGI layer; the public contract of `request.state.user` shifts from "dict-or-None" to "User-or-None" and downstream routes consume the new shape. Plan-phase double-checks the one Phase 1 caller (`/debug/whoami` if it landed) and updates it.

### Logout + admin gate

- **D-12: `/logout` is POST-only with CSRF.** `<form method="post" action="/logout">` rendered in the nav (or wherever the sign-out link sits) with the CSRF hidden input. Aligns with the SEC-01 invariant (every state-changing form is CSRF-protected) and blocks drive-by logout via `<img src="/logout">`. Mild UX cost — a one-button form instead of an `<a>` — accepted.
- **D-13: `/admin` Phase-2 stub is one route, one line.** `GET /admin` returns 200 with the literal body `"Admin (stub) — wiring lands in Phase 9"` if `request.state.user` is non-None AND `user.is_admin`, else 403. No sub-router scaffolding; no nav skeleton — Phase 9 owns the admin shape and any scaffolding now is throwaway. Returned as a plain HTML page extending `base.html` (gives the future Phase 9 work an existing-template hook).
- **D-14: `/debug/proxy` admin-gate.** Wrap the existing `app/routers/debug.py::debug_proxy` route in the same `is_admin` dependency the `/admin` stub uses. Plan-phase introduces a shared `require_admin` FastAPI dependency in `app/dependencies/auth.py` (new module) so both routes import from one place; Phase 9 admin sub-routes pick up the same dependency.

### CSRF integration (added 2026-05-17 from plan-phase research)

- **D-15: `CSRFFormFieldShim` ASGI middleware bridges classic form POSTs to `starlette-csrf` 3.0.** Resolves the D-05 amendment. The shim is a ~30 LOC ASGI middleware that on any `POST` request whose `Content-Type` starts with `application/x-www-form-urlencoded` or `multipart/form-data` and that does NOT already carry the `X-CSRF-Token` header: (1) buffers the request body via the standard ASGI body-replay pattern (collect `http.request` events until `more_body=false`, then build a fresh `receive` that re-emits them), (2) parses it as form data, (3) reads the `X-CSRF-Token` form field, (4) injects it into `scope["headers"]` as `(b"x-csrf-token", value.encode())`, (5) hands off downstream with the replay-`receive`. Constraints: only mutates headers when the field is present and the header is absent (idempotent for HTMX-driven POSTs that already set the header); preserves multipart body byte-for-byte (chunks are re-emitted in original order with `more_body` flags intact); passes GET and non-form content types through untouched. Module location: append to `app/csrf.py` so all CSRF concerns live in one file. **Mount order in `app/main.py`: added AFTER `CSRFMiddleware` so on the request path it executes OUTSIDE / BEFORE `CSRFMiddleware`.** Final add-order in `create_app()`: `SessionMiddleware` → `CSRFMiddleware` → **`CSRFFormFieldShim` (NEW)** → `FragmentCacheHeadersMiddleware` → `SecurityHeadersMiddleware` → `RequestContextMiddleware` (Starlette reverse-of-add: last-added is outermost; on a request `RequestContext` → `SecurityHeaders` → `FragmentCache` → **shim** → `CSRFMiddleware` → `SessionMiddleware` → route). Test surface: separate `test_csrf_shim.py` covering header-already-present passthrough, form-only POST injection (303 success path observed), multipart POST body preservation (file upload hash matches input), GET passthrough, JSON-content-type passthrough (a real API client is responsible for setting the header itself).

### Claude's Discretion

- **Password policy floor.** Not discussed. Default: argon2-cffi's input handling tolerates anything ≥ 1 char; planner enforces a soft 12-char minimum at the Pydantic schema for `/setup` and Phase 9 user-create. No complexity rules, no HIBP breached-password check (HIBP would add an outbound HTTP call on a route already rate-limited; skip in v1, revisit only if a security review flags it). Username constraints: 3–32 chars, `[A-Za-z0-9_-]` (citext already handles case). Email: validated via Pydantic `EmailStr` when provided.
- **Setup template ergonomics.** Single scrollable form; show a one-line "First-time setup — this creates the household admin account." preamble. Plan-phase picks the exact copy and Tailwind classes; UX baseline from Phase 0's `tailwind.config.js` cream/espresso palette.
- **Login template ergonomics.** "Sign in to Snobbery" heading; username + password fields; CSRF hidden; submit button. Failure path re-renders with the generic D-07 message above the form.
- **Where does the sign-out button live in Phase 2?** Phase 2 doesn't ship a full nav (that's Phase 11). The minimum needed: the placeholder `pages/index.html` gets a tiny "Signed in as {{ user.username }} · <form ...>Sign out</form>" footer when `request.state.user` is non-None; logged-out it shows a link to `/login`. Sufficient for the AUTH-09 / smoke flow without bleeding into nav design.
- **`require_admin` dependency shape.** FastAPI dependency that raises `HTTPException(status_code=403)` if `request.state.user is None or not request.state.user.is_admin`. Plan-phase picks the module location (`app/dependencies/auth.py` or similar) and tests the negative path.
- **Setup-completed read in `GET /setup`.** Use the future-Phase-3 typed `app_settings` reader if it lands first, else a direct `SELECT value FROM app_settings WHERE key = 'setup_completed'` here. Plan-phase decides based on the timing.
- **Atomic flip mechanics.** Plan-phase locks whether the FOR UPDATE / INSERT / UPDATE is done via raw SQL in `app/services/setup.py` or via SQLAlchemy 2.0 `select().with_for_update()` plus an `update()` call. Either is fine; the invariant is "one commit, FOR UPDATE held across the swap."

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` §"Key Decisions" — single uvicorn worker (in-memory rate limiter is consistent); CSRF double-submit-cookie pattern (every Phase 2 form carries the token); no public registration (no `/register` route, ever).
- `.planning/REQUIREMENTS.md` §"Authentication & Sessions" (AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-06, AUTH-07, AUTH-09 — verbatim).
- `.planning/ROADMAP.md` §"Phase 2: Auth" — goal sentence + 5 success criteria + Notes (argon2id params + argon2-verify-on-no-match). Note: success criterion #1 wording ("the route 404s") is amended per D-01 to "302 → /login"; success criterion #5 wording ("setup → login → see /") is amended per D-03 to reflect auto-login.
- `.planning/STATE.md` — current decision accumulator; no plan-phase research flag specific to Phase 2 (the three carried flags belong to Phases 1, 7, 10, 11).
- `.planning/phases/00-foundation/00-CONTEXT.md` — Phase 0 locked the `users` schema (citext username, nullable email with partial unique index, argon2-ready `password_hash` TEXT column), the `app_settings` seed including `setup_completed = "false"`, and the `/` placeholder template that Phase 2 augments with a "Signed in as / Sign in" footer.
- `.planning/phases/01-middleware/01-CONTEXT.md` — Phase 1 locked SessionMiddleware shape (D-07..D-10), session helpers (`regenerate_session` atomic delete+insert), the failed-login logging policy (D-15: `bad_password` with `user_id` when matched, `user_not_found` with no `attempted_username` otherwise), the event taxonomy (D-14), `/debug/proxy` admin-gate hand-off (D-16), and the slowapi limit constants (`LOGIN_LIMIT`, `SETUP_LIMIT` — Phase 2 inherits, doesn't re-declare).

### Operational + spec
- `CLAUDE.md` §"Stack invariants" (argon2-cffi for passwords — explicit; Fernet for API keys — not relevant here; signed session cookies via itsdangerous — already wired); §"Architectural invariants" (no public registration; CSRF on all state-changing forms; security headers on every response); §"Things to never do silently" (no logging passwords / session tokens / API keys — log only event + user_id + ip + request_id per D-14/D-15).
- `docs/snobbery-gsd-prompt.md` — historical spec. Use as reference for the original AUTH intent; .planning/ docs win on conflict.

### External library docs (planner verifies via Context7 during plan-phase, not now)
- `argon2-cffi` >=25.1 — `PasswordHasher(memory_cost=65536, time_cost=3, parallelism=4)` invocation; `verify()` constant-time semantics; `verify_dummy_hash()` or equivalent for the user-not-found branch.
- `starlette-csrf` 3.0 — confirm that `CSRFMiddleware` reads the token from either the `X-CSRF-Token` header OR a form field of the same name on POSTs (so the `<input type=hidden>` pattern works without JS).
- `itsdangerous` 2.2 — already wired in `app/signing.py`; no new usage in Phase 2.
- `sqlalchemy.ext.asyncio` 2.0 — `with_for_update()` syntax on `select()` constructs for the AUTH-02 lock; verify that `commit()` releases the row lock.
- `FastAPI` 0.136 — `Depends` dependency shape for `require_admin`; `RedirectResponse(status_code=303)` for POST-redirect-GET.

### Existing code (read before changing)
- `app/middleware/session.py` — the file to upgrade per D-09/D-10. Existing TODO comment ("Phase 2: replace stub with full User row lookup") marks the exact line.
- `app/services/sessions.py` — all the session helpers Phase 2 needs are already here (`regenerate_session`, `delete_session`, `build_session_cookie`, `build_session_clear_cookie`).
- `app/signing.py` — `sign_session_id` / `load_session_id` already exist.
- `app/routers/auth.py` — Phase 1 stubs to REPLACE (don't add a parallel file).
- `app/routers/debug.py` — wrap `debug_proxy` in `require_admin` per D-14.
- `app/csrf.py` — `CSRF_COOKIE_NAME` and `CSRF_HEADER_NAME` constants Phase 2 templates and routes consume.
- `app/events.py` — event-name constants already declared (`AUTH_LOGIN_SUCCEEDED`, `AUTH_LOGIN_FAILED`, `AUTH_LOGOUT`, `ADMIN_USER_CREATED`); Phase 2 emits them.
- `app/rate_limit.py` — `LOGIN_LIMIT = "5/15minutes"`, `SETUP_LIMIT = "5/15minutes"` constants; the real routes import these the same way the stubs do.
- `app/models/user.py` — schema is final for Phase 2; no migration needed in this phase.
- `app/main.py` — middleware order is locked; Phase 2 changes only the SessionMiddleware *behavior* (D-09/D-10), not its position in the stack.
- `app/migrations/versions/0001_initial.py` and `app/migrations/versions/p1_sessions_table.py` — schema is in place; Phase 2 ships no new migrations.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (all already on disk from Phases 0 + 1)
- **`app.services.sessions`** — Five async helpers cover the full session lifecycle: `create_session`, `regenerate_session` (atomic delete+insert), `delete_session`, `get_session_by_id`, `refresh_last_seen`. Plus two pure cookie-value builders (`build_session_cookie`, `build_session_clear_cookie`). Phase 2 imports these directly; no new session helpers needed.
- **`app.signing.sign_session_id` / `load_session_id`** — `itsdangerous.URLSafeSerializer` bound to `APP_SECRET_KEY` with `salt="session"`. Phase 2's `/login` success path: `regenerate_session()` → `sign_session_id(new_id)` → `build_session_cookie(signed)` → attach to response.
- **`app.middleware.SessionMiddleware`** — Already populates `request.state.user` (currently the `{"user_id": int}` stub). The TODO at `app/middleware/session.py:179` marks the exact line Phase 2 changes per D-09. The async session-factory plumbing is already there.
- **`app.csrf`** — `CSRF_COOKIE_NAME = "csrftoken"`, `CSRF_HEADER_NAME = "X-CSRF-Token"`, `CSRF_SENSITIVE_COOKIES = {"session_id"}` — Phase 2 templates and routes read these constants; no re-declaration.
- **`app.rate_limit`** — `LOGIN_LIMIT` / `SETUP_LIMIT` constants + `limiter` Limiter instance. The Phase 2 real `/login` and `/setup` decorations keep using `@limiter.limit(LOGIN_LIMIT)` / `@limiter.limit(SETUP_LIMIT)` exactly as the Phase 1 stubs do.
- **`app.events`** — `AUTH_LOGIN_SUCCEEDED`, `AUTH_LOGIN_FAILED`, `AUTH_LOGOUT`, `ADMIN_USER_CREATED` constants are pre-declared. Phase 2 emits, doesn't add new constants.
- **`app.templates_setup.templates`** — Jinja2Templates instance with autoescape ON; Phase 2's `setup.html` and `login.html` extend `base.html` and consume the existing `{{ csp_nonce(request) }}` and `{{ request.cookies.get('csrftoken', '') }}` patterns from base.
- **`app.models.user.User`** — Schema is final for Phase 2's needs (id, username citext, email nullable citext, password_hash text, is_admin bool, is_active bool, timestamps, last_login_at). No migration in this phase.

### Established Patterns
- **"Cross-cutting → middleware; feature surface → router; stateful logic → service"** — Phase 2's split: routes in `app/routers/auth.py` (replace stubs), helpers in `app/services/auth.py` (new — argon2 verify, setup transaction, login transaction) and `app/services/setup.py` (new — the FOR-UPDATE first-admin transaction). SessionMiddleware behavior change is in-place per D-11.
- **"Async DB for auth surfaces; sync DB for the rest"** — Sessions, signing, and the cookie helpers all run async (matching `SessionMiddleware`'s factory). Phase 2's setup + login transactions also run async to compose cleanly with `regenerate_session()`. Phase 4+ catalog routes go back to the sync pattern.
- **"Every state-changing POST carries the CSRF token via either header (HTMX) or hidden form input (classic POST)"** — `starlette-csrf` 3.0 accepts both; Phase 2 uses the hidden-input pattern (D-05).
- **"Audit events are structured-logger calls, not custom tables"** — Phase 2 emits `auth.login_succeeded / failed / logout` + `admin.user_created` per Phase 1 D-14; no new `audit_log` table.
- **"Fail-closed on any session-invalidating condition"** — Phase 1 SessionMiddleware already deletes + clears for expired / tampered / missing-row branches. D-10 extends the same pattern to deactivated/deleted users.

### Integration Points
- **`SessionMiddleware` upgrade** — single-file change at `app/middleware/session.py`. The cookie / signing / row-fetch flow already in place; only the User-row lookup and the deactivated-user branch are new.
- **`app/routers/auth.py`** — full body replacement. Keep the file, replace the stub bodies with real implementations + new `/logout` handler.
- **`app/routers/admin.py`** — NEW file in Phase 2 (one route, `GET /admin`). Phase 9 expands this into the full admin surface.
- **`app/routers/debug.py`** — single-line change: wrap `debug_proxy` in `Depends(require_admin)`.
- **`app/dependencies/auth.py`** — NEW module Phase 2 introduces for `require_admin` (and possibly `require_user`). Phase 9 reuses these dependencies.
- **`app/templates/pages/setup.html`** and **`app/templates/pages/login.html`** — NEW templates extending `base.html`. The `|safe` grep CI test set up in Phase 1 already covers them — no special handling.
- **`app/templates/pages/index.html`** — small augmentation: footer with "Signed in as {{ user.username }} · sign-out POST form" when `request.state.user` is non-None.
- **`pyproject.toml`** — add `argon2-cffi>=25.1,<26` to dependencies. No requirements.txt convention in this project; pyproject is canonical.
- **`app/services/auth.py`** (NEW) — `verify_password`, `hash_password`, `argon2_dummy_verify` (constant-time defense for user-not-found per Phase 1 D-15).
- **`app/services/setup.py`** (NEW) — `create_first_admin(db, username, email, password)` running the FOR UPDATE + INSERT + setting-flip in one TX.

</code_context>

<specifics>
## Specific Ideas

- **Plan-phase: amend ROADMAP success criteria #1 and #5** for Phase 2 to match D-01 (302 → /login) and D-03 (auto-login → /). The ROADMAP is a living doc; minor wording fixes that reflect locked context decisions belong in the plan-phase open as a doc commit.
- **303 See Other, not 302** — post-redirect-GET pattern requires 303 to force the browser to GET after a POST, even on HTTP/1.0 clients. FastAPI's `RedirectResponse(status_code=303)`.
- **Failed-login generic message wording locked** — "Invalid username or password." Single sentence, no variation. Aligned with constant-time backend per Phase 1 D-15.
- **`require_admin` dependency lives in a new `app/dependencies/` package** so the empty `app/dependencies/__init__.py` is the convention Phase 9 inherits when it adds more dependencies (`require_active_user`, etc.).
- **`/setup` form intentionally has no "I am admin" checkbox** — first user is always admin; `is_admin=true` is set by the service-layer code, not user input.
- **The `setup_completed` write happens via the typed `value` column (currently text "true" / "false"); plan-phase confirms** the `app_settings` value_type for that row is `boolean` per Phase 0 D-17 and the typed reader (when it lands in Phase 3) returns a Python bool.
- **Phase 2 does NOT ship a new migration.** All tables and seeds are in place from Phases 0 + 1. If plan-phase finds a need (e.g., an index), it can add a small migration — but the expectation is none.

</specifics>

<deferred>
## Deferred Ideas

- **"Sign out everywhere" UX** — Phase 1 D-09 already rejected for v1; revisit if/when a `device_label` column lands on `sessions`.
- **Password reset / recovery flow.** Not in v1 — relies on email infrastructure that's also out of scope. Note the dependency for v2 planning.
- **Breached-password (HIBP k-anonymity) check.** Considered under "Claude's Discretion / Password policy floor" — rejected for v1 to keep `/setup` and Phase 9 user-create free of outbound HTTP. Revisit only if a security review flags it.
- **Complex password policy (special chars, mixed case, common-password blocklist).** Considered — rejected for v1. argon2id makes brute-force expensive enough that a 12-char minimum is sufficient at household scale.
- **Periodic expired-session sweep job** — Phase 8 owns the APScheduler job per the comment in `app/services/sessions.py`. Phase 2 doesn't ship cleanup.
- **`?next=` query-param support on `/login`** — D-06 punts to "Revisit only if a Phase 4+ flow proves the friction is real." Note in deferred so the discussion isn't lost.
- **HTMX-friendly 429 error template for the rate-limit handler** — D-08 leaves the JSON handler in place; revisit only if user feedback says the JSON page is jarring during a real attack.
- **`require_active_user` dependency** (separate from `require_admin`) — Phase 4+ guarded routes will want this. Phase 2 establishes the `app/dependencies/auth.py` module location so Phase 4 has a home for it.
- **Admin email vs personal email separation in `users`** — current schema has one `email` column. Adequate for v1; v2 might want a separate `recovery_email` if recovery flows land.

</deferred>

---

*Phase: 2-Auth*
*Context gathered: 2026-05-17*
