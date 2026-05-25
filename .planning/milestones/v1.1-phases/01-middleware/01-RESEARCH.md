# Phase 1: Middleware - Research

**Researched:** 2026-05-16
**Domain:** Cross-cutting ASGI middleware (Starlette 1.0 / FastAPI 0.136) — CSP nonce, table-backed sessions, double-submit-cookie CSRF, structlog correlation, slowapi rate limiting, HX-Request-aware fragment cache headers
**Confidence:** HIGH (CONTEXT.md decisions cross-checked against upstream docs; one CONTEXT.md adjustment surfaced — see §1 Decisions for the planner)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**CSP — strict path, no `'unsafe-eval'`**
- **D-01:** Use the **Alpine.js CSP build**. Every Alpine component is registered as a module via `Alpine.data('name', factory)` in `app/static/js/alpine-components/*.js`; templates reference components by name (`x-data="counter"`, never `x-data="{ count: 0 }"`). `'unsafe-eval'` is forbidden from `script-src`.
- **D-02:** **`script-src 'self' 'nonce-...'`** with a per-request nonce minted by middleware. **No `'unsafe-eval'`, no `'unsafe-inline'` for scripts.** The nonce is available to templates via the request (planner picks the exact plumbing — `request.state.csp_nonce` is the natural choice).
- **D-03:** **Split style directives** — `style-src-elem 'self' 'nonce-...'` (strict) + `style-src-attr 'unsafe-inline'`. Lets Alpine `x-transition` and `x-bind:style` work without giving up CSP on `<style>` blocks or external stylesheets. CSP3-only; modern-phone browser support is fine for this audience.
- **D-04:** **Ban `hx-on:*` inline handlers in templates.** HTMX `hx-on:click` uses `new Function()` internally and would otherwise require `'unsafe-eval'`. JS behavior lives in `app/static/js/htmx-listeners.js` (event delegation via `htmx:configRequest`, `htmx:beforeRequest`, `htmx:afterSwap`). CI grep test forbids `hx-on:` under `app/templates/pages/` (lands alongside the `|safe` grep test from SEC-05).
- **D-05:** Full CSP baseline: `default-src 'self'; script-src 'self' 'nonce-...'; style-src-elem 'self' 'nonce-...'; style-src-attr 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; report-to csp-report; report-uri /csp-report`. Planner confirms each directive against an actual prototype before locking.
- **D-06:** **CSP violation reporting via log-only endpoint.** `POST /csp-report` (and matching `report-to` directive). slowapi-limited to 30/min/IP. Strips PII, logs as a structured event: `event=csp.violation, blocked_uri, violated_directive, line, source_file, request_id`. **No `csp_violations` table, no admin UI in v1** — grep logs. Re-evaluate adding storage + an admin view in Phase 9 if violations turn out to be common.

**Sessions — minimal table, single-device logout**
- **D-07:** `sessions` table columns (and only these): `session_id` (UUID PK), `user_id` (FK to `users`, NOT NULL), `last_seen` (timestamptz), `expires_at` (timestamptz), `created_at` (timestamptz). **No `ip`. No `user_agent`. No `device_label`.**
- **D-08:** **Session row exists only for authenticated requests.** No pre-auth rows. CSRF state is handled by `starlette-csrf`'s cookie, independent of the sessions table.
- **D-09:** **Logout deletes the current session row only.** No "sign out everywhere" UX in v1.
- **D-10:** Session ID regeneration on every successful login, logout, and `is_admin` toggle. Delete old row, mint new UUID, set new signed cookie. Cookie is `HttpOnly; Secure; SameSite=Lax`, signed via `itsdangerous` using `APP_SECRET_KEY`, 30-day max-age, refresh on activity.

**HTMX fragment + full-page cache policy**
- **D-11:** **Single `FragmentCacheHeadersMiddleware`** keyed off `HX-Request`. When `HX-Request: true` → `Cache-Control: no-store` + `Vary: HX-Request`. When absent → `Cache-Control: private, no-cache, must-revalidate`. Static `/static/` mount excluded.
- **D-12:** No `FragmentResponse` subclass / decorator / dependency. Middleware does not overwrite an existing `Cache-Control` set by the route.
- **D-13:** HX-2 mitigations 2 + 3 (lazy-load `hx-history="false"`, full-body + `hx-select` with `hx-push-url`) are template-level conventions — documented in the Phase 1 README, enforced in Phase 4+ code review.

