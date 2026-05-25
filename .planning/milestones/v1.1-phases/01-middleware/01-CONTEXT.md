# Phase 1: Middleware - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Cross-cutting middleware infrastructure that every later router relies on. No user-facing UI yet.

In scope:
- uvicorn proxy-header trust (configured via `--proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS` — leaning on Phase 0 plumbing)
- Per-request CSP nonce minting + the full security-header set on every response
- Structured logging with `request_id` correlation (structlog + ProcessorFormatter merging uvicorn / FastAPI / SQLAlchemy)
- `sessions` table + custom table-backed `SessionMiddleware` resolving `request.state.user`
- Double-submit-cookie CSRF via `starlette-csrf`
- slowapi rate limiter wired but applied only to `/login` and `/setup` at this phase
- Jinja2 autoescape on globally; CI grep test forbidding `|safe` under `app/templates/pages/`
- README NGINX server-block example documenting HSTS + `proxy_set_header X-Forwarded-Proto $scheme` + `proxy_buffering off` for future SSE
- Stub `/login` route (returns 200) so slowapi can be exercised; the real login lands in Phase 2
- `/debug/proxy` endpoint (public in this phase; Phase 2 wraps it behind `is_admin`)
- `/csp-report` log-only endpoint with its own slowapi limiter

Out of scope (belongs in later phases):
- Real `/login` / `/setup` route bodies (Phase 2)
- Argon2id verify + session-ID regeneration on login (Phase 2)
- Encryption service or `api_credentials` (Phase 3)
- Any feature router (Phase 4+)
- Per-fragment route decisions about what is fragment-vs-full-page (Phase 4+ routers use the middleware locked here)

8 requirements mapped: AUTH-05, AUTH-08, AUTH-10, SEC-01, SEC-02, SEC-03, SEC-04, SEC-05.

</domain>

<decisions>
## Implementation Decisions

### CSP — strict path, no `'unsafe-eval'`

- **D-01:** Use the **Alpine.js CSP build**. Every Alpine component is registered as a module via `Alpine.data('name', factory)` in `app/static/js/alpine-components/*.js`; templates reference components by name (`x-data="counter"`, never `x-data="{ count: 0 }"`). `'unsafe-eval'` is forbidden from `script-src`.
- **D-02:** **`script-src 'self' 'nonce-...'`** with a per-request nonce minted by middleware. **No `'unsafe-eval'`, no `'unsafe-inline'` for scripts.** The nonce is available to templates via the request (planner picks the exact plumbing — `request.state.csp_nonce` is the natural choice).
- **D-03:** **Split style directives** — `style-src-elem 'self' 'nonce-...'` (strict) + `style-src-attr 'unsafe-inline'`. Lets Alpine `x-transition` and `x-bind:style` work without giving up CSP on `<style>` blocks or external stylesheets. CSP3-only; modern-phone browser support is fine for this audience.
- **D-04:** **Ban `hx-on:*` inline handlers in templates.** HTMX `hx-on:click` uses `new Function()` internally and would otherwise require `'unsafe-eval'`. JS behavior lives in `app/static/js/htmx-listeners.js` (event delegation via `htmx:configRequest`, `htmx:beforeRequest`, `htmx:afterSwap`). CI grep test forbids `hx-on:` under `app/templates/pages/` (lands alongside the `|safe` grep test from SEC-05).
- **D-05:** Full CSP baseline: `default-src 'self'; script-src 'self' 'nonce-...'; style-src-elem 'self' 'nonce-...'; style-src-attr 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; report-to csp-report; report-uri /csp-report`. Planner confirms each directive against an actual prototype before locking.
- **D-06:** **CSP violation reporting via log-only endpoint.** `POST /csp-report` (and matching `report-to` directive). slowapi-limited to 30/min/IP. Strips PII, logs as a structured event: `event=csp.violation, blocked_uri, violated_directive, line, source_file, request_id`. **No `csp_violations` table, no admin UI in v1** — grep logs. Re-evaluate adding storage + an admin view in Phase 9 if violations turn out to be common.

