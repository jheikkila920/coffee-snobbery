---
phase: 02-auth
verified: 2026-05-18T13:10:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Restart the running uvicorn process to pick up the Phase-2 code (currently running stale code from before the docker cp)"
    expected: "curl http://127.0.0.1:8080/admin returns 403 (not 404); curl http://127.0.0.1:8080/debug/proxy returns 403 (not 200)"
    why_human: "The container has been up 15 hours (since 2026-05-17 22:28 UTC); the Phase-2 source files (app/main.py, app/routers/admin.py, app/routers/debug.py, app/csrf.py, etc.) were docker cp'd in AFTER the uvicorn process started (file mtimes 01:38–02:34 vs PID 1 start 22:28). The on-disk code is correct (the full pytest suite is green inside the container: 79 passed, 2 skipped, 10 xfailed) but the served HTTP surface is the Phase-1 stub. Operator must run `docker compose restart coffee-snobbery` (or rebuild + up -d) so the live process reflects the verified codebase. Curl probes after restart confirm. Pure deployment-hygiene gap, not a code defect."
  - test: "Visually verify the mobile-first cream/espresso palette + 375px viewport for /setup, /login, /admin, /"
    expected: "No horizontal scroll at 375px; cream surfaces with espresso button accents; form inputs ≥16px to suppress iOS focus-zoom"
    why_human: "CLAUDE.md mobile-first invariant: 'any UI change tested at 375px viewport'. Templates use Tailwind `mx-auto max-w-prose px-6 py-12` + `bg-espresso-900 text-cream-50` but visual conformance requires a browser at 375×667. Out of scope for grep-based verification."
  - test: "Clean up the duplicate /app/app/dependencies/dependencies/ subdirectory inside the container"
    expected: "Only /app/app/dependencies/ contains __init__.py, auth.py, db.py — no nested dependencies/dependencies/"
    why_human: "Cosmetic docker cp artifact: /app/app/dependencies/dependencies/ holds an old copy of the package (timestamps 01:14 / 01:29). Does NOT affect imports (Python resolves the outer app.dependencies first) but is housekeeping noise that should be removed before the next deploy. Host filesystem is clean — only the container is affected."

re_verification:
  previous_status: initial
  previous_score: null

overrides: []
gaps: []
deferred: []
---

# Phase 02: Auth — Verification Report

**Phase Goal (ROADMAP):** Setup race-protected first-admin creation, argon2id login, session regeneration on privilege change, admin gate.

