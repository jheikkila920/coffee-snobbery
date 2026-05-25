# Phase 2: Auth - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-17
**Phase:** 2-Auth
**Areas discussed:** Setup flow specifics, Login routing & form style, Session middleware user payload, Logout method + admin-stub scope

---

## Setup flow specifics

### Q1 — Post-setup behavior

| Option | Description | Selected |
|--------|-------------|----------|
| 404 (silent) | Matches success criterion #1. Doesn't reveal that /setup ever existed; one less attack surface to think about. Less friendly if an admin types /setup by accident later. | |
| 302 → /login (Recommended) | Matches the roadmap goal sentence. Friendlier: an admin who bookmarked /setup pre-launch isn't stuck on a 404 page; security cost is nil. | ✓ |
| 410 Gone | Pedantically correct HTTP semantics: 'resource intentionally retired.' Same UX cost as 404, no real benefit over a redirect. | |

**User's choice:** 302 → /login
**Notes:** Aligns ROADMAP goal sentence with success criterion #1; the criterion wording gets amended at plan-phase to match.

### Q2 — Email field on /setup

| Option | Description | Selected |
|--------|-------------|----------|
| Optional email field (Recommended) | Adds an <input type=email>; blank is fine (schema is nullable). Stores it now so future admin recovery / notification features have a value to work with. | |
| Username + password only | Cleanest setup form. Email can always be added later via Phase 9's admin user editor. Matches the spec's literal 'username + password' phrasing. | |
| Email required for first admin | Forces an email at setup time. Stricter, but no recovery flow exists in v1 to make use of it — mostly future-proofing. | ✓ |

**User's choice:** Email required for first admin
**Notes:** User opted to require email even though my recommendation was "optional." Phase 9 admin user-create is a separate decision — likely keep email optional there.

---

## Login routing & form style

### Q1 — Post-login destination

| Option | Description | Selected |
|--------|-------------|----------|
| Always redirect to / (Recommended) | Simplest. One landing spot for everyone. No URL-injection surface. | ✓ |
| Honor ?next= with same-origin allowlist | Value once Phase 4+ has guarded routes that bounce anonymous users to /login. Requires strict same-origin allowlist to prevent open-redirect CVEs. | |
| Different landing for admin vs regular user | Admins → /admin, regular users → /. Overkill for a two-user household app. | |

**User's choice:** Always redirect to /
**Notes:** ?next= captured as deferred for revisit if Phase 4+ friction proves real.

### Q2 — Form interaction style

| Option | Description | Selected |
|--------|-------------|----------|
| Classic form POST → 302 (Recommended) | Standard <form method=post>. 303 redirect with Set-Cookie. No HTMX on auth surfaces. Works without JS, works under CSP. | ✓ |
| HTMX POST with HX-Redirect | <form hx-post=/login>. Server returns 204 + HX-Redirect: / header. Slightly more consistent with the rest of the app. | |
| Mixed: classic on /setup, HTMX on /login | More moving parts — worth it only if inline error swap matters. | |

**User's choice:** Classic form POST → 302
**Notes:** Locked to 303 See Other in CONTEXT (forces GET-after-POST on HTTP/1.0 clients).

---

## Session middleware user payload

### Q1 — What does SessionMiddleware load on every authenticated request?

| Option | Description | Selected |
|--------|-------------|----------|
| Full User row (Recommended) | One SELECT users.* per authenticated request. ~9 cols, indexed PK, ~0.2ms at household scale. Simple downstream API. | ✓ |
| Minimal tuple (id, username, is_admin, is_active) | Cheaper but premature for two-user scale. Downstream code needing email/last_login_at would need a second query. | |
| Full row, lazy-loaded via a per-request property | Saves the lookup on anonymous routes. Adds machinery; only matters if a lot of routes never read user fields. | |

**User's choice:** Full User row
**Notes:** Replaces the Phase 1 `{"user_id": int}` stub at `app/middleware/session.py:179`.