### Sessions — minimal table, single-device logout

- **D-07:** `sessions` table columns (and only these): `session_id` (UUID PK), `user_id` (FK to `users`, NOT NULL), `last_seen` (timestamptz), `expires_at` (timestamptz), `created_at` (timestamptz). **No `ip`. No `user_agent`. No `device_label`.** Tightest privacy footprint; Phase 9 active-sessions admin shows count + per-row `last_seen` only.
- **D-08:** **Session row exists only for authenticated requests.** No pre-auth rows. CSRF state is handled by `starlette-csrf`'s cookie, independent of the sessions table.
- **D-09:** **Logout deletes the current session row only.** No "sign out everywhere" UX in v1. Other devices wait for the 30-day expiry. Consistent with the no-device-info schema choice — there is no per-device list to attach a "sign out everywhere" button to.
- **D-10:** Session ID regeneration on every successful login, logout, and `is_admin` toggle (PITFALL SEC-3): delete the old row, mint a new UUID, set the new signed cookie. Cookie is `HttpOnly; Secure; SameSite=Lax`, signed via `itsdangerous` using `APP_SECRET_KEY`, 30-day max-age, refresh on activity. (Spec already locks these; restated here so the planner has them in one place.)

### HTMX fragment + full-page cache policy

- **D-11:** **Single `FragmentCacheHeadersMiddleware` applies cache headers based on `HX-Request`**, fail-safe (no per-route opt-in):
  - **When `HX-Request: true`** → response gets `Cache-Control: no-store` + `Vary: HX-Request`. Solves PITFALL HX-2 by default.
  - **When `HX-Request` absent (full page)** → response gets `Cache-Control: private, no-cache, must-revalidate`. Allows bfcache (fast back-button), forces revalidation so a logged-out user clicking "back" doesn't see a cached authenticated page.
  - Static assets (mounted under `/static/`) are untouched by this middleware — `StaticFiles` sets its own cache headers.
- **D-12:** Phase 4+ router authors do **not** need a `FragmentResponse` subclass, decorator, or dependency. The middleware is the contract. If a future case needs explicit override (e.g., an `ETag`-friendly static-ish full page), set headers directly on the response and the middleware respects existing `Cache-Control` (planner spec: "do not overwrite if already set by the route").
- **D-13:** PITFALL HX-2 mitigations 2 + 3 (lazy-load `hx-history="false"` convention, full-body + `hx-select` pattern for routes with `hx-push-url`) are template-level conventions — documented in the Phase 1 README section, enforced in Phase 4+ code review, not encoded in middleware.

### Audit logging + `/debug/proxy`

- **D-14:** Structured-logger **event taxonomy** for auth + admin events: `auth.login_succeeded`, `auth.login_failed`, `auth.logout`, `admin.user_created`, `admin.user_deleted`, `admin.password_reset`, `admin.is_admin_toggled`, `csp.violation`. Every event carries: `event`, `request_id`, `ip`, `timestamp_iso`. Auth events that resolved to a real user also carry `user_id`. No request bodies, no passwords, no session tokens, no API keys.
- **D-15:** **Failed-login username policy** — log the attempted username **only when it matches a real user**:
  - Real user, wrong password → `event=auth.login_failed, user_id, ip, reason=bad_password`.
  - Unknown username → `event=auth.login_failed, ip, reason=user_not_found`. **No `attempted_username` field.**
  - Argon2-verify runs in both branches (constant-time, defends against user-enumeration via response timing — Phase 2 implements; restated for posterity).