**Verified:** 2026-05-18T13:10:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Phase Success Criteria post-D-01 / D-03)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | With zero users, `/setup` accepts username+password and creates an admin user; concurrent `/setup` POSTs produce exactly one row because of `SELECT … FOR UPDATE` on `app_settings.setup_completed`; once true, the route responds `302 → /login` | VERIFIED | `app/services/setup.py` runs `select(AppSetting).where(...).with_for_update()` + atomic INSERT + UPDATE + single commit. `tests/services/test_setup.py::test_for_update_atomic` asserts SQL stream contains "FOR UPDATE" on app_settings, INSERT users before UPDATE, exactly 1 COMMIT. `tests/services/test_setup.py::test_create_first_admin_race_lost` returns None when flag is 'true'. `tests/routers/test_auth.py::test_setup_concurrent_race` uses asyncio.gather + asserts exactly 1 user row + sorted Locations == ["/", "/login"]. `tests/routers/test_auth.py::test_setup_blocked_after_completion` flips flag, GET→303→/login, POST→303→/login. Code uses 303 (See Other) not literally 302; intent met (redirect to /login). Tests all pass. |
| 2 | `/login` accepts credentials, sets a `session_id` cookie with `HttpOnly`, `Secure`, `SameSite=Lax`, signed by `APP_SECRET_KEY`, and 30-day max-age; refresh on activity bumps `sessions.last_seen` | VERIFIED | `app/services/sessions.py::build_session_cookie` returns `session_id={signed_value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000` (2_592_000 = 30 days). `app/signing.py::sign_session_id` uses `itsdangerous.URLSafeSerializer(APP_SECRET_KEY, salt='session')`. `tests/routers/test_auth.py::test_session_cookie_attributes` asserts all 5 attributes (HttpOnly, Secure, SameSite=Lax, Max-Age=2592000, Path=/). `app/middleware/session.py` runs `refresh_last_seen` when elapsed > REFRESH_THRESHOLD_SECONDS (300s) — write-throttled per T-04-06. |
| 3 | Successful login deletes the previous `sessions` row and mints a fresh `session_id` (session-fixation defense) | VERIFIED | `app/services/sessions.py::regenerate_session(db, current_session_id, user_id)` does `delete(Session).where(Session.session_id == current_session_id)` then INSERT new UUID + single commit. `app/routers/auth.py::login_submit` calls `regenerate_session(db, prior_session_id, user.id)`. `tests/routers/test_auth.py::test_session_fixation_defense` proves old session row is DELETEd from DB AND new cookie value differs from pre-set. `test_preset_cookie_does_not_inherit` proves attacker's signed-but-revoked cookie value never appears as new session value. |
| 4 | Hitting `/admin` as a non-admin returns 403; as an admin returns 200 (stub). Logout deletes the session row and unsets the cookie | VERIFIED | `app/dependencies/auth.py::require_admin` raises 403 when `user is None or not user.is_admin`. `app/routers/admin.py` uses `user: User = Depends(require_admin)` (Form 1). `app/templates/pages/admin.html` renders literal "Admin (stub) — wiring lands in Phase 9." `tests/routers/test_admin.py` 4 tests cover anon→403, non-admin→403, admin→200, stub body literal. `app/routers/auth.py::logout_submit` calls `delete_session(db, session.session_id)` + emits `build_session_clear_cookie()` (Max-Age=0). `tests/routers/test_auth.py::test_logout_clears_session` proves 303→/login, Max-Age=0 in Set-Cookie, DB row DELETEd. |
| 5 | Smoke pass: cold container → `/setup` → auto-login → see `/` page with "Signed in as <username>" footer | VERIFIED | `tests/test_phase02_smoke.py::test_cold_container_through_login` walks GET /setup → POST /setup → 303 to / with session_id Set-Cookie → GET / with cookie shows "Signed in as smoketest" + `/logout` form → POST /logout → 303 to /login + Max-Age=0 → GET / (no session) shows "Sign in" link. Test passes. `app/templates/pages/index.html` line 8-16 implements footer with `{% if request.state.user %}` branching to `request.state.user.username` (D-09 User-row attribute access). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/auth.py` | argon2-cffi PasswordHasher singleton + hash_password + verify_password + dummy_verify | VERIFIED | Module-level `_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)`. `_DUMMY_HASH` precomputed once at import time. Three public functions match interface. `tests/services/test_auth.py` 4 tests pass (roundtrip, params, dummy_verify timing, invalid-hash handling). |
| `app/services/setup.py` | create_first_admin async transaction (SELECT FOR UPDATE + INSERT + UPDATE + one commit) | VERIFIED | `with_for_update()` on AppSetting, `db.add(User(... is_admin=True, is_active=True))`, flush, UPDATE app_settings, single commit. Returns User on success, None on race. is_admin/is_active service-enforced (not in signature). |
| `app/dependencies/__init__.py` | package marker | VERIFIED | Single-line docstring present. |
| `app/dependencies/db.py` | get_async_session FastAPI dep | VERIFIED | Lazy-imports `async_session_factory` from app.main inside the generator body (avoids circular import). `inspect.isasyncgenfunction(get_async_session) == True`. |
| `app/dependencies/auth.py` | require_user (401) and require_admin (403) | VERIFIED | require_user raises 401 when `request.state.user is None`. require_admin raises 403 when `user is None or not user.is_admin` (folds anon into 403 per D-13). Both exported in `__all__`. `tests/dependencies/test_auth.py` 5 tests pass. |
| `app/csrf.py::CSRFFormFieldShim` | Pure-ASGI middleware hoisting X-CSRF-Token form field to header | VERIFIED | Class appended to existing app/csrf.py. Behavior gates 1-4 (non-HTTP/non-POST/header-present/non-form-content) pass through. Step 5 buffers body via receive-replay pattern, parses form/multipart for X-CSRF-Token field, mutates scope["headers"]. `tests/middleware/test_csrf_form_shim.py` 5 D-15 tests pass (GET passthrough, header passthrough, form-field hoist, multipart byte-preservation, JSON passthrough). Mounted in app/main.py AFTER CSRFMiddleware. |
| `app/middleware/session.py` (D-09 + D-10) | Loads User row + fail-closed on deleted/inactive | VERIFIED | Lines 189-213 replaced the Phase-1 stub. Local import `from app.models.user import User`. Queries `select(User).where(User.id == session_row.user_id)`. D-10 branch `if user_row is None or not user_row.is_active` deletes session, sets clear_cookie, state.user = None. `tests/middleware/test_session.py::test_state_user_shape` proves `isinstance(state.user, User)`. `test_deactivated_user_fail_closed` proves clear-cookie + DB row deleted. `test_deleted_user_fail_closed` skipped with explanatory text (FK CASCADE prevents true orphan state; the OR-branch is exercised by the inactive test). |
| `app/routers/auth.py` | Real /setup + /login + /logout handlers | VERIFIED | GET/POST /setup, GET/POST /login, POST /logout. Pre-flight setup_completed check before argon2 cost (RESEARCH Open Q5). D-07 generic error re-render (200 + "Invalid username or password."). D-15 logging contract: user_not_found has no user_id/attempted_username; bad_password has user_id. D-12 POST-only /logout. dummy_verify called on user-not-found AND inactive AND ValidationError branches for symmetric timing. RedirectResponse(status_code=303) for all redirects. |
| `app/routers/admin.py` | GET /admin gated by require_admin | VERIFIED | Single route, Form 1 dependency (`user: User = Depends(require_admin)`). Renders pages/admin.html with literal body. |
| `app/routers/debug.py` (D-14) | /debug/proxy wrapped in require_admin | VERIFIED | Lines 22-26: decorator carries `dependencies=[Depends(require_admin)]` (Form 2). Module docstring updated to reflect D-14. Route body unchanged. `tests/routers/test_debug_proxy.py::test_debug_proxy_admin_only` proves three-state gate. |
| `app/schemas/auth.py` | SetupForm + LoginForm Pydantic v2 | VERIFIED | SetupForm: username regex `^[A-Za-z0-9_-]{3,32}$`, EmailStr, password min_length=12. LoginForm: loose 1-32 username, min_length=1 password (intentional — see module docstring on enumeration defense). |
| `app/templates/pages/setup.html` | First-admin form with CSRF hidden field | VERIFIED | extends base.html, `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">`, username/email/password fields with HTML5 validation. |
| `app/templates/pages/login.html` | Sign-in form with CSRF + username repop | VERIFIED | extends base.html, CSRF hidden input, username value repopulated via `{{ username or '' }}`, error display block. |
| `app/templates/pages/admin.html` | 5-line stub per D-13 | VERIFIED | extends base.html, literal body "Admin (stub) — wiring lands in Phase 9." (Unicode em-dash). |
| `app/templates/pages/index.html` | Footer: Signed-in-as / Sign-in branch | VERIFIED | Lines 7-17. `{% if request.state.user %}` branches between "Signed in as {{ request.state.user.username }}" + Sign-out POST form vs "Sign in" link. Attribute access (D-09 contract). |
| `app/main.py` (wiring) | CSRFFormFieldShim + admin_router included | VERIFIED | Line 74: `from app.csrf import CSRFFormFieldShim, csrf_middleware_kwargs`. Line 84: `from app.routers import admin as admin_router`. Lines 187-192: middleware add-order per D-15 (Session → CSRFMiddleware → CSRFFormFieldShim → FragmentCache → SecurityHeaders → RequestContext). Line 198: `app.include_router(admin_router.router)`. Docstring middleware-order block has 6 entries with rationale. |
| `tests/test_phase02_smoke.py` | Cold-container E2E | VERIFIED | 137-line single-test file walks the full Phase-2 happy path. Passes. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| POST /setup happy path | create_first_admin + regenerate_session + sign_session_id + build_session_cookie | RedirectResponse(303) with Set-Cookie | WIRED | app/routers/auth.py:202-211 chains these calls. |
| POST /login wrong-user | dummy_verify | called BEFORE response rendering | WIRED | app/routers/auth.py:284 calls dummy_verify(form.password). Inactive-user (line 304) and ValidationError (line 261) branches also call dummy_verify. |
| POST /logout | delete_session + build_session_clear_cookie | 303 to /login + Set-Cookie | WIRED | app/routers/auth.py:383-391. |
| SessionMiddleware → User row | select(User).where(User.id == session_row.user_id) | local import, same async session | WIRED | app/middleware/session.py:189-194. |
| /admin → require_admin | request.state.user.is_admin | Depends(require_admin) Form 1 | WIRED | app/routers/admin.py:33. |
| /debug/proxy → require_admin | Depends(require_admin) Form 2 | decorator dependencies=[...] | WIRED | app/routers/debug.py:25. |
| index.html footer → request.state.user | `{% if request.state.user %}` + .username attribute | D-09 contract | WIRED | app/templates/pages/index.html:8-9. |
| CSRFFormFieldShim → CSRFMiddleware | scope["headers"] mutation before CSRFMiddleware runs | mounted AFTER CSRFMiddleware in add order | WIRED | app/main.py:187-189. Shim runs JUST BEFORE CSRFMiddleware on request path (Starlette reverse-of-add). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| pages/index.html footer | request.state.user.username | SessionMiddleware D-09 lookup of User row by session.user_id | YES — SELECT from users by indexed PK | FLOWING |
| pages/admin.html | (literal text only) | n/a — no dynamic data this phase | n/a (stub) | FLOWING (literal) |
| /setup form POST | username/email/password | request.form() → Pydantic SetupForm | YES — values flow through to INSERT users + commit | FLOWING |
| /login form POST | username/password | request.form() → Pydantic LoginForm → SELECT users + argon2 verify | YES — db.execute(select(User)) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full Phase-2 test suite green | `docker compose exec -T coffee-snobbery python -m pytest` | 79 passed, 2 skipped, 10 xfailed, 0 failed | PASS |
| Phase-2 smoke test passes | `docker compose exec -T coffee-snobbery python -m pytest tests/test_phase02_smoke.py -v` | 1 passed | PASS |
| Auth router tests pass | `docker compose exec -T coffee-snobbery python -m pytest tests/routers/test_auth.py -v` | 12 passed | PASS |
| Admin router tests pass | `docker compose exec -T coffee-snobbery python -m pytest tests/routers/test_admin.py -v` | 4 passed | PASS |
| Debug-proxy admin gate tests pass | `docker compose exec -T coffee-snobbery python -m pytest tests/routers/test_debug_proxy.py -v` | 2 passed, 1 xfailed (TestClient-shadowed ProxyHeaders) | PASS |
| Setup service tests pass (FOR UPDATE atomic) | `docker compose exec -T coffee-snobbery python -m pytest tests/services/test_setup.py -v` | 5 passed | PASS |
| Session middleware D-09/D-10 tests pass | `docker compose exec -T coffee-snobbery python -m pytest tests/middleware/test_session.py -v` | 3 passed, 1 skipped (FK CASCADE), 2 xfailed (TestClient-shadowed) | PASS |
| D-15 logging assertions on real /login | `docker compose exec -T coffee-snobbery python -m pytest tests/test_logging.py -v` | 7 passed | PASS |
| CSRF form-field shim tests pass | `docker compose exec -T coffee-snobbery python -m pytest tests/middleware/test_csrf_form_shim.py -v` | 5 passed | PASS |
| Live HTTP: `/admin` returns 403 | `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/admin` | 404 | FAIL (live server is stale; see human_verification) |
| Live HTTP: `/debug/proxy` returns 403 to anon | `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/debug/proxy` | 200 (no auth required) | FAIL (live server is stale; see human_verification) |