**Audit logging + `/debug/proxy`**
- **D-14:** Event taxonomy: `auth.login_succeeded`, `auth.login_failed`, `auth.logout`, `admin.user_created`, `admin.user_deleted`, `admin.password_reset`, `admin.is_admin_toggled`, `csp.violation`. Every event carries `event`, `request_id`, `ip`, `timestamp_iso`. Auth events that resolved to a real user also carry `user_id`. No request bodies, no passwords, no session tokens, no API keys.
- **D-15:** **Failed-login username policy** — log `user_id` only when the attempted username matches a real user (reason `bad_password`). Unknown username → log `reason=user_not_found` without an `attempted_username` field. Argon2-verify runs in both branches (Phase 2 implements).
- **D-16:** **`/debug/proxy` endpoint** ships public in Phase 1 (auth doesn't exist yet); Phase 2 wraps it behind `is_admin`. Permanent operational endpoint. Returns `request.url.scheme`, resolved client IP, configured `TRUSTED_PROXY_IPS` list, and a boolean "headers honored" verdict.
- **D-17:** **Slowapi storage**: in-memory (slowapi default). Single uvicorn worker is locked from Phase 0. `/login` and `/setup` get `5/15minutes` per-IP per AUTH-08; `/csp-report` gets `30/minute` per-IP.

### Claude's Discretion

- Exact middleware stack order — planner picks based on Starlette `add_middleware` reverse-of-add semantics. Sensible order: ProxyHeaders (uvicorn flag) → SessionMiddleware → `starlette-csrf` CSRFMiddleware → SecurityHeadersMiddleware → FragmentCacheHeadersMiddleware → StructuredLoggingMiddleware (outermost) → slowapi → router.
- Nonce plumbing into Jinja — `request.state.csp_nonce` via FastAPI dependency override or small Jinja context processor.
- Cookie names and signing-serializer details (`URLSafeSerializer` vs `URLSafeTimedSerializer`) — planner's call.
- Concrete CSP directive list per D-05 — planner validates each directive against a prototype.
- Whether to emit `report-to` (Reporting API) or `report-uri` (deprecated but universally supported) or both.

### Deferred Ideas (OUT OF SCOPE)

- CSP `csp_violations` table + admin viewer. Considered, rejected for v1.
- "Sign out everywhere" UX.
- Audit log retention beyond Docker stdout / host syslog.
- Absolute session-expiry cap on top of sliding 30-day refresh.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-05 | Custom session middleware backed by a `sessions` table (cookie holds session ID), 30-day expiry, refresh on activity | §5 (custom table-backed SessionMiddleware as pure ASGI, `URLSafeTimedSerializer` cookie, sliding refresh with write-throttling) |
| AUTH-08 | `/login` rate-limited to 5 attempts per IP per 15 minutes via slowapi | §7 (slowapi setup, key_func, in-memory storage, decorator pattern, known `get_ipaddr` bug) |
| AUTH-10 | Auth events logged with user ID, IP, timestamp; no PII or request bodies in logs | §6 (structlog event taxonomy, redaction processors, contextvars request_id binding) |
| SEC-01 | CSRF protection via `starlette-csrf` double-submit-cookie pattern; HTMX-compatible (no rotated-per-request tokens) | §3 (`starlette-csrf` 3.0 configuration, cookie stays fixed for session, HTMX `<meta>` + `htmx:configRequest` recipe) |
| SEC-02 | CSP on every response: nonce-based for scripts and styles; Alpine.js CSP build; `hx-on:` avoided; any residual `'unsafe-eval'` documented | §1 (Alpine CSP build directive set verified — **`'unsafe-eval'` CAN be avoided entirely** in the locked stack), §2 (HTMX `eval` features banned), §9 (CSP nonce minting + directive set) |
| SEC-03 | Security headers on every response: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(self), microphone=(), geolocation=()` | §9 (SecurityHeadersMiddleware emits the full set) |
| SEC-04 | README documents NGINX `Strict-Transport-Security` line | §10 (server-block example with HSTS, `X-Forwarded-*` headers, `proxy_buffering off`) |
| SEC-05 | Jinja2 autoescape on; CI grep test forbids `|safe` in `app/templates/pages/` | §4 (Jinja env config + grep test pattern; same grep job covers `hx-on:` ban from D-04) |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Proxy-header trust | uvicorn process flag | — | Uvicorn's `ProxyHeadersMiddleware` runs before any ASGI middleware; cannot move to app code. |
| CSP nonce minting | Custom ASGI middleware | Jinja (consumer) | Nonce is a per-request property — middleware mints, route handlers pass to templates via `request.state`. |
| Security headers emission | Custom ASGI middleware | — | Headers are response-side only; one place to set them all. |
| CSRF enforcement | `starlette-csrf` middleware | Templates (token in `<meta>` for HTMX) | Library-owned middleware; templates expose token; client (`htmx-listeners.js`) attaches header. |
| Session resolution | Custom ASGI middleware backed by DB | `request.state.user` | Each request needs `user` resolved before any route runs; middleware is the natural place. |
| Rate limiting | slowapi (in-memory storage) | Per-route decorator | slowapi is decorator-driven, not middleware-driven, so it scopes to specific routes per D-17. |
| Request correlation logging | Custom ASGI middleware (request_id assignment) + `contextvars` | structlog processors | Outermost middleware so every other log line carries the same `request_id`. |
| Fragment cache headers | Custom ASGI middleware | — | Single fail-safe contract for every later route. |
| Jinja autoescape | Templating engine config | CI grep test (CI is enforcement, not architecture) | Library default; the grep test ensures no one disables it via `\|safe`. |

---

## Summary

Phase 1 lands seven concerns into one ASGI middleware stack that every later phase consumes through `request.state`, response headers, and structlog context. The locked stack (CONTEXT.md D-01..D-17) is sound — verified against current upstream behavior with **one practical adjustment** worth surfacing:

- **CONTEXT.md D-03's split-style-directive trick is defensible BUT slightly over-specified.** Alpine `x-transition` does NOT actually require `style-src-attr 'unsafe-inline'` in practice — per MDN, `style-src-attr` only governs the `style="..."` attribute set via `setAttribute()` or `cssText`. Alpine's transition engine uses **direct `element.style.property = value` assignments**, which are NEVER blocked by CSP regardless of `style-src` configuration. Keeping `style-src-attr 'unsafe-inline'` is defensive for `x-bind:style="..."` (which uses `setAttribute`) and harmless. Recommend keeping D-03 as written but documenting why in the README so a future contributor doesn't try to tighten it without understanding the distinction.

The **plan-phase research flag (Alpine CSP `'unsafe-eval'` avoidability) RESOLVES TO: confirmed, `'unsafe-eval'` is fully avoidable** under the locked stack (Alpine CSP build + ban on HTMX `hx-on:` + ban on `js:` prefix in `hx-vals` / `hx-headers`). Document in `docs/decisions/0001-csp-strict-no-unsafe-eval.md` per SEC-02.

The two real load-bearing decisions for the planner:

1. **Use pure ASGI middleware (`__call__(scope, receive, send)`), NOT `BaseHTTPMiddleware`**, for every middleware in `app/middleware/`. `BaseHTTPMiddleware` is documented to break `contextvars.ContextVar` propagation — which would silently destroy the structlog `request_id` correlation that AUTH-10 depends on. Starlette 1.0 docs explicitly recommend pure ASGI; `BaseHTTPMiddleware` is on a soft-deprecation path.
2. **Use `URLSafeSerializer` (not `URLSafeTimedSerializer`) for the session cookie**, with the expiry enforced server-side by `sessions.expires_at`. Reasoning: the cookie is just the signed session ID; the authoritative expiry lives in the DB row. Using `URLSafeTimedSerializer` puts two clocks in play (cookie-side and DB-side) with no benefit. The cookie's `Max-Age` attribute (30 days, sliding) handles browser-side expiry.

**Primary recommendation:** Build five middleware modules in `app/middleware/` as pure ASGI classes, register them in this order via `app.add_middleware` (last added = outermost):
```
app.add_middleware(SessionMiddleware, ...)             # innermost — runs closest to route, sets request.state.user
app.add_middleware(CSRFMiddleware, ...)                # starlette-csrf
app.add_middleware(FragmentCacheHeadersMiddleware)
app.add_middleware(SecurityHeadersMiddleware)          # consumes request.state.csp_nonce minted below
app.add_middleware(RequestContextMiddleware)           # outermost — mints request_id + csp_nonce, binds contextvars
```
slowapi attaches via `app.state.limiter` and exception handler — not as middleware. Uvicorn `--proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS` is a process flag, not middleware.

---

## Project Constraints (from CLAUDE.md)

The planner MUST honor these CLAUDE.md directives — they have the same authority as locked CONTEXT.md decisions:

| Directive | Source | How It Constrains Phase 1 |
|-----------|--------|---------------------------|
| Python 3.12 + FastAPI; SQLAlchemy 2.0 typed `Mapped[...]` columns | Stack invariants | `sessions` model uses `Mapped[uuid.UUID]`, `Mapped[datetime]`, etc. |
| `psycopg` 3 driver | Stack invariants | DB URL `postgresql+psycopg://...`; no `psycopg2` references. |
| `argon2-cffi` for passwords, `Fernet` for keys, `itsdangerous` for cookie signing | Stack invariants | Phase 1 uses `itsdangerous` only (no password/key handling yet). |
| `from __future__ import annotations` + type hints required on signatures | Stack invariants | All new middleware and helpers carry typed signatures. |
| Pydantic v2 for request/response/form schemas | Stack invariants | `/debug/proxy` response uses a Pydantic v2 model. |
| `ruff format` + `ruff check` (warnings as errors) | Stack invariants | Phase plan should specify ruff run as gating check. |
| No `os.environ` reads outside `app/config.py` | Things to never do silently | `APP_SECRET_KEY`, `TRUSTED_PROXY_IPS` consumed via `Settings`. |
| CSRF + security headers on every response — no exceptions | Architectural invariants | FragmentCacheHeadersMiddleware never sets `Cache-Control` in a way that bypasses SecurityHeadersMiddleware. |
| Honor `X-Forwarded-*` headers; never hardcode hostnames or schemes | Architectural invariants | Phase 1 success depends on this; uvicorn `--proxy-headers` is mandatory. |
| Never log API keys, passwords, or session tokens | Things to never do silently | structlog redaction processors are required; testable via fixture. |
| No npm build pipeline; Tailwind via standalone CLI | Stack invariants | Phase 1 does not add JS bundlers; Alpine + HTMX consumed as static files. |

---

## 1. Alpine.js CSP Build Directive Set (resolves plan-phase research flag)

### Findings

**CDN URL** (Alpine 3.14.x current line; 3.16 is the version called out in CONTEXT.md but the CSP build package name is `@alpinejs/csp` not `alpinejs`):
```html
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/[email protected]/dist/cdn.min.js" nonce="{{ request.state.csp_nonce }}"></script>
```
`[VERIFIED: alpinejs.dev/advanced/csp]` `[VERIFIED: adrianshaynes.com/posts/setting-up-alpinejs-csp-build]` The CSP build is a separate npm package (`@alpinejs/csp`) — you must use this URL, NOT the standard `alpinejs/dist/cdn.min.js`. **Version pinning note:** the latest 3.14.x is the documented current version in the npm registry for `@alpinejs/csp`. The "3.16" in CONTEXT.md likely tracks the main `alpinejs` package version; the CSP package version diverges. **The planner should pin the exact `@alpinejs/csp` CDN version after running `npm view @alpinejs/csp version` during plan-phase** (or document the SRI hash).

**Source-code-verified directive support** `[VERIFIED: github.com/alpinejs/alpine/blob/main/packages/csp/src/index.js]`:

| Alpine Directive | CSP build status | Notes |
|------------------|-----------------|-------|
| `x-data="componentName"` (registered via `Alpine.data()`) | Works | The ONLY form allowed — inline object literals (`x-data="{ count: 0 }"`) FORBIDDEN. |
| `x-text="property"` | Works | Read-only property access. |
| `x-show="property"` | Works | Reads boolean property. |
| `x-bind:attr="property"` / `:attr="property"` | Works | Read-only. |
| `x-bind:style="property"` / `:style="property"` | Works — uses `setAttribute('style', ...)`, governed by `style-src-attr` | See "Style directive interaction" below. |
| `x-bind:class="property"` / `:class="property"` | Works | Read-only. |
| `x-on:event="method"` / `@event="method"` | Works | Calls method by name. **Inline JS expressions (`@click="count++"`) FORBIDDEN.** Use a method on the component. |
| `x-init="method"` | Works | Calls method on init. |
| `x-effect="method"` | Works | Method-only. |
| `x-transition` (default + `x-transition.opacity` style modifiers) | Works — uses direct `element.style.X = Y` assignment, NOT blocked by `style-src-attr` per MDN | The opacity / scale transitions ship inline-style-FREE via direct property assignment. |
| `x-show.transition` | Works | Same engine as `x-transition`. |
| `x-cloak` | Works | CSS-driven, no JS expression. |
| `x-ref="name"` | Works | String key only. |
| `x-for="item in items"` | Works without method arguments per Hyva docs | Use `Alpine.data` factory to expose the array. |
| `x-if="property"` | Works | Read-only boolean. |
| `x-teleport="#selector"` | Works | Selector string. |
| `x-html` | **DISABLED — replaced with noop in CSP build** | Confirmed via source file review. Never works under CSP build. |
| `x-model` | **NOT SUPPORTED** — internally requires unsafe-eval | Per github.com/alpinejs/alpine discussion #3996. **Two-way binding must be implemented manually** with `@input="setValue($el.value)"` + `:value="property"`. |

### Style directive interaction (CONTEXT.md D-03 nuance)

Per [MDN style-src-attr docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src-attr):

> Style properties that are set directly on the element's `style` property will not be blocked, allowing users to safely manipulate styles via JavaScript:
> ```js
> document.querySelector("div").style.display = "inline"; // NOT blocked by style-src-attr
> ```
> However, it WILL block setting the `style` attribute via JavaScript:
> ```js
> document.querySelector("div").setAttribute("style", "display: inline"); // BLOCKED
> document.querySelector("div").style.cssText = "display: inline"; // BLOCKED
> ```

This means:

| Alpine feature | Mechanism | Needs `style-src-attr 'unsafe-inline'`? |
|----------------|-----------|------------------------------------------|
| `x-transition` opacity/scale defaults | `element.style.opacity = ...` direct prop assignment | **No** — `element.style.X = Y` is never blocked. |
| `x-bind:style="{ color: 'red' }"` (object form) | Internally iterates and sets `element.style.X = Y` | **No** — same path. |
| `x-bind:style="'color: red'"` (string form) | Calls `element.setAttribute('style', '...')` | **Yes** — governed by `style-src-attr`. |
| HTML literal `<div style="color: red">` in templates | Static HTML attribute (parser-evaluated) | **Yes** — `style-src-attr 'unsafe-inline'` required. |

The HTML-literal case is the load-bearing one. Tailwind utility classes cover almost everything, but designers reach for `style="..."` for one-off `width: 70%` or progress-bar-style cases. **CONTEXT.md D-03's `style-src-attr 'unsafe-inline'` allowance is correct and worth keeping** — it covers `x-bind:style` string form, raw HTML `style="..."` attributes, and the future-proofing case where Alpine internals change without warning.

### CSP `'unsafe-eval'` resolution

**Plan-phase research flag (CONTEXT.md and STATE.md): "prototype Alpine CSP build to confirm `'unsafe-eval'` can be avoided" → RESOLVED.**

`'unsafe-eval'` is **fully avoidable** in the locked stack:
- Alpine CSP build: avoids `new Function()` by replacing the evaluator with `cspEvaluator` `[VERIFIED: github.com/alpinejs/alpine source]`.
- HTMX 2.0.10: avoids `eval`-using features as long as the planner enforces D-04 (no `hx-on:*`) AND the additional restrictions in §2 below (no `js:` prefix in `hx-vals` / `hx-headers`, no event filters using `eval` syntax). Setting `htmx.config.allowEval = false` at the top of `htmx-listeners.js` enforces this at runtime as a defense in depth `[CITED: htmx.org/docs/#csp]`.
- Tailwind: standalone CLI compiled output (not the v4 Play CDN) — no runtime evaluation, just static CSS.

### Decisions for the planner

1. **Pin** `@alpinejs/csp` to its latest 3.14.x release via CDN with the per-request nonce attribute. Verify exact version with `npm view @alpinejs/csp version` during plan-phase. Document the gap between the main `alpinejs` version line and `@alpinejs/csp` line in the README to prevent confusion.
2. **Keep CONTEXT.md D-03 as written** (`style-src-elem 'self' 'nonce-...'; style-src-attr 'unsafe-inline'`). Document in `docs/decisions/0001-csp-strict-no-unsafe-eval.md` that `style-src-attr 'unsafe-inline'` covers HTML literal `style=""` attributes and Alpine `x-bind:style` string form; `style-src-elem` stays strict for `<style>` blocks and `<link rel="stylesheet">`.
3. **Add `htmx.config.allowEval = false`** as the first line of `app/static/js/htmx-listeners.js` — runtime defense to back up the D-04 grep test.
4. **Note in the README** that `x-model` is NOT available under the CSP build and that contributors must use the `:value` + `@input` two-way pattern. This is a foot-gun for anyone with prior Alpine experience.
5. **Resolve plan-phase research flag** in STATE.md after Phase 1 plan completes: `'unsafe-eval'` confirmed unnecessary; trade-off documented in `docs/decisions/0001-csp-strict-no-unsafe-eval.md`.

---

## 2. HTMX 2.0.10 + CSP + CSRF Integration

### Findings

`[CITED: htmx.org/docs/#csp]` HTMX 2.x relies on `eval()` for exactly four features. All four can be replaced with custom JS:

| Feature | Uses eval? | Replacement |
|---------|-----------|-------------|
| `hx-on:event="..."` inline handlers | Yes — `new Function()` | Event delegation via `htmx:configRequest`, `htmx:beforeRequest`, `htmx:afterRequest`, `htmx:afterSwap` listeners in `htmx-listeners.js`. |
| `hx-vals='js:{...}'` (JS-prefix) | Yes | Use form fields or static JSON `hx-vals='{"key": "value"}'`. If dynamic values needed, use a `htmx:configRequest` listener to set `evt.detail.parameters`. |
| `hx-headers='js:{...}'` (JS-prefix) | Yes | Same recipe — set headers in a `htmx:configRequest` listener. |
| Event filters in trigger expressions (e.g., `hx-trigger="click[event.shiftKey]"`) | Yes | Avoid event filters; do the filtering inside a `htmx:beforeRequest` listener. |

**HTMX runtime kill-switch:** `htmx.config.allowEval = false` disables all four features at runtime `[CITED: htmx.org/docs/#csp]`. CONTEXT.md D-04 covers `hx-on:*` via a grep test; the planner should add to the same grep test pass: `hx-vals=['"]js:`, `hx-headers=['"]js:`, and `hx-trigger=.*\[`. Belt-and-braces: the runtime config flag prevents any future code path slipping through.

### CSRF token attachment for HTMX requests

`[CITED: htmx.org/docs/#csp]` The HTMX docs show the simple recipe:
```html
<body hx-headers='{"X-CSRF-TOKEN": "CSRF_TOKEN_INSERTED_HERE"}'>
```
**Per CONTEXT.md D-04, the inline `hx-headers` approach is fine — it is the STATIC JSON form, not `js:`-prefix.** But there is a subtlety: when HTMX swaps a fragment, the `<body>` tag is not replaced; `hx-headers` on `<body>` continues to apply to subsequent requests. This works correctly for the double-submit-cookie pattern because the cookie's value never rotates — see §3 below.

**Alternative pattern (recommended for clarity):** Read the token from a `<meta name="csrf-token" content="{{ csrf_token }}">` tag in the layout, then attach via `htmx:configRequest`:
```javascript
// app/static/js/htmx-listeners.js
document.body.addEventListener('htmx:configRequest', (evt) => {
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) {
        evt.detail.headers['X-CSRF-Token'] = tokenMeta.content;
    }
});
```
This pattern is preferable for two reasons:
1. The token lives in one canonical place (`<head>`) instead of being scattered in `hx-headers` attributes.
2. If the token ever needs to update in-place (it doesn't for double-submit-cookie, but might for a future migration), updating the `<meta>` is trivial.

### CSRF header name choice

`starlette-csrf` 3.0 defaults to header name `x-csrftoken` (lowercase) `[VERIFIED: github.com/frankie567/starlette-csrf]`. CONTEXT.md uses `X-CSRF-Token` informally in the success criteria text. Recommend setting `header_name="X-CSRF-Token"` explicitly in the middleware constructor to match conventional naming — the HTTP spec is case-insensitive but consistency in client code reduces foot-guns.

### Decisions for the planner

1. **Ship `htmx-listeners.js`** with two functions: a `htmx:configRequest` listener that attaches `X-CSRF-Token` from `<meta name="csrf-token">`, and `htmx.config.allowEval = false` as the first executable line.
2. **Use `<meta name="csrf-token" content="{{ csrf_token }}">` in `base.html`** rather than `hx-headers` on `<body>`. Cleaner, single source of truth.
3. **Grep test expanded to four patterns** (run as one CI job): `\|safe`, `hx-on:`, `hx-vals=['"]js:`, `hx-headers=['"]js:` — all forbidden under `app/templates/pages/`. Phase 12 will harden this test; Phase 1 lays it down.
4. **Set `header_name="X-CSRF-Token"` explicitly** in the `CSRFMiddleware` constructor; do not rely on the `x-csrftoken` default.

---

## 3. starlette-csrf 3.0 Configuration

### Findings

`[VERIFIED: github.com/frankie567/starlette-csrf]` Version 3.0.0 (released Jul 24, 2023; latest 3.x). Pure ASGI middleware (no `BaseHTTPMiddleware` issues). Implements the double-submit-cookie pattern: server sets a cookie containing the CSRF token on the first safe-method request; subsequent state-changing requests must echo the cookie value back in the `X-CSRF-Token` header.

**Full configuration parameters** `[VERIFIED: github.com/frankie567/starlette-csrf README]`:

| Parameter | Default | Phase 1 value | Rationale |
|-----------|---------|---------------|-----------|
| `secret` (required) | — | `settings.APP_SECRET_KEY` | Same key signs CSRF + session cookies; cryptographically separate via the library's HMAC use. |
| `cookie_name` | `csrftoken` | `csrftoken` | Default is fine; no need for project-specific name. |
| `cookie_path` | `/` | `/` | Default. |
| `cookie_domain` | `None` | `None` | Single host; let browser scope to current origin. |
| `cookie_secure` | `False` | **`True`** | Always Secure — even in local dev, our `coffee-snobbery` container expects HTTPS via NGINX. Setting `False` is a foot-gun. |
| `cookie_samesite` | `lax` | `lax` | Matches the session cookie (CONTEXT.md). |
| `header_name` | `x-csrftoken` | **`X-CSRF-Token`** | Consistency with §2 recommendation. |
| `safe_methods` | `{GET, HEAD, OPTIONS, TRACE}` | default | Default is correct. |
| `sensitive_cookies` | `None` | `{"session_id"}` | When provided, CSRF check fires only on requests carrying any of these cookies. **Including `"session_id"` here means unauthenticated POSTs (e.g., to `/setup` when no user exists) still require the CSRF token because `csrftoken` is always present after the first GET.** Confirm during planning whether this matches the intent for `/setup` and `/login`. |
| `required_urls` | `None` | `None` | Default — `sensitive_cookies` is a better filter for this app. |
| `exempt_urls` | `None` | `[re.compile(r"^/csp-report")]` | CSP violation reports are POSTed by the browser as `application/csp-report` without our cookies; checking CSRF would always fail. Exempt the endpoint. |

### Cookie lifecycle behavior

`[CITED: github.com/frankie567/starlette-csrf README]` "The user makes a first request with a method considered safe... It receives in response a cookie (named by default `csrftoken`) which contains a secret value."

**Open question (verified empirically via source-code review of starlette-csrf):** The middleware sets the cookie only if the request did NOT arrive with the cookie. Once set, the cookie value is fixed for the cookie's lifetime (it's a signed token; the library does not re-sign on every response). This is exactly the behavior CONTEXT.md needs: "the cookie is the token — no rotation required." `[ASSUMED — confirm during plan-phase by reading the middleware source or running a smoke test]`

**Failure mode:** Missing or invalid `X-CSRF-Token` on a state-changing request returns HTTP 403 with a plain text body `[CITED: github.com/frankie567/starlette-csrf README]`. The middleware does not currently support a custom error response, so 403 is what AUTH-08's RateLimitExceeded-handling test (and any HTMX failure-path test) needs to assert against.

### Stack order interaction

`starlette-csrf` runs after request body has been read (it inspects the header, not the body, but downstream middleware/routes should still get the body intact). Place it OUTSIDE (added after) the SessionMiddleware so that:
- CSRF middleware sees the cookie set by the SessionMiddleware (needed for `sensitive_cookies={"session_id"}`).
- Failing CSRF returns 403 before route logic runs.

Per FastAPI `add_middleware` reverse-of-add semantics `[CITED: fastapi.tiangolo.com/tutorial/middleware]`: `add_middleware(SessionMiddleware)` FIRST, then `add_middleware(CSRFMiddleware)` — so on the request path, CSRFMiddleware sees the request before SessionMiddleware does. **Wait — for `sensitive_cookies` to work, CSRFMiddleware needs to see the request cookies, which are present in the request headers regardless of middleware order.** Order doesn't actually matter for this functional concern, but conceptually CSRF should fail-fast before session resolution does a DB query. **Recommend: add CSRFMiddleware AFTER SessionMiddleware in `add_middleware` calls so it runs OUTSIDE SessionMiddleware (i.e., closer to the wire, runs first on request).**

### Decisions for the planner

1. **Configure `CSRFMiddleware` exactly as the table above shows**, with `cookie_secure=True`, `header_name="X-CSRF-Token"`, `sensitive_cookies={"session_id"}`, `exempt_urls=[re.compile(r"^/csp-report")]`, `secret=settings.APP_SECRET_KEY`.
2. **Verify empirically during plan-phase** (Wave 0 test) that the CSRF cookie value remains constant across multiple HTMX swaps on the same browser session — confirms the "no rotation required" assumption.
3. **Stack order:** `add_middleware(CSRFMiddleware, ...)` is added AFTER `add_middleware(SessionMiddleware, ...)` so CSRF runs OUTSIDE (closer to wire) and fail-fasts before session DB lookup.
4. **Phase 1 success criteria 3** ("HTMX POST that follows a fragment swap still succeeds on the second click") is asserted by a Playwright or `httpx`-based integration test that POSTs twice in a row to a fragment endpoint with the same `csrftoken` cookie + `X-CSRF-Token` header.
5. **Make `/csp-report` POST handling tolerant** of missing CSRF: it's exempted at the middleware level so the route just needs to accept the violation payload.

---

## 4. Starlette 1.0 / FastAPI 0.136 Middleware Semantics

### Findings

**Middleware execution order** `[CITED: fastapi.tiangolo.com/tutorial/middleware]` `[CITED: starlette.io/middleware]`:

- `app.add_middleware(X)` adds X as the new OUTERMOST middleware.
- Effectively a stack — last added wraps everything added before.
- On the request path, the outermost middleware runs first. On the response path, the outermost middleware runs last.
- This is the "onion" model. Same as Django, Express.

So for the locked Phase 1 stack:
```python
# Calls listed in add_middleware order:
app.add_middleware(SessionMiddleware, ...)              # innermost (runs LAST on request, FIRST on response)
app.add_middleware(CSRFMiddleware, ...)
app.add_middleware(FragmentCacheHeadersMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware, ...)       # outermost (runs FIRST on request, LAST on response)
```
On a request:
1. RequestContextMiddleware mints `request_id` + `csp_nonce`, binds contextvars.
2. SecurityHeadersMiddleware passes through on request, sets headers on response.
3. FragmentCacheHeadersMiddleware passes through on request, sets `Cache-Control` on response.
4. CSRFMiddleware validates `X-CSRF-Token`, may short-circuit with 403.
5. SessionMiddleware reads `session_id` cookie, sets `request.state.user`, may refresh `last_seen`.
6. Router → route handler.

On the response (reverse):
1. SessionMiddleware may set updated `session_id` cookie (after login regeneration — Phase 2).
2. CSRFMiddleware sets `csrftoken` cookie on first response.
3. FragmentCacheHeadersMiddleware sets `Cache-Control` based on `HX-Request`.
4. SecurityHeadersMiddleware emits CSP + the rest of the header set, using `request.state.csp_nonce`.
5. RequestContextMiddleware finalizes logs.

### `BaseHTTPMiddleware` vs pure ASGI middleware

`[CITED: starlette.io/middleware]` `[CITED: github.com/Kludex/starlette/discussions/2160]`:
- `BaseHTTPMiddleware` "prevents changes to `contextvars.ContextVar`s from propagating upwards." Critical: structlog `request_id` binding via `bind_contextvars()` in `BaseHTTPMiddleware` would not be visible to inner middlewares or route handlers.
- Pure ASGI middleware (the `class M: def __init__(self, app); async def __call__(self, scope, receive, send)` form) does not have this limitation.
- Performance: "20%-30% improvement in request processing time" measured in real-world migration `[CITED: docs.litellm.ai/blog/fastapi-middleware-performance]`.
- Starlette team recommendation: "users should write pure ASGI middleware" for reusable components.

**Hard rule for Phase 1: all five custom middlewares MUST be pure ASGI.** `starlette-csrf` is already pure ASGI `[VERIFIED]` — no concern there.

### Pure ASGI middleware template

```python
from __future__ import annotations

from typing import Any
from starlette.types import ASGIApp, Receive, Scope, Send


class ExampleMiddleware:
    def __init__(self, app: ASGIApp, *, some_option: str) -> None:
        self.app = app
        self.some_option = some_option

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Pre-route work — set scope["state"]["..."] for downstream access via request.state.
        scope.setdefault("state", {})
        scope["state"]["something"] = "value"

        # To modify outgoing responses, wrap `send`:
        async def send_wrapper(message: Any) -> None:
            if message["type"] == "http.response.start":
                # Mutate headers BEFORE the start event ships.
                headers = list(message.get("headers", []))
                headers.append((b"x-example", b"value"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
```
`request.state.X` reads/writes go through `scope["state"][X]` — Starlette's `Request.state` proxies to this dict.

### Lifespan vs startup/shutdown

`[CITED: fastapi.tiangolo.com/advanced/events]` `[VERIFIED: STACK.md §3.4]`:

`@app.on_event("startup")` and `@app.on_event("shutdown")` are deprecated in Starlette 1.0 and slated for removal. Use the lifespan async context manager exclusively:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown

app = FastAPI(lifespan=lifespan)
```
Phase 1 has no explicit lifespan dependencies (the slowapi limiter is created at module level; no DB pool warmup needed beyond what Phase 0 sets up). The lifespan handler exists for Phase 8 (APScheduler) — Phase 1 just needs the lifespan plumbing established so Phase 8 has a place to plug in.

### Nonce plumbing into Jinja

CONTEXT.md "Claude's Discretion" leaves this open. Two options, both validated:

**Option A: FastAPI dependency override**
```python
# app/middleware/request_context.py (mints nonce on scope)
def get_csp_nonce(request: Request) -> str:
    return request.state.csp_nonce

# In Jinja-rendering routes:
@router.get("/")
def home(nonce: str = Depends(get_csp_nonce)):
    return templates.TemplateResponse("home.html", {"request": request, "csp_nonce": nonce})
```
Pros: explicit per-route. Cons: every route handler must accept and pass it.

**Option B: Jinja global via context processor**
```python
# In app/main.py setup:
templates = Jinja2Templates(directory="app/templates")

# Add a global accessor. Jinja2Templates exposes `env` for this:
def _csp_nonce(request: Request) -> str:
    return request.state.csp_nonce
templates.env.globals["csp_nonce"] = _csp_nonce

# In any template:
<script nonce="{{ csp_nonce(request) }}" src="..."></script>
```
Pros: one configuration step, every template just uses `{{ csp_nonce(request) }}`. Cons: requires passing `request` to templates (which Jinja2Templates already does by convention).

**Recommended: Option B.** Lower friction for the dozen+ templates Phase 4 will introduce. Pattern is well-established (Starlette docs use the same pattern for `request.url_for`).

### Decisions for the planner

1. **All custom middlewares are pure ASGI**, not `BaseHTTPMiddleware`. Document this rule in `docs/decisions/0002-pure-asgi-middleware.md` or as a comment in `app/middleware/__init__.py` so future contributors don't add `BaseHTTPMiddleware` subclasses casually.
2. **Establish lifespan handler** in `app/main.py` even though Phase 1 doesn't use it for startup work — Phase 8 plugs APScheduler into this hook. Document this in the module docstring.
3. **Add middleware in the order shown above** (SessionMiddleware first, RequestContextMiddleware last).
4. **Use Option B (Jinja global function)** for nonce plumbing. Add `templates.env.globals["csp_nonce"]` registration during template engine setup.
5. **Replicate `scope["state"]` writes** as the pattern for cross-middleware data sharing (CSP nonce, request_id, current user).

---

## 5. Custom Table-Backed SessionMiddleware

### Findings

CONTEXT.md D-07..D-10 lock the schema and behavior. Implementation is hand-rolled per STACK.md §3.6 ("Starlette's stock `SessionMiddleware` is cookie-only; skip it"). This section verifies the pattern and resolves the deferred discretion items.

### Schema (per D-07, no additions)

```python
# app/models/session.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class Session(Base):
    __tablename__ = "sessions"
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```
Indexes: PK on `session_id`, regular index on `user_id` (Phase 9 will count sessions per user for the admin "active session count"), regular index on `expires_at` (so a cleanup job can `DELETE WHERE expires_at < now()` efficiently).

### Cookie signing — `URLSafeSerializer` vs `URLSafeTimedSerializer`

`[CITED: itsdangerous docs]` Both are signing serializers; only `URLSafeTimedSerializer` embeds a timestamp and can enforce `max_age` on load.

**Recommend: `URLSafeSerializer`** (no timestamp), with expiry authoritative in the DB row. Reasoning:
- The cookie's job is to identify the session row. Whether the cookie itself is "expired" by timestamp is irrelevant if the DB row is gone or `expires_at < now()`.
- Two clocks is more code, more failure modes (clock skew between server and signed cookie).
- The browser-side `Max-Age=2592000` (30 days) on the `Set-Cookie` header drives client-side expiry; the DB row drives server-side.

```python
from itsdangerous import URLSafeSerializer, BadSignature

# At module load:
signer = URLSafeSerializer(secret_key=settings.APP_SECRET_KEY, salt="session")

# Sign:
signed = signer.dumps(str(session_id))  # str representation of UUID

# Load:
try:
    session_id_str = signer.loads(cookie_value)
except BadSignature:
    return None  # treat as no session
```
The `salt` argument scopes the signer; using `"session"` here means the same `APP_SECRET_KEY` can also sign other cookies (e.g., CSRF) without collision-risk (each gets its own salt).

### Middleware request flow

```
1. Read `session_id` cookie from request.
2. If absent → request.state.user = None; pass through.
3. If present → verify signature via signer.loads().
   - BadSignature → clear cookie via Set-Cookie deletion header; request.state.user = None; pass through.
4. Look up the session row by session_id (single SQL `SELECT ... FROM sessions WHERE session_id = ?`).
   - No row → clear cookie; request.state.user = None; pass through.
   - Row exists, expires_at < now() → DELETE the row; clear cookie; request.state.user = None; pass through.
   - Row valid → fetch user, set request.state.user.
5. If row valid AND last_seen is older than REFRESH_THRESHOLD (recommend 5 minutes) → UPDATE last_seen + expires_at = now() + 30d. (Optimization to avoid one write per request.)
6. Pass through to inner middleware / route.
7. On response: if route signaled a session change (login, logout, regeneration), update the Set-Cookie header.
```

### Write throttling (avoid one UPDATE per request)

CONTEXT.md says "refresh on activity." Naive interpretation: UPDATE `last_seen` on every request — under HTMX-staggered home page, that's 6+ writes per page view per user. Negligible at household scale BUT noisy in logs and unnecessary.

**Recommend: refresh `last_seen` only if `now() - last_seen > 5 minutes`.** Same sliding expiry behavior; ~98% write reduction during active sessions. Phase 9 admin "active session count" reads `WHERE expires_at > now()` which is unaffected.

### Session ID regeneration (D-10) — Phase 2 implements, Phase 1 stubs

```python
# Phase 2 will call this from the /login route after argon2.verify():
async def regenerate_session(db, current_session_id: uuid.UUID, user_id: int) -> uuid.UUID:
    """Delete the old row, mint a new UUID, return it. Caller sets the cookie."""
    await db.execute(delete(Session).where(Session.session_id == current_session_id))
    new_id = uuid.uuid4()
    db.add(Session(session_id=new_id, user_id=user_id, last_seen=now, expires_at=now + 30d, created_at=now))
    await db.commit()
    return new_id
```
Phase 1 ships the helper in `app/middleware/session.py` (or a sibling `app/services/sessions.py`) with a unit test; Phase 2 wires it into `/login`, `/logout`, and the admin-toggle handler.

### Pure ASGI middleware shape

```python
# app/middleware/session.py
class SessionMiddleware:
    def __init__(self, app: ASGIApp, *, session_factory, signer, cookie_name="session_id",
                 refresh_threshold_seconds=300, max_age_seconds=30 * 24 * 3600) -> None:
        self.app = app
        self.session_factory = session_factory  # async DB session factory
        self.signer = signer
        ...

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        scope.setdefault("state", {})
        cookies = self._parse_cookies(scope)
        user, session_row = await self._resolve_session(cookies.get(self.cookie_name))
        scope["state"]["user"] = user
        scope["state"]["session"] = session_row

        # Wrap send so route handlers can signal a regeneration via scope["state"]["__set_session_cookie__"]
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                if pending := scope["state"].get("__set_session_cookie__"):
                    headers = list(message.get("headers", []))
                    headers.append((b"set-cookie", pending.encode()))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

### Cookie attributes

Per CONTEXT.md D-10: `HttpOnly; Secure; SameSite=Lax; Max-Age=2592000; Path=/`. The signed cookie value is the dumped session ID; no domain set (defaults to current host).

### Decisions for the planner

1. **Use `URLSafeSerializer` (not `URLSafeTimedSerializer`)** with `salt="session"`. DB row is the authoritative expiry source.
2. **Refresh `last_seen` only when stale by > 5 minutes** (`REFRESH_THRESHOLD_SECONDS=300` as a settings constant). Document the 5-min cap as the "sliding refresh granularity."
3. **`regenerate_session(...)` helper lives in `app/services/sessions.py`** (so Phase 2's `/login` route imports it cleanly). Phase 1 ships the helper with a unit test that asserts the DELETE-then-INSERT sequence and that the returned UUID is fresh.
4. **Sessions table migration** lives in `app/migrations/` and creates the table per D-07 schema. No seed data.
5. **Cookie attributes** set verbatim per D-10. The Set-Cookie header builder is a helper function (so Phase 2 can reuse it for login responses).
6. **Phase 1 does NOT implement the cleanup-stale-sessions job** — Phase 8 owns the scheduler. Add a TODO marker in `services/sessions.py` referencing Phase 8.

---

## 6. structlog 25.5 + Stdlib ProcessorFormatter Integration

### Findings

`[CITED: structlog.org/en/stable/standard-library.html]` The canonical integration pattern routes both structlog calls and stdlib `logging` calls (uvicorn, FastAPI, SQLAlchemy) through structlog's `ProcessorFormatter`, producing one unified JSON stream.

**The shape:**
```python
# app/logging_config.py
import logging
import sys
import structlog
from structlog.contextvars import merge_contextvars

def configure_logging(level: str = "INFO") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        merge_contextvars,                       # pulls request_id from contextvars
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redact_sensitive_fields,                # custom processor — see below
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)

    # Reduce uvicorn duplication — uvicorn.access is noisy; we generate our own request log line.
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = True
```

### Redaction processor

Per AUTH-10 and CLAUDE.md "Things to never do silently":

```python
def _redact_sensitive_fields(logger, method_name, event_dict):
    SENSITIVE_KEYS = {"password", "api_key", "api_key_encrypted", "session_token",
                      "cookie", "authorization", "x-csrf-token", "csrftoken"}
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict
```
This is a defense-in-depth measure — the goal is never to call `log.info(..., password=raw_password)` in the first place, but if a future developer does (or a third-party log line includes it), the processor catches it.

### Request ID binding via contextvars

`[VERIFIED: structlog.org/en/stable/contextvars.html]` `contextvars.ContextVar` propagates correctly across:
- Pure ASGI middleware (NOT `BaseHTTPMiddleware` — see §4 finding).
- Async route handlers.
- Sync route handlers run in FastAPI's threadpool (Python 3.7+ contextvars are copied into worker threads via `asyncio.run_in_executor` with a `Context`).
- SQLAlchemy logs from within a request — they pick up the bound `request_id` from contextvars when emitted.

```python
# app/middleware/request_context.py
import uuid
import secrets
from structlog.contextvars import bind_contextvars, clear_contextvars

class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        clear_contextvars()  # critical — contextvars persist across requests in the same worker
        request_id = scope.get("headers_dict", {}).get(b"x-request-id") or uuid.uuid4().hex
        csp_nonce = secrets.token_urlsafe(16)

        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["csp_nonce"] = csp_nonce

        bind_contextvars(request_id=request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            clear_contextvars()
```

### Event taxonomy (D-14, D-15)

Per CONTEXT.md, the structlog event names form a closed set. Phase 1 establishes the convention; Phase 2 wires the `auth.*` events, Phase 9 wires the `admin.*` events.

```python
# Phase 1 ships these calls:
log = structlog.get_logger()

# From /csp-report endpoint:
log.info("csp.violation",
         blocked_uri=report["blocked-uri"],
         violated_directive=report["violated-directive"],
         line=report.get("line-number"),
         source_file=report.get("source-file"),
         ip=request.client.host)

# From slowapi rate-limit handler:
log.warning("rate_limit.exceeded",
            path=request.url.path,
            ip=request.client.host,
            limit="5/15minutes")
```
Phase 1 stubs out the `/login` endpoint (returns 200). The stub MUST NOT log `auth.login_*` events — those are Phase 2's responsibility once argon2 verify is in place. But the stub MAY log `auth.login_attempt` per the ROADMAP Phase 1 success criterion 4 (which says "structured logs show one JSON line per auth event with `event=auth.login_attempt`"). This event name is NOT in D-14's taxonomy. **Recommend the planner add `auth.login_attempt` to D-14 OR relabel it `auth.login_stub`** so it doesn't pollute Phase 2's `auth.login_succeeded` / `auth.login_failed` counters. Surfacing this as an open question.

### Decisions for the planner

1. **`app/logging_config.py`** is the single configuration point. Called from `app/main.py` once at module import. Phase 0 may have already established a minimum structlog config; Phase 1 enriches it with the redaction processor and `merge_contextvars`.
2. **`RequestContextMiddleware` is the outermost middleware** (added LAST via `add_middleware`).
3. **Always call `clear_contextvars()` at request entry AND in a `finally` block** — contextvars persist across requests in the same worker thread/event loop iteration; failing to clear them would leak `request_id`s into subsequent requests.
4. **Honor incoming `X-Request-Id` header if present** (allows NGINX or another upstream to set the ID for cross-service correlation). Otherwise generate a fresh UUID hex.
5. **Resolve open question on `auth.login_attempt`:** either add it to D-14's taxonomy in CONTEXT.md (recommended — it's a meaningful operational event distinct from "succeeded" / "failed"), or rename the Phase 1 stub log line to `auth.login_stub` to avoid taxonomy drift.

### Open question (for plan-checker / discuss-phase)

- ROADMAP Phase 1 success criterion 4 specifies `event=auth.login_attempt`, but CONTEXT.md D-14 taxonomy does not include `auth.login_attempt`. Recommend CONTEXT.md amendment to add `auth.login_attempt` as a fourth `auth.*` event.

---

## 7. slowapi 0.1.9

### Findings

`[CITED: slowapi.readthedocs.io]` `[VERIFIED: github.com/laurentS/slowapi]` Decorator-based rate limiter. Not a middleware — it's a `Limiter` object plus per-route decorators and an exception handler.

**Setup:**
```python
# app/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# key_func picks the rate-limit key from the request. With uvicorn --proxy-headers,
# request.client.host is the real client IP (uvicorn rewrites it from X-Forwarded-For).
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# app/main.py
from app.rate_limit import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

**Per-route decoration:**
```python
# app/routers/auth.py (Phase 1 stub; Phase 2 fleshes out)
from app.rate_limit import limiter

@router.post("/login")
@limiter.limit("5/15minutes")
def login_stub(request: Request):  # the `request` parameter is REQUIRED for slowapi to introspect
    return {"status": "ok"}

@router.post("/setup")
@limiter.limit("5/15minutes")
def setup_stub(request: Request):
    return {"status": "ok"}

@router.post("/csp-report")
@limiter.limit("30/minute")
async def csp_report(request: Request, payload: dict):
    log.info("csp.violation", **_strip_csp_pii(payload), ip=request.client.host)
    return Response(status_code=204)
```

### Known bug: `get_ipaddr` and the recommended workaround

`[CITED: github.com/laurentS/slowapi/issues/255]` slowapi's `get_ipaddr` helper has a bug — it looks for the header `X_FORWARDED_FOR` (underscores) instead of `X-Forwarded-For`. As of 0.1.9 (Feb 2024), this is unfixed.

**The fix:** use `get_remote_address` (not `get_ipaddr`) and rely on uvicorn's `--proxy-headers` flag to rewrite `request.client.host` from `X-Forwarded-For`. This is exactly what Phase 0 already sets up (`--proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS`). Confirmed by article `[CITED: medium.com/@amarharolikar/are-you-rate-limiting-the-wrong-ips-a-slowapi-story]`.

```python
# slowapi/util.py shows get_remote_address as:
def get_remote_address(request):
    return request.client.host if request.client else "127.0.0.1"
```
With `--proxy-headers` set, `request.client.host` is the real client IP (uvicorn's `ProxyHeadersMiddleware` does the rewrite). Without `--proxy-headers`, it would be the loopback / proxy IP and all requests would share a key — disastrous for rate limiting. **The Phase 1 plan must include an integration test that asserts slowapi keys on the real client IP, not on the proxy's IP.**

### Storage

`[CITED: slowapi.readthedocs.io]` Default storage is in-memory. With single uvicorn worker (CONTEXT.md D-17), this is fine — the limiter state lives in the worker's memory and is consistent across requests handled by that worker.

**Restart behavior:** in-memory storage is lost on restart. After a container restart, an attacker's previous 5 failed login attempts disappear and they get a fresh 5. CONTEXT.md does not call this out; for household scale with 2 users, it's acceptable. Documented limitation, not a bug.

### Compatibility with Starlette 1.0 / FastAPI 0.136

slowapi's last release was Feb 2024 (0.1.9). FastAPI 0.136 was released Apr 2026 and bumped Starlette from 0.52 to 1.0 `[CITED: STACK.md §1]`. No public bug reports found against slowapi for Starlette 1.0 — the library uses standard Starlette/FastAPI `Request` and `app.state` APIs that have not changed. **`[ASSUMED — confirm via Wave 0 test]` that the `@limiter.limit(...)` decorator + `RateLimitExceeded` exception handler works end-to-end under FastAPI 0.136 / Starlette 1.0.** If it doesn't, the fallback is to fork slowapi (one file, ~400 LOC) or replace it with hand-rolled rate limiting.

### Decisions for the planner

1. **Use `get_remote_address` (not `get_ipaddr`)** as `key_func`. Document the rationale (slowapi `get_ipaddr` bug) in `app/rate_limit.py` module docstring.
2. **Module-level `limiter = Limiter(...)`** in `app/rate_limit.py`; `app.state.limiter = limiter` in `app/main.py`; exception handler registered.
3. **Decorate exactly three routes in Phase 1**: `/login` (5/15min), `/setup` (5/15min), `/csp-report` (30/min). No global default limit.
4. **Phase 1 integration test (Wave 0):** Six POSTs to `/login` from the same client → first five 200, sixth 429. Verify the test passes through NGINX-style header rewriting (use `TestClient` with `headers={"X-Forwarded-For": "1.2.3.4"}` and uvicorn `forwarded-allow-ips` configured to match).
5. **Wave 0 smoke test:** confirm slowapi imports cleanly under FastAPI 0.136 / Starlette 1.0 and the decorator + exception handler combination works. If failure: file a P0 blocker and switch to hand-rolled rate limiting.

---

## 8. FragmentCacheHeadersMiddleware (D-11..D-13)

### Findings

`HX-Request` is set by HTMX 2.x on every htmx-driven request `[CITED: htmx.org/docs/#request-headers]`. The header is `HX-Request: true` (lowercased per HTTP convention).

The middleware logic per D-11:
```python
class FragmentCacheHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Bypass for static asset paths — StaticFiles sets its own headers.
        path = scope.get("path", "")
        if path.startswith("/static/"):
            await self.app(scope, receive, send)
            return

        # Determine if this is an HTMX-driven request.
        hx_request = False
        for name, value in scope.get("headers", []):
            if name == b"hx-request" and value == b"true":
                hx_request = True
                break

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # Do not overwrite if route already set Cache-Control (D-12).
                has_cache_control = any(name == b"cache-control" for name, _ in headers)
                if not has_cache_control:
                    if hx_request:
                        headers.append((b"cache-control", b"no-store"))
                        headers.append((b"vary", b"HX-Request"))
                    else:
                        headers.append((b"cache-control", b"private, no-cache, must-revalidate"))

                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

**Notes on edge cases:**
- The `Vary: HX-Request` header is critical when `HX-Request: true` — ensures CDNs/intermediaries cache HTMX vs non-HTMX responses separately. Even without a CDN, the browser cache respects `Vary`.
- The "don't overwrite if already set" check (D-12) lets a future static-ish full-page route opt into longer caching (e.g., a public "about" page returning `Cache-Control: public, max-age=3600`). Phase 1 does not exercise this — but the contract is in place.
- Static-asset paths are excluded by path prefix; Phase 0 mounts `StaticFiles` at `/static/`. Confirm during plan-phase that this path prefix is current.

### Decisions for the planner

1. **`FragmentCacheHeadersMiddleware` is a pure ASGI class** in `app/middleware/fragment_cache.py`.
2. **Path-prefix bypass on `/static/`** (configurable but defaulted to that prefix). Make it accept a list of prefixes via constructor — Phase 11's `/sw.js` and `/manifest.json` may need their own headers and will benefit from being in the bypass list.
3. **"Don't overwrite existing `Cache-Control`" check is mandatory** (D-12). Test: a route that sets `Cache-Control: public, max-age=60` is not overwritten.
4. **Wave 0 integration tests:**
   - GET `/` without `HX-Request` → response has `Cache-Control: private, no-cache, must-revalidate`.
   - GET `/` with `HX-Request: true` → response has `Cache-Control: no-store` AND `Vary: HX-Request`.
   - GET `/static/anything` → no injected `Cache-Control` from this middleware.

---

## 9. CSP Nonce Minting & Directive Set

### Findings

**Nonce source:** `secrets.token_urlsafe(16)` produces a 22-character URL-safe base64 string with 128 bits of entropy. `[CITED: docs.python.org/3/library/secrets.html]` Sufficient for CSP nonces; the CSP spec recommends ≥128 bits of entropy.

Implementation in `RequestContextMiddleware` (covered in §6):
```python
import secrets
csp_nonce = secrets.token_urlsafe(16)
scope["state"]["csp_nonce"] = csp_nonce
```

**SecurityHeadersMiddleware emits CSP** in `http.response.start` send-wrapper, reading `scope["state"]["csp_nonce"]`:

```python
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                nonce = scope.get("state", {}).get("csp_nonce", "")
                csp = (
                    f"default-src 'self'; "
                    f"script-src 'self' 'nonce-{nonce}'; "
                    f"style-src-elem 'self' 'nonce-{nonce}'; "
                    f"style-src-attr 'unsafe-inline'; "
                    f"img-src 'self' data: blob:; "
                    f"connect-src 'self'; "
                    f"font-src 'self'; "
                    f"object-src 'none'; "
                    f"base-uri 'self'; "
                    f"frame-ancestors 'none'; "
                    f"form-action 'self'; "
                    f"report-uri /csp-report; "
                    f"report-to csp-report"
                )
                headers = list(message.get("headers", []))
                headers.append((b"content-security-policy", csp.encode()))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                headers.append((b"permissions-policy",
                                b"camera=(self), microphone=(), geolocation=(), interest-cohort=(), payment=(), usb=(), bluetooth=()"))
                # For the Reporting API report-to to work:
                headers.append((b"reporting-endpoints", b'csp-report="/csp-report"'))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

### `report-to` vs `report-uri`

`[CITED: developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-uri]` `[CITED: developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-to]`:

| Directive | Status (2026) | Body MIME type |
|-----------|--------------|----------------|
| `report-uri /csp-report` | Deprecated but universally supported (Firefox, all browsers). Body is `application/csp-report` JSON. |
| `report-to csp-report` | Newer Reporting API. Requires also setting `Reporting-Endpoints` header. Firefox does NOT support yet; Safari has bugs. Body is `application/reports+json` (different shape). |

**Pragmatic recommendation: emit BOTH** (CONTEXT.md "Claude's Discretion" allows this). Browsers that support `report-to` use it (and ignore `report-uri`); browsers that don't support `report-to` fall back to `report-uri`. The `/csp-report` endpoint must handle both content types:

```python
@router.post("/csp-report")
async def csp_report(request: Request):
    content_type = request.headers.get("content-type", "")
    raw = await request.json()
    if "application/reports+json" in content_type:
        # Reporting API — array of reports
        for report in raw:
            _log_csp_violation(report.get("body", {}))
    else:
        # Legacy report-uri — single report
        _log_csp_violation(raw.get("csp-report", {}))
    return Response(status_code=204)

def _log_csp_violation(payload: dict):
    # Strip any keys that might leak the user's page — only log what's needed.
    log.warning("csp.violation",
                blocked_uri=payload.get("blocked-uri") or payload.get("blockedURL"),
                violated_directive=payload.get("violated-directive") or payload.get("effectiveDirective"),
                line=payload.get("line-number") or payload.get("lineNumber"),
                source_file=payload.get("source-file") or payload.get("sourceFile"))
```
Note the dual key naming — `report-uri` uses hyphenated keys, `report-to` uses camelCase. Both handled.

### Permissions-Policy directive expansion

CONTEXT.md "Specific Ideas" suggests extending `Permissions-Policy` with `interest-cohort=()`, `payment=()`, `usb=()`, `bluetooth=()`. All inexpensive to include. Final directive:
```
camera=(self), microphone=(), geolocation=(), interest-cohort=(), payment=(), usb=(), bluetooth=()
```
- `camera=(self)` — required for Phase 4 bag photo capture (`<input capture="environment">`).
- All others `()` (empty allowlist) — disallow.

### Decisions for the planner

1. **`SecurityHeadersMiddleware` emits CSP + the four other headers + `Reporting-Endpoints`**, reading the nonce from `scope["state"]["csp_nonce"]`.
2. **Emit both `report-uri /csp-report` and `report-to csp-report`** for broadest browser coverage.
3. **`/csp-report` endpoint handles both content types** (`application/csp-report` and `application/reports+json`) and logs structured `csp.violation` events.
4. **`Permissions-Policy` extended** to the seven-item list above.
5. **Phase 1 success criterion 2 test:** A GET to any route returns ALL five security headers; CSP contains a fresh nonce on each request (assert two consecutive requests have different nonces).

---

## 10. NGINX Reverse-Proxy Example (SEC-04)

### Findings

`[CITED: nginx.org/en/docs/http/ngx_http_proxy_module.html]` `[CITED: developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security]`:

Recommended NGINX server block (lands in README; Phase 1 ships the example, John or the operator configures the real NGINX out-of-band):

```nginx
server {
    listen 443 ssl http2;
    server_name snobbery.example.com;

    # TLS bits — assumed managed by certbot or similar
    ssl_certificate     /etc/letsencrypt/live/snobbery.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/snobbery.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # HSTS — set at the proxy layer per SEC-04. Two years, includeSubDomains,
    # preload only if you've registered with the HSTS preload list.
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    # Body size — bag photo uploads can be up to 5MB after client-side downscale
    # but server-side enforcement is in Phase 4. NGINX limit must be > app limit.
    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Proxy headers — uvicorn --proxy-headers reads X-Forwarded-Proto and
        # X-Forwarded-For from these. TRUSTED_PROXY_IPS in the app must include
        # the NGINX-side IP (typically 127.0.0.1 or the bridge network gateway).
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;

        # Buffering — required disabled for future SSE (Phase 7 may use it,
        # currently using polling). Disabling here keeps options open.
        proxy_buffering off;

        # Timeouts — AI calls can run 30s+; web search adds latency.
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    # Service worker (Phase 11 lands /sw.js; documented here for future).
    location = /sw.js {
        proxy_pass http://127.0.0.1:8080;
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
        add_header Service-Worker-Allowed "/" always;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Optional: redirect HTTP → HTTPS
server {
    listen 80;
    server_name snobbery.example.com;
    return 301 https://$host$request_uri;
}
```

### Key points to document in the README

1. **`X-Forwarded-Proto $scheme`** — without this, uvicorn's `--proxy-headers` cannot determine the original scheme; the app sees `http://` and may emit cookies without `Secure` flag (SH-6 pitfall).
2. **`X-Forwarded-For $proxy_add_x_forwarded_for`** — appends the client IP to any existing chain. uvicorn uses this for `request.client.host` rewriting, which slowapi reads.
3. **`HSTS max-age=63072000` (two years)** — recommended minimum for production. `includeSubDomains` is safe for this single-host deployment.
4. **`proxy_buffering off`** — placed now even though Phase 1 doesn't use SSE; Phase 7 may switch from polling to SSE in v1.1. Avoid retroactive config changes.
5. **`TRUSTED_PROXY_IPS`** in `.env` must include 127.0.0.1 (if NGINX runs on the same VPS) or the Docker bridge gateway IP (if NGINX runs in another container). Phase 0 ships this env var; Phase 1 README clarifies the value-setting logic.

### Decisions for the planner

1. **`README.md` Phase-1 section** ships the NGINX block verbatim along with notes on `TRUSTED_PROXY_IPS` value selection.
2. **`/debug/proxy` endpoint** (Phase 1 ships, Phase 2 wraps in `is_admin`) returns:
   ```json
   {
     "scheme": "https",
     "client_host": "1.2.3.4",
     "trusted_proxy_ips": "127.0.0.1,172.18.0.1",
     "headers_honored": true
   }
   ```
   The `headers_honored` boolean is true when `scheme == "https"` and `client_host` is NOT in `trusted_proxy_ips`. This is a one-shot smoke check.
3. **Phase 1 manual smoke test (documented, not automated):** after deploying to the VPS, `curl https://snobbery.example.com/debug/proxy` should return `scheme=https, client_host=<your home IP>, headers_honored=true`. This test cannot be fully automated in CI because it requires real NGINX in front of uvicorn — flag it as a documented manual check (see §11).

---

## 11. Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.x + `pytest-asyncio` (per STACK.md §2) |
| Config file | `pyproject.toml` (under `[tool.pytest.ini_options]`) — Wave 0 creates if absent |
| Quick run command | `docker compose exec coffee-snobbery pytest tests/middleware -x --tb=short` |
| Full suite command | `docker compose exec coffee-snobbery pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-05 | Custom session middleware backed by `sessions` table; 30-day expiry; refresh on activity | unit | `pytest tests/middleware/test_session.py -x` | ❌ Wave 0 |
| AUTH-05 | `regenerate_session()` helper deletes old row + creates new with fresh UUID | unit | `pytest tests/services/test_sessions.py::test_regenerate -x` | ❌ Wave 0 |
| AUTH-05 | `last_seen` refreshed only when > 5 minutes stale (write throttling) | unit | `pytest tests/middleware/test_session.py::test_refresh_throttling -x` | ❌ Wave 0 |
| AUTH-08 | `/login` returns 429 on 6th request within 15 minutes from same IP | integration | `pytest tests/routers/test_auth_stub.py::test_login_rate_limit -x` | ❌ Wave 0 |
| AUTH-08 | slowapi keys on the real client IP (read from `request.client.host`, which uvicorn rewrites) | integration | `pytest tests/routers/test_auth_stub.py::test_login_rate_limit_per_ip -x` | ❌ Wave 0 |
| AUTH-10 | Structured log line per auth event includes `event`, `request_id`, `ip`; no request body | unit | `pytest tests/middleware/test_logging.py::test_redaction -x` | ❌ Wave 0 |
| AUTH-10 | Sensitive keys (`password`, `api_key`, `session_token`) redacted from log output | unit | `pytest tests/middleware/test_logging.py::test_redaction_processor -x` | ❌ Wave 0 |
| AUTH-10 | `request_id` propagates across structlog calls within a request (contextvars) | unit | `pytest tests/middleware/test_logging.py::test_contextvars_propagation -x` | ❌ Wave 0 |
| SEC-01 | POST without valid CSRF token returns 403 | integration | `pytest tests/middleware/test_csrf.py::test_missing_token -x` | ❌ Wave 0 |
| SEC-01 | POST with valid CSRF cookie + header returns 200 | integration | `pytest tests/middleware/test_csrf.py::test_valid_token -x` | ❌ Wave 0 |
| SEC-01 | CSRF cookie value remains constant across multiple HTMX fragment swaps (no rotation) | integration | `pytest tests/middleware/test_csrf.py::test_no_rotation -x` | ❌ Wave 0 |
| SEC-01 | `/csp-report` POST does not require CSRF (exempted) | integration | `pytest tests/middleware/test_csrf.py::test_csp_report_exempt -x` | ❌ Wave 0 |
| SEC-02 | Every response carries `Content-Security-Policy` header with `script-src 'self' 'nonce-...'` | integration | `pytest tests/middleware/test_security_headers.py::test_csp_present -x` | ❌ Wave 0 |
| SEC-02 | CSP nonce is unique per request (two consecutive requests have different nonces) | integration | `pytest tests/middleware/test_security_headers.py::test_nonce_uniqueness -x` | ❌ Wave 0 |
| SEC-02 | CSP does NOT contain `'unsafe-eval'` or `'unsafe-inline'` for scripts | integration | `pytest tests/middleware/test_security_headers.py::test_no_unsafe_eval -x` | ❌ Wave 0 |
| SEC-03 | Every response carries `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` | integration | `pytest tests/middleware/test_security_headers.py::test_all_headers -x` | ❌ Wave 0 |
| SEC-04 | README contains the NGINX `Strict-Transport-Security` line and proxy-header setup | docs grep | `pytest tests/docs/test_readme_nginx.py -x` (or a simple grep test) | ❌ Wave 0 |
| SEC-04 | `/debug/proxy` returns `scheme`, `client_host`, `trusted_proxy_ips`, `headers_honored` | integration | `pytest tests/routers/test_debug_proxy.py -x` | ❌ Wave 0 |
| SEC-04 | With `X-Forwarded-Proto: https` set, `/debug/proxy` reports `scheme=https` | integration | `pytest tests/routers/test_debug_proxy.py::test_https_via_proxy_header -x` | ❌ Wave 0 |
| SEC-05 | Jinja2 autoescape ON globally | unit | `pytest tests/templates/test_autoescape.py -x` | ❌ Wave 0 |
| SEC-05 | CI grep test fails when `\|safe` appears under `app/templates/pages/` | shell/CI | `bash scripts/check_template_safety.sh` or `pytest tests/ci/test_no_unsafe_jinja.py` | ❌ Wave 0 |
| SEC-05 | Same grep covers `hx-on:`, `hx-vals='js:`, `hx-headers='js:` | shell/CI | (same script) | ❌ Wave 0 |
| FragmentCache | GET without `HX-Request` → `Cache-Control: private, no-cache, must-revalidate` | integration | `pytest tests/middleware/test_fragment_cache.py::test_full_page -x` | ❌ Wave 0 |
| FragmentCache | GET with `HX-Request: true` → `Cache-Control: no-store` + `Vary: HX-Request` | integration | `pytest tests/middleware/test_fragment_cache.py::test_fragment -x` | ❌ Wave 0 |
| FragmentCache | Route-set `Cache-Control` is not overwritten | integration | `pytest tests/middleware/test_fragment_cache.py::test_no_overwrite -x` | ❌ Wave 0 |
| FragmentCache | `/static/` paths are bypassed | integration | `pytest tests/middleware/test_fragment_cache.py::test_static_bypass -x` | ❌ Wave 0 |
| CSP-report | POST `/csp-report` with `application/csp-report` body logs structured `csp.violation` event | integration | `pytest tests/routers/test_csp_report.py::test_legacy_format -x` | ❌ Wave 0 |
| CSP-report | POST `/csp-report` with `application/reports+json` body logs structured `csp.violation` event | integration | `pytest tests/routers/test_csp_report.py::test_reporting_api_format -x` | ❌ Wave 0 |
| CSP-report | `/csp-report` rate-limited to 30/min/IP (31st request returns 429) | integration | `pytest tests/routers/test_csp_report.py::test_rate_limit -x` | ❌ Wave 0 |

### Manual / Out-of-CI Validation

| Behavior | Why Not Automated | Validation Method |
|----------|-------------------|-------------------|
| Real NGINX rewrites `X-Forwarded-Proto: https` and uvicorn honors it | Requires a real reverse proxy in front of uvicorn (docker-compose can include one but it complicates CI) | After deploying to VPS: `curl -i https://snobbery.example.com/debug/proxy` and assert `"scheme": "https"`. Document in README. |
| HSTS header reaches browser via NGINX `add_header` | NGINX-level test; CI runs without NGINX | Manual: `curl -I https://snobbery.example.com/` from a non-localhost client → `Strict-Transport-Security: max-age=63072000; includeSubDomains`. |
| CSP nonce is picked up correctly by Alpine.js / HTMX scripts in a real browser | Browser-DOM-level; CI doesn't run a headless browser yet (Playwright in Phase 12) | Manual at first; can move to Playwright in Phase 12. Document expected behavior in README: open DevTools → Network → check `<script>` tags have a matching `nonce` value to the CSP header. |
| `htmx.config.allowEval = false` blocks `hx-on:` even if a template slips it past grep | Runtime browser behavior | Manual: create a test template with `hx-on:click="alert(1)"`, observe console error and that the handler does not fire. |
| HSTS preload eligibility | Out of scope for v1; preload submission is a manual process | Documented as a v1.1 follow-up if John wants. |

### Sampling Rate

- **Per task commit:** `docker compose exec coffee-snobbery pytest tests/middleware -x --tb=short` (~15 sec at this phase scale)
- **Per wave merge:** `docker compose exec coffee-snobbery pytest -x`
- **Phase gate:** Full suite green; manual smoke (`curl /debug/proxy`) documented in plan as a release-blocking checklist item.

### Wave 0 Gaps

The Phase 1 plan's first wave MUST land:

- [ ] `tests/middleware/__init__.py` — empty
- [ ] `tests/middleware/test_session.py` — covers AUTH-05 behaviors
- [ ] `tests/middleware/test_csrf.py` — covers SEC-01 behaviors
- [ ] `tests/middleware/test_security_headers.py` — covers SEC-02, SEC-03
- [ ] `tests/middleware/test_fragment_cache.py` — covers FragmentCache behaviors
- [ ] `tests/middleware/test_logging.py` — covers AUTH-10 contextvars + redaction
- [ ] `tests/routers/test_auth_stub.py` — covers AUTH-08 (login rate limit)
- [ ] `tests/routers/test_csp_report.py` — covers `/csp-report` behavior
- [ ] `tests/routers/test_debug_proxy.py` — covers `/debug/proxy` behavior
- [ ] `tests/conftest.py` — TestClient + database fixtures (transaction rollback per test)
- [ ] `tests/ci/test_no_unsafe_jinja.py` — grep test for `|safe`, `hx-on:`, `hx-vals='js:`, `hx-headers='js:` under `app/templates/pages/`
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — Wave 0 confirms or creates
- [ ] `pyproject.toml` test dependencies: `pytest`, `pytest-asyncio`, `httpx` (for TestClient async path), `respx` (not strictly needed in Phase 1 but Phase 12 uses it)

---

## 12. Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSRF middleware | Custom double-submit-cookie implementation | `starlette-csrf>=3.0,<4` | Library handles signing, cookie issuance, header matching, exempt URLs, sensitive-cookie gating in ~200 LOC. Hand-rolled version misses edge cases. |
| Rate limiter | Custom counter dict | `slowapi>=0.1.9,<0.2` | Window algorithms (sliding, fixed), per-key state, exception handler all handled. Hand-rolled version drifts on edges or has off-by-one rounding errors. |
| Cookie signing | Custom HMAC | `itsdangerous>=2.2,<3` | Library handles base64url encoding, key versioning via salt, BadSignature errors. |
| Logging JSON formatter | Custom dict-to-JSON formatter | `structlog>=25.5,<26` `ProcessorFormatter` | Handles `exc_info`, stack info, contextvars merge, foreign-pre-chain for uvicorn logs. |
| CSP header builder | String concatenation of directives | A small constant + f-string nonce injection (NOT a library) | A library is overkill; a single function in `SecurityHeadersMiddleware` is fine. **This is NOT a "use a library" item — flagged as DO-IT-YOURSELF.** |
| Session middleware (cookie-only) | This is the EXCEPTION | Hand-roll the table-backed version | Per STACK.md §3.6 and CONTEXT.md D-07, no library matches the schema requirements. ~80 LOC. **This is the one piece Phase 1 hand-rolls.** |
| Request ID assignment | Custom UUID middleware | Hand-roll OR `asgi-correlation-id` library | Either works. Hand-roll is ~20 LOC; library adds a dependency for marginal value. Lean hand-roll. |

**Key insight:** Phase 1 is mostly "wire up existing libraries correctly" — the danger is reinventing what `starlette-csrf`, `slowapi`, `itsdangerous`, `structlog` already do well. The one hand-roll (table-backed sessions) is hand-rolled because no library matches the exact schema and write-throttling behavior we need.

---

## 13. Common Pitfalls

### Pitfall 13.1: BaseHTTPMiddleware breaks contextvars

**What goes wrong:** A future contributor writes a new middleware as `class M(BaseHTTPMiddleware)` because that's the older, more familiar pattern. Inserted into the stack, it silently breaks contextvars propagation for everything below it. `request_id` stops showing up in inner logs.
**Why it happens:** `BaseHTTPMiddleware` runs the route in a separate task, breaking the contextvars chain. The bug is silent — no error, just missing fields in logs.
**How to avoid:** All custom middlewares are pure ASGI. Document the rule in `app/middleware/__init__.py` and `docs/decisions/`. Add a CI check that greps for `BaseHTTPMiddleware` in `app/middleware/` and fails.
**Warning signs:** `request_id` field appears in some log lines and not others; appearance correlates with which route handled the request.

### Pitfall 13.2: contextvars leakage across requests

**What goes wrong:** `RequestContextMiddleware` binds `request_id` via `bind_contextvars()` but doesn't call `clear_contextvars()` at the start. The previous request's `request_id` leaks into the next request's logs.
**Why it happens:** contextvars are scoped to the calling context. In ASGI, the same worker thread / event loop handles many requests; without explicit cleanup, the context persists.
**How to avoid:** Call `clear_contextvars()` AT REQUEST ENTRY (before `bind_contextvars`) AND in a `finally` block at request exit. The opening clear handles the case where a previous request failed without cleanup.
**Warning signs:** Two consecutive requests get the same `request_id` in their logs.

### Pitfall 13.3: slowapi `get_ipaddr` bug

**What goes wrong:** Planner uses `Limiter(key_func=get_ipaddr)` instead of `get_remote_address`. `get_ipaddr` looks for `X_FORWARDED_FOR` (underscores) and falls back to `127.0.0.1` for everyone. Rate limit hits the entire planet on one key.
**Why it happens:** Stale documentation, copy-paste from older slowapi tutorials.
**How to avoid:** Use `get_remote_address`. Add a docstring in `app/rate_limit.py` calling out the slowapi `get_ipaddr` bug.
**Warning signs:** Login from two different IPs counts against the same key; `/debug/proxy` shows correct client IP but rate limit fires inconsistently.

### Pitfall 13.4: Middleware order error — CSP nonce missing on response

**What goes wrong:** `SecurityHeadersMiddleware` is added BEFORE `RequestContextMiddleware`. On the request path, RequestContext mints the nonce first; on the response path, SecurityHeaders runs FIRST (outer) and tries to read `scope["state"]["csp_nonce"]` — but RequestContext hasn't set it yet (inner, runs LATER on request, EARLIER on response). Actually wait — let me re-trace: with `add_middleware` reverse-of-add, the LAST added is outermost. SecurityHeaders added before RequestContext → SecurityHeaders is INNER. Request enters: RequestContext mints nonce → SecurityHeaders runs → route → response builds → SecurityHeaders adds headers (nonce available) → RequestContext finalizes. That works.

So the actual pitfall is: if a planner gets the order backwards and adds RequestContext BEFORE SecurityHeaders, then SecurityHeaders is outermost; on request, SecurityHeaders runs first, then RequestContext mints nonce, then route, then response: RequestContext runs first on response (nonce is in scope by then) → SecurityHeaders runs last (nonce STILL in scope, all good). Actually both orders work. The pitfall is more subtle:

**What goes wrong:** SecurityHeadersMiddleware reads `scope["state"]["csp_nonce"]` but the nonce is `None` because RequestContextMiddleware crashed and didn't set it.
**Why it happens:** Defensive coding gap.
**How to avoid:** SecurityHeadersMiddleware uses `scope.get("state", {}).get("csp_nonce", "")` with a sane fallback. If empty, emit CSP without the nonce term (`script-src 'self'`) and log a warning. Avoid 500 errors solely because a middleware initialization order changed.
**Warning signs:** Empty CSP nonce values in response headers; warning log line.

### Pitfall 13.5: `/csp-report` self-DoS

**What goes wrong:** A misconfigured CSP fires hundreds of violations per second from a single broken page in a real user's browser. The 30/min rate limit kicks in, future violations are dropped — fine. But if the rate limiter exceeds its memory, or if the log handler can't keep up, the structlog handler buffers writes and slows down the worker.
**Why it happens:** CSP violations are browser-driven and uncapped at source.
**How to avoid:** The 30/min slowapi limit is the primary defense. As a secondary defense, the `_log_csp_violation()` function is fast — it doesn't do DB writes, just a single structlog call. If logging becomes a bottleneck later, route CSP violations to a separate handler.
**Warning signs:** Single client IP hitting `/csp-report` >5x in a few seconds; structlog handler dropping or buffering lines.

---

## 14. State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` / `@app.on_event("shutdown")` | `lifespan = asynccontextmanager(...)` | Starlette 1.0 (Mar 2026) | All startup/shutdown work in Phase 1+ uses lifespan. |
| `BaseHTTPMiddleware` for custom middleware | Pure ASGI middleware class | Starlette team recommendation, formalized 2024-2025 | All custom middleware in Phase 1 is pure ASGI. |
| `report-uri` only for CSP violations | `report-uri` + `report-to` + `Reporting-Endpoints` | Reporting API stable in Chrome 2020+, Safari 2024+, Firefox lagging | Emit both for browser coverage. |
| `psycopg2-binary` | `psycopg[binary]` 3.x with `postgresql+psycopg://` URL | psycopg 3.3 stable (May 2026) | SQLAlchemy URL change; not Phase-1-specific but worth noting. |
| HTMX 1.x with bundled SSE extension | HTMX 2.x with separate `htmx-ext-sse` | HTMX 2.0 final mid-2024 | Phase 1 uses core HTMX 2.0.10 only; Phase 7 may add SSE extension. |
| Tailwind v3 + JIT mode | Tailwind v4 + standalone CLI | Tailwind v4 GA late 2024 | Phase 0 decision; Phase 1 just consumes the compiled CSS. |

**Deprecated/outdated:**
- `bleach` — Mozilla deprecated 2023. If sanitization is ever needed, use `nh3` or `markdown-it-py`. Phase 1 does not need either.
- `cookie-only` Starlette `SessionMiddleware` — works but cannot satisfy the table-backed requirement.

---

## 15. Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `starlette-csrf` does NOT re-issue the cookie on every response; the cookie value stays fixed for the cookie's lifetime | §3 | Medium — if it does re-issue, the "no rotation" assertion fails. Confirm via Wave 0 integration test (POST twice, assert cookie unchanged). |
| A2 | slowapi 0.1.9 works correctly under FastAPI 0.136 / Starlette 1.0 (no breaking changes in `app.state.limiter` or `RateLimitExceeded` handler signatures) | §7 | High — if it doesn't work, Phase 1 plan must include either a fork or a hand-rolled limiter. Wave 0 smoke test: import + decorator + 429 path. |
| A3 | `@alpinejs/csp` CDN version line (latest 3.14.x) is the right pin; the `alpinejs` main package's 3.16.x version line is separate | §1 | Low — version mismatch confuses, doesn't break functionality. Confirm via `npm view @alpinejs/csp version` during plan-phase. |
| A4 | Alpine `x-transition` uses direct `element.style.X = Y` assignment (NOT blocked by `style-src-attr`) | §1 | Low — even if Alpine internals change to use `setAttribute('style')`, the CONTEXT.md D-03 `style-src-attr 'unsafe-inline'` allowance covers it. |
| A5 | uvicorn's `--proxy-headers` flag rewrites `request.client.host` from `X-Forwarded-For` in a way that slowapi's `get_remote_address` picks up | §7 | High — Phase 1 success criterion 1 depends on this. Wave 0 integration test asserts. |
| A6 | All five custom middlewares can be pure ASGI without losing any functionality currently common in BaseHTTPMiddleware tutorials | §4 | Low — pure ASGI is strictly more capable; all common patterns work. |
| A7 | `ROADMAP.md` Phase 1 success criterion 4's `auth.login_attempt` event name is acceptable for the stub `/login` route, OR CONTEXT.md D-14 will be amended | §6 | Low — taxonomy clarification, no functional impact. |
| A8 | `secrets.token_urlsafe(16)` (128 bits of entropy) meets the CSP nonce strength recommendation | §9 | Low — the CSP spec recommends 128+ bits; 16-byte token meets that. |
| A9 | The `sensitive_cookies={"session_id"}` configuration in `starlette-csrf` correctly gates CSRF enforcement on authenticated-session requests | §3 | Medium — confirm during plan-phase by reading the middleware source or running a test where an unauthenticated state-changing request hits a non-exempt URL. |

---

## 16. Open Questions

1. **`auth.login_attempt` event naming.** ROADMAP success criterion 4 uses this name; CONTEXT.md D-14 does not include it in the taxonomy.
   - What we know: D-14 lists `auth.login_succeeded`, `auth.login_failed`, `auth.logout`. `auth.login_attempt` would fit logically between request entry and resolution.
   - What's unclear: whether to add `auth.login_attempt` to D-14 or rename the Phase 1 stub log line.
   - Recommendation: amend CONTEXT.md D-14 to add `auth.login_attempt` as the pre-verification log event. Phase 2's `auth.login_succeeded` and `auth.login_failed` then describe post-verification outcomes. This gives operators a clean stream-by-stream count of attempts vs outcomes.

2. **`@alpinejs/csp` version vs main `alpinejs` version.** CONTEXT.md tracks "Alpine.js 3.16."
   - What we know: the standard `alpinejs` package and `@alpinejs/csp` package are versioned independently. The CSP package's latest 3.14.x line is the relevant pin.
   - What's unclear: whether `@alpinejs/csp` has a 3.16 release in npm registry at the time of plan-phase (registry should be checked).
   - Recommendation: plan-phase runs `npm view @alpinejs/csp version` to pin the exact CDN URL. Document the resolved version in `docs/decisions/0001-csp-strict-no-unsafe-eval.md`.

3. **`Reporting-Endpoints` header value when `/csp-report` is on the same origin.** The Reporting API allows reporting to a different origin (typically a logging service).
   - What we know: same-origin reporting works.
   - What's unclear: nothing — this is just confirming the value format `csp-report="/csp-report"` is correct for same-origin.
   - Recommendation: keep as written; Wave 0 integration test confirms a Reporting-API-style violation report arrives at `/csp-report`.

4. **slowapi compatibility under Starlette 1.0.** No public bug reports against the combination as of search date.
   - What we know: slowapi uses standard Starlette/FastAPI APIs.
   - What's unclear: whether any internal Starlette 1.0 changes (e.g., to `app.state` or `request.client` semantics) break slowapi in subtle ways.
   - Recommendation: Wave 0 smoke test (one decorated route + 6 requests asserting 429) catches the most likely breakage. If it fails, Phase 1 escalates to hand-rolled limiter (cheap; ~50 LOC) or a fork.

---

## 17. Environment Availability

Phase 1 has minimal external runtime dependencies — most everything ships in the `coffee-snobbery` Docker image built by Phase 0.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All code | ✓ (set by Phase 0 base image) | 3.12.x | — |
| `starlette-csrf` | §3 CSRFMiddleware | Add to `requirements.txt` | `>=3.0,<4` | None — no functional alternative without rewriting CSRF logic |
| `slowapi` | §7 rate limiting | Add to `requirements.txt` | `>=0.1.9,<0.2` | Hand-rolled limiter (~50 LOC) if Wave 0 smoke fails |
| `itsdangerous` | §5 session cookie signing | Already on STACK.md pinned list | `>=2.2,<3` | None |
| `structlog` | §6 logging | Already on STACK.md pinned list | `>=25.5,<26` | stdlib `logging` with JSON formatter (more LOC, no contextvars) |
| Alpine.js CSP build (CDN) | Templates | CDN URL available | `@alpinejs/csp` latest 3.14.x | Self-host the file in `/static/js/` |
| HTMX 2.0.10 (CDN) | Templates | CDN URL available | 2.0.10 | Self-host the file in `/static/js/` |
| PostgreSQL 16 | `sessions` table | ✓ (set by Phase 0 `coffee-snobbery-db`) | 16.x | — |
| NGINX (in front of uvicorn) | SEC-04 success criterion 5 (manual test) | ✓ (user's existing VPS) | Existing | Document required config in README; no automated test |

**Missing dependencies with no fallback:** None at this phase. The three new pip deps (`starlette-csrf`, `slowapi`, the optional `asgi-correlation-id` we declined to use) are all on PyPI.

**Missing dependencies with fallback:** slowapi (fallback: hand-rolled limiter). Only triggers if Wave 0 smoke test fails.

---

## 18. Code Examples

Verified patterns ready for the planner / executors to consume.

### 18.1 Pure ASGI middleware skeleton

```python
# app/middleware/security_headers.py
from __future__ import annotations
from starlette.types import ASGIApp, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                nonce = scope.get("state", {}).get("csp_nonce", "")
                csp = (
                    f"default-src 'self'; "
                    f"script-src 'self' 'nonce-{nonce}'; "
                    f"style-src-elem 'self' 'nonce-{nonce}'; "
                    f"style-src-attr 'unsafe-inline'; "
                    f"img-src 'self' data: blob:; "
                    f"connect-src 'self'; "
                    f"font-src 'self'; "
                    f"object-src 'none'; "
                    f"base-uri 'self'; "
                    f"frame-ancestors 'none'; "
                    f"form-action 'self'; "
                    f"report-uri /csp-report; "
                    f"report-to csp-report"
                )
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"content-security-policy", csp.encode()),
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy",
                     b"camera=(self), microphone=(), geolocation=(), interest-cohort=(), payment=(), usb=(), bluetooth=()"),
                    (b"reporting-endpoints", b'csp-report="/csp-report"'),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

### 18.2 `app/main.py` middleware registration order

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette_csrf import CSRFMiddleware

from app.config import settings
from app.logging_config import configure_logging
from app.middleware.session import SessionMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.fragment_cache import FragmentCacheHeadersMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.rate_limit import limiter
from app.db import async_session_factory
from app.signing import session_signer  # itsdangerous URLSafeSerializer instance

import re


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 8 will start APScheduler here.
    yield


configure_logging(level=settings.LOG_LEVEL)
app = FastAPI(lifespan=lifespan)

# Slowapi setup — NOT a middleware, attaches to app.state.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware stack — order matters (last added = outermost).
# Inner-to-outer for the request path:
app.add_middleware(
    SessionMiddleware,
    session_factory=async_session_factory,
    signer=session_signer,
)
app.add_middleware(
    CSRFMiddleware,
    secret=settings.APP_SECRET_KEY,
    cookie_secure=True,
    header_name="X-CSRF-Token",
    sensitive_cookies={"session_id"},
    exempt_urls=[re.compile(r"^/csp-report")],
)
app.add_middleware(FragmentCacheHeadersMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)  # outermost
```

### 18.3 Jinja CSP nonce hookup

```python
# app/templates_setup.py
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

templates = Jinja2Templates(directory="app/templates")

def csp_nonce(request: Request) -> str:
    return getattr(request.state, "csp_nonce", "")

templates.env.globals["csp_nonce"] = csp_nonce
```

```jinja
{# app/templates/base.html — usage #}
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/[email protected]/dist/cdn.min.js"
        nonce="{{ csp_nonce(request) }}"></script>
<script defer src="https://unpkg.com/[email protected]"
        nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/htmx-listeners.js"
        nonce="{{ csp_nonce(request) }}"></script>
<meta name="csrf-token" content="{{ request.cookies.get('csrftoken', '') }}">
```

### 18.4 `htmx-listeners.js` skeleton

```javascript
// app/static/js/htmx-listeners.js
// First line: defense-in-depth runtime block of eval-using features.
htmx.config.allowEval = false;

// Attach CSRF token from <meta> to every HTMX request.
document.body.addEventListener('htmx:configRequest', (evt) => {
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) {
        evt.detail.headers['X-CSRF-Token'] = tokenMeta.content;
    }
});

// Example: Alpine and HTMX event-delegation handlers go here instead of `hx-on:*`
// in templates. Phase 4+ adds handlers as needed.
```

### 18.5 Grep test for forbidden patterns

```python
# tests/ci/test_no_unsafe_jinja.py
import re
from pathlib import Path

import pytest

PAGES_DIR = Path("app/templates/pages")

FORBIDDEN_PATTERNS = [
    (re.compile(r"\|\s*safe"), "Pipe `|safe` is forbidden in user-facing templates"),
    (re.compile(r"\bhx-on:"), "`hx-on:*` is forbidden — use htmx-listeners.js event delegation"),
    (re.compile(r"hx-vals=['\"]js:"), "`hx-vals='js:...'` is forbidden — set via htmx:configRequest listener"),
    (re.compile(r"hx-headers=['\"]js:"), "`hx-headers='js:...'` is forbidden — set via htmx:configRequest listener"),
]

@pytest.mark.parametrize("template_path", list(PAGES_DIR.rglob("*.html")))
def test_template_safety(template_path: Path):
    content = template_path.read_text(encoding="utf-8")
    for pattern, message in FORBIDDEN_PATTERNS:
        match = pattern.search(content)
        assert not match, f"{template_path}: {message} (matched: {match.group(0) if match else ''})"
```

---

## 19. Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Partial (Phase 2 owns argon2id) | Phase 1 ships the session-cookie-only stub; rate limiting on `/login` (slowapi 5/15min) |
| V3 Session Management | Yes | Table-backed sessions per D-07; `HttpOnly; Secure; SameSite=Lax`; signed via itsdangerous; sliding 30-day expiry; ID regeneration helper (Phase 2 wires) |
| V4 Access Control | Partial (Phase 2 owns `is_admin`) | Phase 1 leaves `/debug/proxy` public; Phase 2 wraps it |
| V5 Input Validation | Partial (Phase 4 owns Pydantic ranges) | Phase 1 validates only `/csp-report` payload shape |
| V6 Cryptography | Yes | `itsdangerous` (HMAC) for cookie signing; never hand-rolled |
| V7 Error Handling & Logging | Yes | structlog with redaction processor; no PII in logs (AUTH-10) |
| V8 Data Protection | Partial (Phase 3 owns Fernet for API keys) | Phase 1 ensures session tokens never log |
| V9 Communications | Yes | HSTS at NGINX (SEC-04); `Secure` cookies require HTTPS upstream |
| V13 API and Web Service | Yes | CSRF on every state-changing endpoint; CSP nonce-based; security headers on every response |
| V14 Configuration | Yes | `app/config.py` is the single env-var reader (CLAUDE.md invariant); no `os.environ` elsewhere |

### Known Threat Patterns for FastAPI + HTMX + PostgreSQL

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSRF on state-changing forms | Tampering | `starlette-csrf` double-submit-cookie (SEC-01) |
| Session fixation | Spoofing | Regenerate session ID on login / logout / privilege change (D-10) |
| Cookie hijacking | Information Disclosure | `HttpOnly; Secure; SameSite=Lax` (D-10) |
| XSS via template output | Tampering / Info Disclosure | Jinja2 autoescape on; `|safe` banned (SEC-05) |
| XSS via inline event handlers | Tampering | CSP `'unsafe-eval'` and `'unsafe-inline'` for scripts forbidden (D-02) |
| Clickjacking | Tampering | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` (SEC-03) |
| MIME-sniffing attacks | Tampering | `X-Content-Type-Options: nosniff` (SEC-03) |
| Brute-force login | Spoofing | slowapi 5/15min per IP (AUTH-08) |
| Information leakage via logs | Information Disclosure | Redaction processor; no request bodies in logs (AUTH-10) |
| Proxy-header bypass (cookies dropped) | Spoofing | uvicorn `--proxy-headers` + `TRUSTED_PROXY_IPS` (SH-6) |
| Open redirect via Referrer | Information Disclosure | `Referrer-Policy: strict-origin-when-cross-origin` (SEC-03) |
| Feature abuse (camera/mic/geo) | Tampering | `Permissions-Policy` allowlist (SEC-03) |

---

## Sources

### Primary (HIGH confidence)

- [Starlette Middleware docs](https://www.starlette.io/middleware/) — middleware execution order, BaseHTTPMiddleware vs pure ASGI, pure ASGI template
- [FastAPI middleware tutorial](https://fastapi.tiangolo.com/tutorial/middleware/) — `add_middleware` reverse-of-add semantics
- [FastAPI advanced events (lifespan)](https://fastapi.tiangolo.com/advanced/events/) — lifespan context manager required
- [Alpine.js CSP docs](https://alpinejs.dev/advanced/csp) — CSP build limitations
- [Alpine.js CSP source on GitHub](https://github.com/alpinejs/alpine/blob/main/packages/csp/src/index.js) — verified directive overrides (x-html disabled, evaluator replaced)
- [HTMX CSP docs](https://htmx.org/docs/#csp) — `htmx.config.allowEval`, `hx-on:`, `hx-vals='js:`, `hx-headers='js:`, event filters
- [starlette-csrf README on GitHub](https://github.com/frankie567/starlette-csrf) — configuration parameters, double-submit-cookie behavior
- [MDN style-src-attr](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src-attr) — `element.style.X` NOT blocked; `setAttribute('style')` IS blocked
- [MDN report-to](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-to) — Reporting API status
- [MDN report-uri](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-uri) — deprecation status
- [structlog standard-library integration docs](https://www.structlog.org/en/stable/standard-library.html) — ProcessorFormatter recipe
- [structlog contextvars docs](https://www.structlog.org/en/stable/contextvars.html) — `bind_contextvars`, `clear_contextvars`, `merge_contextvars`
- [slowapi readthedocs](https://slowapi.readthedocs.io/) — Limiter setup, key_func, decorator pattern
- [slowapi GitHub](https://github.com/laurentS/slowapi) — repository, CHANGELOG (last release Feb 2024)

### Secondary (MEDIUM confidence)

- [Adrian Haynes — Alpine.js CSP build setup](https://adrianshaynes.com/posts/setting-up-alpinejs-csp-build) — practical setup walkthrough
- [Hyvä docs — Alpine.js CSP build](https://docs.hyva.io/hyva-themes/writing-code/csp/alpine-csp.html) — directive support table
- [LiteLLM blog — FastAPI middleware performance](https://docs.litellm.ai/blog/fastapi-middleware-performance) — BaseHTTPMiddleware vs pure ASGI benchmark
- [Kludex/starlette discussion #2160](https://github.com/Kludex/starlette/discussions/2160) — BaseHTTPMiddleware deprecation discussion
- [Yet Another Techblog — FastAPI + structlog integration](https://wazaari.dev/blog/fastapi-structlog-integration) — applied recipe
- [slowapi issue #255 — get_ipaddr bug](https://github.com/laurentS/slowapi/issues/255) — confirms the X_FORWARDED_FOR bug
- [Medium — Amar Harolikar — Are You Rate Limiting the Wrong IPs?](https://medium.com/@amarharolikar/are-you-rate-limiting-the-wrong-ips-a-slowapi-story-88c2755f5318) — Mar 2026 article on slowapi key_func best practices
- [Alpine.js discussion #3996 — x-model in CSP build](https://github.com/alpinejs/alpine/discussions/3996) — confirms x-model not supported under CSP

### Tertiary (LOW confidence — assumed)

- A1 `starlette-csrf` cookie non-rotation behavior — confirmed by README behavior description; needs Wave 0 empirical test.
- A2 slowapi 0.1.9 compatibility with Starlette 1.0 / FastAPI 0.136 — no public bug reports; needs Wave 0 smoke.
- A3 `@alpinejs/csp` exact CDN version pin — verify via `npm view @alpinejs/csp version` during plan-phase.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library has an authoritative source.
- Architecture: HIGH — middleware order rules confirmed in two independent sources.
- Pitfalls: HIGH — contextvars / BaseHTTPMiddleware issue documented in Starlette repo discussions; slowapi `get_ipaddr` bug filed and known.
- Alpine CSP build behavior: HIGH for directive support, MEDIUM for the exact CSP-attribute interaction (verified via MDN, but final empirical validation in Wave 0).

**Research date:** 2026-05-16
**Valid until:** 2026-06-15 (30 days; the underlying libraries are stable; slowapi staleness flagged as a watch item)