- **D-16:** **`/debug/proxy` endpoint lifecycle**: Phase 1 ships it public (auth doesn't exist yet). Phase 2 wraps the route in the `is_admin` gate. **Permanent operational endpoint** — used after every NGINX config change to confirm `X-Forwarded-Proto` / `X-Forwarded-For` are flowing. Returns: `request.url.scheme`, the resolved client IP, the configured `TRUSTED_PROXY_IPS` list, and a boolean "headers honored" verdict. The Phase 9 note's "or removed here" clause is dropped — the endpoint stays.
- **D-17:** **Slowapi storage**: in-memory (slowapi default). Single uvicorn worker is locked from Phase 0, so a single in-memory limiter is consistent across requests. No Redis. `/login` and `/setup` get `5/15minutes` per-IP per AUTH-08; `/csp-report` gets `30/minute` per-IP.

### Claude's Discretion

- Exact middleware stack order — planner picks based on Starlette `add_middleware` reverse-order semantics, but a sensible order is: ProxyHeaders (uvicorn flag) → SessionMiddleware (resolves `request.state.user`) → `starlette-csrf` CSRFMiddleware → SecurityHeadersMiddleware (emits CSP + headers using the nonce from `request.state`) → FragmentCacheHeadersMiddleware → StructuredLoggingMiddleware (request_id assignment outermost so every other middleware can log against it) → slowapi → router.
- Nonce plumbing into Jinja — `request.state.csp_nonce` set by middleware, exposed to templates either via FastAPI dependency override or a small Jinja context processor. Either is fine.
- Cookie names and signing-serializer details (`URLSafeSerializer` vs `URLSafeTimedSerializer`) — planner's call.
- Concrete CSP directive list per D-05 — planner validates each directive against an actual prototype before locking.
- Whether to use `report-to` (newer, with Reporting API) or `report-uri` (deprecated but universally supported) or both — pragmatic: emit both for now; drop `report-uri` when browser support permits.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` §"Key Decisions" — CSRF double-submit-cookie pattern (row 15), MultiFernet (row 17), single uvicorn worker (row 14), HTMX 2.x (row 8 region), Tailwind standalone CLI (row 9 region) are all locked here.
- `.planning/REQUIREMENTS.md` §"Authentication & Sessions" (AUTH-05, AUTH-08, AUTH-10) and §"Security Hardening" (SEC-01 through SEC-05) — the 8 requirements mapped to this phase, verbatim.
- `.planning/ROADMAP.md` §"Phase 1: Middleware" — goal, success criteria, dependencies, plan-phase research flag (Alpine CSP prototype).
- `.planning/STATE.md` — current decision accumulator; plan-phase research flag list includes the Alpine CSP prototype for Phase 1.

### Research output
- `.planning/research/STACK.md` §1 (pinned versions of Starlette 1.0, FastAPI 0.136, structlog 25.5, itsdangerous 2.2, slowapi 0.1.9), §2 (gap-library picks: `starlette-csrf`, hand-rolled session middleware, `slowapi`, `structlog`), §3.2 (HTMX 2.x deltas), §3.6 (custom session store collision with Starlette `SessionMiddleware`).
- `.planning/research/PITFALLS.md` §2 (HX-1 CSRF rotation, HX-2 bfcache fragments), §4 (SH-6 X-Forwarded-Proto), §5 (SEC-1 CSP/Alpine trade-off, SEC-3 session-ID regeneration). HX-2 and SEC-1 are the most load-bearing for this phase.
- `.planning/research/ARCHITECTURE.md`, `.planning/research/FEATURES.md`, `.planning/research/SUMMARY.md` — context only; nothing Phase-1-specific that isn't already pulled into the other refs.

### Operational + spec
- `CLAUDE.md` §"Stack invariants" + §"Architectural invariants" + §"Things to never do silently" — reverse-proxy honor, CSRF + security headers on every response, no logging of API keys/passwords/session tokens.
- `docs/snobbery-gsd-prompt.md` — original product brief. Historical reference; CLAUDE.md and the .planning/ docs are authoritative where they diverge.

### External library docs (planner verifies via Context7 in plan-phase, not now)
- `starlette-csrf` (PyPI `>=3.0,<4`) — for double-submit-cookie configuration knobs.
- `structlog` 25.5 — for the stdlib `ProcessorFormatter` integration pattern used in this phase.
- Alpine.js CSP build — declarative-only directive set; what works under the CSP build vs the default build.
- HTMX 2.0.10 — `htmx-ext-sse` is loaded in Phase 7, not here; this phase just needs the core HTMX script.

</canonical_refs>

<code_context>
## Existing Code Insights

**Greenfield phase — no existing application code yet.** Phase 0 (Foundation) will land the Docker stack, Postgres extensions, first migration set, structlog config, and the uvicorn entrypoint. Phase 1 builds on that scaffolding; nothing in this phase has prior code to refactor or extend.

### Anticipated file layout (planner confirms during plan-phase)
- `app/middleware/` — new package for: `session.py` (custom table-backed SessionMiddleware), `security_headers.py` (CSP + the X-Frame-Options / X-Content-Type-Options / Referrer-Policy / Permissions-Policy set), `fragment_cache.py` (the HX-Request-aware cache-headers middleware), `request_id.py` (request-id assignment + structlog binding).
- `app/services/` — already established by Phase 0 as the home for service modules; nothing in this phase lands there yet (Phase 3 puts `encryption.py` here, Phase 6 puts `analytics.py`).
- `app/static/js/` — `htmx-listeners.js` (event delegation replacing banned `hx-on:` handlers) + `alpine-components/` directory for module-registered Alpine components. Phase 1 ships placeholders to establish convention.
- `app/templates/pages/` + `app/templates/fragments/` — autoescape-on globally. CI `|safe` and `hx-on:` grep tests target `app/templates/pages/` (fragments may eventually need narrower rules; revisit if needed).
- `app/migrations/` — one new migration that creates the `sessions` table.

### Established patterns (set by this phase, used by Phase 4+)
- "Cross-cutting concern → middleware" — anything every router needs lands in `app/middleware/` and is added to the stack once. Routers don't import middleware; they consume `request.state` and rely on injected headers.
- "Every authenticated full-page response is `private, no-cache, must-revalidate`; every HTMX fragment is `no-store`" — applied by FragmentCacheHeadersMiddleware. Routers do not set these headers themselves.
- "Audit events are structured-logger calls, not custom tables" — `log.info("auth.login_succeeded", user_id=..., ip=..., request_id=...)`. Phase 9 admin reads logs (Docker stdout / syslog), not a `audit_log` table.

</code_context>

<specifics>
## Specific Ideas

- `/csp-report` rate limit: **30/min/IP** (slowapi). Higher than `/login`'s 5/15min because a single broken page can fire dozens of CSP violations in a few seconds; lower than uncontrolled.
- `Permissions-Policy` directive list locked by ROADMAP success criteria: `camera=(self), microphone=(), geolocation=()`. Planner extends with `interest-cohort=()` (block FLoC), `payment=()`, `usb=()`, `bluetooth=()` if it's cheap to be exhaustive; otherwise the spec set is sufficient.
- Permissions-Policy `camera=(self)` is required for the bag-photo capture flow in Phase 4 (the `<input capture="environment">` control).
- CI grep tests (added in Phase 1, enforced by Phase 12): `|safe` forbidden under `app/templates/pages/`; `hx-on:` forbidden under `app/templates/pages/`; `os.environ` forbidden outside `app/config.py` (already implied by FOUND-10).

</specifics>

<deferred>
## Deferred Ideas

- **CSP `csp_violations` table + admin viewer.** Considered in CSP discussion; rejected for v1 as overbuilt for two users. Reconsider in Phase 9 if grep'ing logs for violations becomes a recurring task.
- **"Sign out everywhere" UX.** Considered in sessions discussion; rejected for v1 as inconsistent with the minimal-sessions schema (no device list to attach the action to). Reconsider when/if a `device_label` column lands.
- **Audit log retention beyond Docker stdout / host syslog.** Not discussed; planner can default to "rely on Docker log rotation + the host syslog" without further input. If long-term audit retention becomes a requirement, that's a separate phase.
- **Absolute session-expiry cap on top of sliding 30-day refresh.** Not discussed; planner defaults to sliding-only per spec. Revisit only if a security review flags it.

</deferred>

---

*Phase: 1-Middleware*
*Context gathered: 2026-05-16*