The live-server probes fail because uvicorn was started before the Phase-2 code was docker-cp'd in. The on-disk code is correct; the served HTTP surface is stale. Restarting the container resolves it.

### Probe Execution

No bash probes declared in PLAN or SUMMARY artifacts. Phase-2 verification is pytest-based, executed above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AUTH-01 | 02-01, 02-05, 02-07, 02-10, 02-11 | First-run /setup creates initial admin; subsequent visits redirect to /login | SATISFIED | tests/routers/test_auth.py::{test_setup_happy_path, test_setup_blocked_after_completion} + tests/test_phase02_smoke.py + service-level tests in test_setup.py |
| AUTH-02 | 02-01, 02-05, 02-07 | /setup uses SELECT FOR UPDATE on app_settings to prevent races | SATISFIED | tests/services/test_setup.py::test_for_update_atomic (SQL stream contains FOR UPDATE + single COMMIT) + test_create_first_admin_race_lost + tests/routers/test_auth.py::test_setup_concurrent_race (asyncio.gather, exactly 1 user) |
| AUTH-03 | 02-02, 02-07 | /login accepts user+password; no public registration | SATISFIED | tests/routers/test_auth.py::{test_login_happy_path, test_login_wrong_password, test_no_register_route} + app/services/auth.py dummy_verify symmetry |
| AUTH-04 | 02-02 | argon2id (m=64MB, t=3, p=4) | SATISFIED | tests/services/test_auth.py::test_password_hasher_params asserts _ph._memory_cost=65536, _time_cost=3, _parallelism=4, _type=Type.ID. test_argon2_roundtrip + tests/services/test_setup.py::test_create_first_admin_uses_hashed_password assert $argon2id$v=19$m=65536,t=3,p=4$ prefix |
| AUTH-06 | 02-07 | Session cookie HttpOnly + Secure + SameSite=Lax + APP_SECRET_KEY-signed | SATISFIED | tests/routers/test_auth.py::test_session_cookie_attributes asserts all 5 attributes. app/services/sessions.py::build_session_cookie returns the literal string. app/signing.py uses APP_SECRET_KEY. |
| AUTH-07 | 02-06, 02-07, 02-10 | Session ID regenerated on login/logout/admin-toggle | SATISFIED | tests/routers/test_auth.py::{test_session_fixation_defense, test_preset_cookie_does_not_inherit, test_logout_clears_session} prove old session row DELETEd + new UUID + cookie value differs. app/services/sessions.py::regenerate_session does atomic delete+insert. |
| AUTH-09 | 02-01, 02-03, 02-08, 02-09 | Admin section gated by is_admin; 403 otherwise | SATISFIED | tests/routers/test_admin.py 4 tests cover three states (anon/non-admin/admin). tests/routers/test_debug_proxy.py::test_debug_proxy_admin_only covers /debug/proxy gate (D-14). app/dependencies/auth.py::require_admin folds anon→403 per D-13. |

