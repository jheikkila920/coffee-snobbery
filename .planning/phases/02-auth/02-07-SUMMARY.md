---
phase: 02-auth
plan: 07
subsystem: routers
tags: [routers, templates, schemas, auth, wave-4, d-01, d-03, d-07, d-12, d-15]

# Dependency graph
requires:
  - phase: 01-middleware
    provides: app.signing.sign_session_id, app.services.sessions.regenerate_session/delete_session/build_session_cookie/build_session_clear_cookie, app.csrf.CSRFFormFieldShim (class only — wiring lands in Plan 02-10), app.rate_limit.limiter + LOGIN_LIMIT + SETUP_LIMIT, app.events.AUTH_LOGIN_SUCCEEDED/AUTH_LOGIN_FAILED/AUTH_LOGOUT/ADMIN_USER_CREATED, app.templates_setup.templates
  - phase: 02-auth
    plan: 01
    provides: tests/conftest.py::seeded_regular_user + fresh_db + async_client fixtures
  - phase: 02-auth
    plan: 02
    provides: app.services.auth.hash_password/verify_password/dummy_verify
  - phase: 02-auth
    plan: 03
    provides: app.dependencies.db.get_async_session
  - phase: 02-auth
    plan: 05
    provides: app.services.setup.create_first_admin (FOR UPDATE race-protected)
  - phase: 02-auth
    plan: 06
    provides: request.state.session is now the Session ORM row (was {'user_id': int}) — login + logout read .session_id / .user_id directly
provides:
  - "GET /setup renders pages/setup.html when setup_completed='false'; 303→/login otherwise"
  - "POST /setup runs explicit pre-flight SELECT to avoid argon2 cost on repeat-post; on success: create_first_admin + admin.user_created log + regenerate_session + auth.login_succeeded log + 303→/ with signed session cookie (D-03 auto-login)"
  - "POST /setup race-loser branch (create_first_admin returns None) → 303→/login"
  - "GET /login renders pages/login.html with empty error + empty username"
  - "POST /login happy path: argon2 verify_password + regenerate_session deletes prior session + signs new session_id + 303→/ + Set-Cookie"
  - "POST /login three failure legs (user_not_found, inactive, bad_password) all hit dummy_verify for symmetric ~100ms wall-clock cost; all return 200 + generic re-render with 'Invalid username or password.' (D-07); D-15 logging contract observed (no attempted_username on user_not_found)"
  - "POST /logout: DELETE session row + build_session_clear_cookie (Max-Age=0) + 303→/login; idempotent when no session attached (user_id=None in audit log)"
  - "app/schemas/auth.py: SetupForm (username regex 3-32 / EmailStr / password ≥12) + LoginForm (loose; no regex to avoid timing-channel enumeration)"
  - "app/templates/pages/setup.html + pages/login.html: hidden X-CSRF-Token input field (D-15); Tailwind utility-class only; 2-space indent; no |safe / no hx-on:"
  - "12 integration tests in tests/routers/test_auth.py covering AUTH-01 / AUTH-02 / AUTH-03 / AUTH-06 / AUTH-07"
  - "requirements.txt: email-validator>=2,<3 (lazy-imported by EmailStr at class-build time)"
affects:
  - "phase 02 plan 10: turns the two CSRF-xfail tests green when CSRFFormFieldShim is wired; structlog assertions for D-15 logging policy land in Plan 10 Task 4"
  - "phase 4+: catalog routes inherit the templates_setup.templates + get_async_session conventions from this plan"

# Tech tracking
tech-stack:
  added:
    - "email-validator>=2,<3 (requirements.txt) — required by pydantic.EmailStr at model-class build time"
  patterns:
    - "Pre-flight explicit SELECT before SELECT FOR UPDATE: avoids ~100ms argon2 cost on the repeat-POST path while the FOR UPDATE inside create_first_admin remains the authoritative race-protection seam (T-02-07-09 + RESEARCH Open Q5)"
    - "FastAPI Form 1 idiom (Depends() / Form(...) in argument defaults) with per-line noqa: B008 — matches the convention from ac71543 (Plan 02-08)"
    - "Manual Pydantic-model construction inside the handler (try: SetupForm(**form_kw) except ValidationError) rather than Annotated[..., Form()] — lets the handler catch ValidationError locally and render the D-07 generic re-render instead of letting FastAPI return the default 422 JSON payload"
    - "Symmetric dummy_verify on the LoginForm ValidationError leg — closes the wall-clock timing channel that would otherwise distinguish 'malformed username' from 'valid shape, wrong credentials' (extends T-02-07-01 symmetry)"
    - "RedirectResponse(303) with response.headers.append('Set-Cookie', ...) (not __setitem__) — append preserves any other Set-Cookie headers (e.g., csrftoken rotation) that middleware may have emitted earlier in the response"
    - "Runtime-xfail pattern (pytest.xfail inside the test body when the precondition is not yet met) for CSRF-gated tests that depend on Plan 02-10 CSRFFormFieldShim wiring — mirrors tests/routers/test_admin.py for tests that span wave boundaries"