### Q2 — Deactivated / deleted user behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Treat as no session, clear cookie, delete row (Recommended) | Same path the middleware already uses for expired/missing sessions. Deactivating immediately logs the user out on next request. | ✓ |
| Treat as authenticated but is_admin=false | User stays signed in but loses admin powers. Inconsistent with what 'deactivate' implies. | |
| Treat as session valid for read-only routes, block writes | Adds a per-route layer. Overengineering for v1. | |

**User's choice:** Treat as no session, clear cookie, delete row
**Notes:** Fail-closed semantics consistent across all "session no longer valid" branches.

---

## Logout method + admin-stub scope

### Q1 — /logout method

| Option | Description | Selected |
|--------|-------------|----------|
| POST-only, CSRF-protected (Recommended) | <form method=post action=/logout> with CSRF token. Aligns with SEC-01. A drive-by GET can't sign John out. | ✓ |
| GET with a one-shot signed token | Plain link with token bound to session_id, single-use. More moving parts; little benefit at household scale. | |
| GET, no token, CSRF-exempt | Easiest UX but violates SEC-01. Don't pick unless trade-off is accepted. | |

**User's choice:** POST-only, CSRF-protected

### Q2 — /admin stub depth

| Option | Description | Selected |
|--------|-------------|----------|
| Single page, 'Admin (stub) — wiring lands in Phase 9' (Recommended) | One route: GET /admin returns 200 or 403. Phase 9 owns the sub-router scaffolding. | ✓ |
| Scaffold sub-router module + nav | Placeholder routes for users / api-credentials / app-settings / backups / system-info. Throwaway code that Phase 9 will reshape. | |
| Scaffold sub-router + start user-management list | Scope creep — user CRUD is owned by Phase 9 (ADMIN-01). | |

**User's choice:** Single page, 'Admin (stub) — wiring lands in Phase 9'

---

## Follow-up: setup auto-login

### Q — Auto-login after /setup, or bounce to /login?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-login → redirect to / (Recommended) | /setup POST creates the user, calls regenerate_session(None, user_id), sets the cookie, 302 to /. One step instead of two. | ✓ |
| Bounce to /login (literal roadmap reading) | /setup POST creates the user, 302 to /login. Matches success criterion #5 verbatim but costs an extra form fill at first boot. | |

**User's choice:** Auto-login → redirect to /
**Notes:** ROADMAP success criterion #5 wording gets amended at plan-phase.

---

## Final wrap

User selected "I'm ready for context" — declined extra areas on password policy and username constraints. Both captured under Claude's Discretion with sensible defaults (12-char password minimum, 3–32 char username with `[A-Za-z0-9_-]`, Pydantic `EmailStr` for email).

## Claude's Discretion

- Password policy floor (defaults: 12 chars min, no complexity rules, no HIBP check)
- Username constraints (defaults: 3–32 chars, `[A-Za-z0-9_-]`, citext for case)
- Setup + login template ergonomics (copy, layout)
- Sign-out button location in Phase 2 (footer on `pages/index.html`)
- `require_admin` dependency module location (`app/dependencies/auth.py` proposed)
- Setup-completed read path (use Phase 3 typed reader if available, else direct SELECT)
- Atomic flip mechanics (raw SQL vs SQLAlchemy 2.0 `with_for_update` — either is fine)

## Deferred Ideas

- "Sign out everywhere" UX (Phase 1 D-09 already rejected for v1)
- Password reset / recovery flow (v2 — needs email infrastructure)
- Breached-password (HIBP) check (rejected for v1; revisit if security review flags it)
- Complex password policy (rejected; argon2id makes brute-force expensive enough)
- Periodic expired-session sweep job (Phase 8)
- `?next=` query-param support on /login (revisit if Phase 4+ friction proves real)
- HTMX-friendly 429 error template (revisit if JSON page is jarring during real attack)
- `require_active_user` dependency (Phase 4+ guarded routes will want this)
- Admin email vs personal email separation in `users` (v2 if recovery flows land)