All 7 declared requirements satisfied with code + test evidence. No orphaned requirements: REQUIREMENTS.md Phase Coverage Summary lists "Phase 2 — Auth: 7 (AUTH-01, 02, 03, 04, 06, 07, 09)" — all 7 are claimed by Phase-2 plans (AUTH-05, AUTH-08, AUTH-10 are owned by Phase 1).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| app/services/sessions.py | 185 | `# Phase 8 TODO: schedule a periodic` | Info | Documented forward reference to Phase 8's expired-session sweep job (per CONTEXT D-09 / deferred list). Not a debt marker requiring closure — explicit roadmap pointer. |
| app/templates/pages/admin.html | 6 | Literal text "(stub)" + "wiring lands in Phase 9" | Info | Intentional per CONTEXT D-13 + ROADMAP SC #4 ("as an admin returns 200 (stub)"). Not a stub-flag for verification purposes; it's the locked Phase-2 deliverable. |

No blockers. No warnings beyond the deployment-hygiene note routed to human verification.

### Human Verification Required

#### 1. Restart container to clear stale uvicorn process

**Test:** Run `docker compose restart coffee-snobbery`, then `curl -i http://127.0.0.1:8080/admin` and `curl -i http://127.0.0.1:8080/debug/proxy`.

**Expected:** `/admin` returns 403; `/debug/proxy` returns 403 (both without an admin cookie). Then with an admin cookie obtained via /setup → /, both routes are reachable per the test suite contract.