key-files:
  created:
    - ".planning/phases/02-auth/02-07-SUMMARY.md (this file)"
    - "app/schemas/auth.py — SetupForm + LoginForm Pydantic v2 schemas (53 lines)"
    - "app/templates/pages/setup.html — first-admin setup form with D-15 hidden CSRF input (24 lines)"
    - "app/templates/pages/login.html — sign-in form with D-15 hidden CSRF input + username repopulation (20 lines)"
    - "tests/routers/test_auth.py — 12 integration tests for AUTH-01 / AUTH-02 / AUTH-03 / AUTH-06 / AUTH-07 + CSRF (411 lines)"
  modified:
    - "app/routers/auth.py — full body replacement: Phase 1 stubs (53 lines) replaced with the real /setup + /login + /logout handlers (396 lines after format/lint)"
    - "requirements.txt — added email-validator>=2,<3 after pydantic-settings (3 line insertion incl. comment + the dep line)"
  deleted:
    - "tests/routers/test_auth_stub.py — replaced by tests/routers/test_auth.py per VALIDATION line 91 (deleted in the same commit as the replacement file lands, per the plan's explicit `git rm` step)"

key-decisions:
  - "Loose LoginForm.username validation (1-32 char, no regex) — a strict regex would create a wall-clock timing channel between 'malformed username, fast 422' and 'valid shape, wrong-password ~100ms argon2 verify' that lets an attacker enumerate valid usernames purely from response timing. The LoginForm ValidationError leg also calls dummy_verify before re-rendering so the malformed-input branch matches the wrong-password branch in cost (T-02-07-01 symmetry)."
  - "Pre-flight SELECT in POST /setup runs BEFORE the SELECT FOR UPDATE inside create_first_admin (RESEARCH Open Q5). The inner FOR UPDATE remains the authoritative race-protection seam; the pre-flight is purely a cost-reduction guard for the repeat-POST path (T-02-07-09 mitigation). Without it, a repeat POST after setup is complete would incur the full ~100ms argon2 hash cost before bailing out."
  - "EmailStr lazy-import added email-validator to requirements.txt. The package is a dnspython-dependent ~35KB wheel; it loads only when the EmailStr-bearing model class is built (pydantic.networks lazy import). First EmailStr usage in the codebase."
  - "noqa: B008 on the four Depends() argument defaults rather than refactoring to FastAPI's Annotated[..., Depends(...)] syntax — preserves the Form 1 idiom already established by Plan 02-08 (ac12d1c — and the dependency-shape consistency keeps Plan 02-10's wiring trivial)."
  - "CSRF-gated tests (test_login_csrf_blocked, test_logout_csrf_blocked) use the runtime-xfail pattern rather than @pytest.mark.xfail. Reason: when Plan 02-10 lands the CSRFFormFieldShim, these tests turn green automatically with strict=False marking; the runtime branching makes the 'why it xfails' inline-readable and prevents a stale xfail-marker drift if Plan 02-10 is implemented in a way that makes these tests pass earlier than expected."

patterns-established:
  - "Forms with the D-15 form-field CSRF shim: every classic form POST template carries a hidden <input name=\"X-CSRF-Token\" value=\"{{ request.cookies.get('csrftoken', '') }}\"> as the FIRST input. Plan 02-10's CSRFFormFieldShim reads this exact name (matches app/csrf.py:CSRF_HEADER_NAME) and hoists it into the request header so CSRFMiddleware sees a header-pair on POSTs."
  - "/setup handler shape: pre-flight SELECT → try-except ValidationError → service call → race-loser branch (None return) → success branch (admin.user_created log + regenerate_session + auth.login_succeeded log + 303 + Set-Cookie). Phase 9 reset-password / promote-user routes follow the same skeleton."
  - "/login handler shape: try-except ValidationError (with dummy_verify symmetry inside the except) → SELECT user → user is None branch (dummy_verify + log without user_id) → not user.is_active branch (dummy_verify + log with user_id + reason='inactive') → not verify_password branch (log with user_id + reason='bad_password') → happy path (regenerate_session + auth.login_succeeded log + 303 + Set-Cookie). All four failure legs emit the same generic D-07 re-render."

requirements-completed: [AUTH-01, AUTH-02, AUTH-03, AUTH-06, AUTH-07]

# Metrics
duration: 26min
completed: 2026-05-18
---

# Phase 02 Plan 07: Real /setup + /login + /logout Handlers Summary

**One-liner:** Real argon2-verify + session-regenerate + cookie-mint flow for /setup (D-03 auto-login), /login (D-07 200-re-render on every failure leg with symmetric dummy_verify timing), and /logout (D-12 POST-only with CSRF) — replacing the Phase 1 stub bodies — plus the matching SetupForm + LoginForm Pydantic schemas and pages/setup.html + pages/login.html templates carrying the D-15 hidden CSRF input.

## What landed

**Production code (3 files):**

1. **`app/routers/auth.py` — full body replacement.** The Phase 1 stub (53 lines, POST-only `/login` + `/setup` returning `{"status":"stub"}`) is replaced by the real handlers (396 lines after format/lint). Five routes registered: `GET /setup`, `POST /setup`, `GET /login`, `POST /login`, `POST /logout`. The slowapi decorators (`@limiter.limit(LOGIN_LIMIT)`, `@limiter.limit(SETUP_LIMIT)`) and the `request: Request` parameter are preserved verbatim from the stub (slowapi requires the introspection at decoration-effective time).
2. **`app/schemas/auth.py` (new).** `SetupForm` (username regex `^[A-Za-z0-9_-]{3,32}$` / `EmailStr` / password ≥12) and `LoginForm` (loose — 1-32 char username, no regex, password ≥1). Both are constructed manually inside the handler so `ValidationError` can be caught locally and the D-07 generic re-render rendered instead of FastAPI's default 422 JSON.
3. **`requirements.txt`** — `email-validator>=2,<3` added immediately after `pydantic-settings`. Required by `pydantic.EmailStr` at model-class build time (lazy import in `pydantic.networks.import_email_validator`).

**Templates (2 files, new):**

4. **`app/templates/pages/setup.html`** — first-admin setup form. Hidden `<input name="X-CSRF-Token">` as the first field (D-15). Username/email/password labeled inputs with browser-native validation hints (`minlength`/`maxlength`/`pattern`). Tailwind utility classes only; 2-space indent; mobile-first `max-w-prose px-6 py-12` works at 375px without horizontal scroll.
5. **`app/templates/pages/login.html`** — sign-in form. Same hidden CSRF input shape; username field re-populated from the `{{ username }}` context var on the D-07 generic re-render path. No password re-population.

**Tests (1 file, new + 1 deletion):**

6. **`tests/routers/test_auth.py` (new, 411 lines, 12 tests):**
   - `test_setup_happy_path` (AUTH-01): clean DB → 303 to `/` with session cookie.
   - `test_setup_blocked_after_completion` (AUTH-01): GET + POST both 303 to `/login` when `setup_completed='true'`.
   - `test_setup_concurrent_race` (AUTH-02): two concurrent POSTs via `async_client` + `asyncio.gather` → exactly one 303→`/` + one 303→`/login`; exactly 1 user row.
   - `test_no_register_route` (AUTH-03): `/register` GET + POST both 404 (or 405 for POST).
   - `test_login_happy_path` (AUTH-03): seeded user + correct creds → 303→`/` + session cookie.
   - `test_login_wrong_password` (AUTH-03 + D-07): wrong password → 200 + body contains "Invalid username or password."
   - `test_session_cookie_attributes` (AUTH-06): Set-Cookie carries `HttpOnly`, `Secure`, `SameSite=Lax`, `Max-Age=2592000`, `Path=/`.
   - `test_session_fixation_defense` (AUTH-07): old session_id DELETEd; new session_id signed differently.
   - `test_preset_cookie_does_not_inherit` (AUTH-07): attacker pre-set cookie value does not carry forward.
   - `test_logout_clears_session` (AUTH-07): POST /logout → 303→`/login`, session row DELETEd, Max-Age=0 in clear cookie.
   - `test_login_csrf_blocked` + `test_logout_csrf_blocked` (CSRF): bare POST without token → 403; **runtime-xfail until Plan 02-10 wires the `CSRFFormFieldShim`**.
7. **`tests/routers/test_auth_stub.py` DELETED** (replaced by the file above, per VALIDATION line 91).

## Commits (in order)

| # | Hash | Type | Summary |
|---|------|------|---------|
| 1 | `059adbf` | `test(02-07)` | Comprehensive /setup + /login + /logout integration tests; DELETE stub |
| 2 | `10b99f3` | `feat(02-07)` | SetupForm + LoginForm Pydantic schemas (AUTH-01 / AUTH-03) |
| 3 | `e5d5b13` | `feat(02-07)` | Real /setup + /login + /logout handlers (replaces Phase 1 stub) |
| 4 | `ac12d1c` | `feat(02-07)` | pages/setup.html + pages/login.html with D-15 form-field CSRF |