**Why human:** The container has been up 15 hours (PID 1 started 2026-05-17 22:28 UTC), but the Phase-2 source files were docker cp'd in AFTER that (file mtimes 2026-05-18 01:38–02:34 UTC for app/main.py and Phase-2 router files). The on-disk code is correct (verified by the full pytest suite passing inside the container), but the served HTTP surface is the Phase-1 stub: live curls confirm `/admin`→404 (route not in the loaded routing table) and `/debug/proxy`→200 (no admin gate applied). This is a deployment-hygiene gap, not a code defect — a restart resolves it. Recommend documenting "after docker cp, restart the service" in the operator runbook.

#### 2. Mobile-first 375px visual smoke

**Test:** Open Chromium devtools, set viewport to 375×667, load /setup, /login, /admin (as admin), and / (signed-in + signed-out).

**Expected:** No horizontal scroll. Form inputs render at ≥16px (no iOS focus-zoom). Cream surfaces with espresso accents from the Phase 0 Tailwind palette. Sign-out form button + "Signed in as <username>" wrap cleanly.

**Why human:** Templates use the locked Tailwind utility classes (`mx-auto max-w-prose px-6 py-12`, `bg-espresso-900 text-cream-50`) but actual visual conformance — palette correctness, tap-target sizing, no horizontal scroll, font-size on inputs — requires a browser. CLAUDE.md mobile-first invariant: "any UI change tested at 375px viewport before being declared done." Out of scope for grep/test verification.

#### 3. Container-only housekeeping: drop the duplicate dependencies/dependencies/ folder

**Test:** Inside the container: `docker compose exec coffee-snobbery rm -rf /app/app/dependencies/dependencies/`.

**Expected:** `ls /app/app/dependencies/` shows only `__init__.py auth.py db.py __pycache__` — no nested `dependencies/` subdir.

**Why human:** Cosmetic docker-cp artifact (the host filesystem is clean — only the container has the nested copy). Does NOT affect imports (Python resolves `app.dependencies.auth` from the outer module first), but is housekeeping noise that should be cleaned before the next deploy snapshot. Operator decides whether to drop it now or rebuild the image.

### Gaps Summary

No code gaps. All 5 ROADMAP success criteria are satisfied by the on-disk codebase and verified by passing tests. The single live-server issue is operational (uvicorn started before the Phase-2 code was hot-copied in) and is fully addressed by `docker compose restart coffee-snobbery`. Two additional human items are mobile UI conformance (always needs human) and a docker-cp housekeeping artifact.

---

_Verified: 2026-05-18T13:10:00Z_
_Verifier: Claude (gsd-verifier)_