## Verification

- `docker compose exec coffee-snobbery python -m pytest tests/routers/test_auth.py tests/ci/test_no_unsafe_jinja.py` → **14 passed, 2 xfailed** (10 non-CSRF-gated + 4 template safety tests pass; 2 CSRF-gated tests xfail with the expected reason).
- Full suite: `docker compose exec coffee-snobbery python -m pytest` → **70 passed, 2 skipped, 16 xfailed** — no regressions in any prior phase test.
- `ruff check app/routers/auth.py app/schemas/auth.py` → all checks pass (B008 silenced with per-line `noqa` on Depends arg defaults — FastAPI Form 1 idiom).
- `ruff format --check app/routers/auth.py app/schemas/auth.py` → already formatted.
- Stub file removal verified: `test -f tests/routers/test_auth_stub.py && echo "STILL PRESENT" || echo "ok deleted"` → `ok deleted`.

## Decisions Made

1. **Loose LoginForm.username validation** (no regex; min/max length only). A strict regex would create a wall-clock timing channel — see `key-decisions[0]`.
2. **Pre-flight SELECT in POST /setup before `create_first_admin`'s SELECT FOR UPDATE.** Cost-reduction for the repeat-POST path; the inner FOR UPDATE remains the authoritative race-protection seam — see `key-decisions[1]`.
3. **`email-validator` added to requirements.txt.** First `EmailStr` usage in the codebase; lazy-imported at class build time — see `key-decisions[2]`.
4. **`noqa: B008` on `Depends()` argument defaults** rather than refactoring to `Annotated[..., Depends(...)]`. Preserves Form 1 idiom from Plan 02-08 — see `key-decisions[3]`.
5. **Runtime-xfail (not `@pytest.mark.xfail`) for CSRF-gated tests.** Auto-flips green when Plan 02-10 wires the shim; no stale-marker risk — see `key-decisions[4]`.

## Deviations from Plan

**None — plan executed as written.** The plan's `<action>` blocks specified the route bodies, template scaffolds, and test set verbatim; all four tasks landed in the order written. The only judgment call (committing as 4 atomic commits per task vs. 1-2 squashed commits — both shapes were explicitly permitted by the plan's `<objective>`) was to use 4 atomic commits for clean per-task attribution.

## Authentication Gates Encountered

None. No external authentication was needed during this plan's execution.

## Known Stubs

None introduced by this plan. The two CSRF-gated tests (`test_login_csrf_blocked`, `test_logout_csrf_blocked`) await Plan 02-10's `CSRFFormFieldShim` wiring — but that's a runtime-xfail with a clear reason, not a code stub. The auth handlers themselves are complete; their CSRF dependency is one wiring step away.

## Threat Flags

None. All security-relevant surface introduced by this plan is enumerated in the plan's `<threat_model>` (T-02-07-01 through T-02-07-10). No new endpoints, no new schema mutations, no new file access patterns outside what the plan modeled.

## TDD Gate Compliance

Plan-task 1 was the only `tdd="true"` task. Gate order verified in git log:

| Gate | Commit | Type |
|------|--------|------|
| RED | `059adbf` | `test(02-07): comprehensive /setup + /login + /logout integration tests` |
| GREEN (schemas) | `10b99f3` | `feat(02-07): SetupForm + LoginForm Pydantic schemas` |
| GREEN (router) | `e5d5b13` | `feat(02-07): real /setup + /login + /logout handlers` |
| GREEN (templates) | `ac12d1c` | `feat(02-07): pages/setup.html + pages/login.html` |

RED → GREEN sequence intact. No REFACTOR commit needed (the implementation matched the planner's verbatim RESEARCH excerpt without post-hoc cleanup).

## Self-Check: PASSED

- `tests/routers/test_auth.py` — present (`git log --oneline --all | grep 059adbf` → FOUND).
- `app/schemas/auth.py` — present (`git log --oneline --all | grep 10b99f3` → FOUND).
- `app/routers/auth.py` — modified (`git log --oneline --all | grep e5d5b13` → FOUND).
- `app/templates/pages/setup.html` — present (`git log --oneline --all | grep ac12d1c` → FOUND).
- `app/templates/pages/login.html` — present (`git log --oneline --all | grep ac12d1c` → FOUND).
- `tests/routers/test_auth_stub.py` — DELETED (`git log --diff-filter=D --name-only HEAD~4 HEAD | grep test_auth_stub` → matched in commit 059adbf).
- All claimed commit hashes (`059adbf`, `10b99f3`, `e5d5b13`, `ac12d1c`) reachable via `git log`.
- Verification commands re-run; results match the SUMMARY claims.
