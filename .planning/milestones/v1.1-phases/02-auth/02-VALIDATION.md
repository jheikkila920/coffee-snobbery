---
phase: 2
slug: auth
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-17
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from `02-RESEARCH.md` § Validation Architecture; paths normalized to the
> project's mirror-of-app test layout (Phase 1 convention: `tests/<module>/test_<file>.py`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0 + pytest-asyncio (auto mode) + httpx 0.28 (`TestClient` for sync routes, `AsyncClient` for the AUTH-02 concurrent-race test) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (already configured in Phases 0+1) |
| **Quick run command** | `docker compose exec coffee-snobbery pytest -x tests/services/test_auth.py tests/services/test_setup.py tests/middleware/test_session.py tests/middleware/test_csrf_form_shim.py tests/routers/test_auth.py tests/routers/test_admin.py tests/dependencies/test_auth.py` |
| **Full suite command** | `docker compose exec coffee-snobbery pytest -x` |
| **Estimated runtime** | ~10s for targeted Phase-2 subset; ~60s for full suite (concurrent-setup test dominates) |

---

## Sampling Rate

- **After every task commit:** Run the per-file targeted command for the file just changed (e.g., `pytest -x tests/services/test_auth.py`)
- **After every plan wave:** Run the Phase-2 quick command (full Phase-2 subset, ~10s)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10s on per-task; 60s on full

---

## Per-Task Verification Map

> Plan-phase wires task IDs (`02-PP-TT`) into the table once `02-PP-PLAN.md` files exist.
> Each requirement below lists the test that proves it; the plan tasks must each emit
> at least one row in this table (or inherit one) before `nyquist_compliant: true`.

| Requirement / Decision | Test File (new ✱ / existing ◆) | Test Function | Test Type | Automated Command |
|------------------------|--------------------------------|---------------|-----------|-------------------|
| AUTH-01 happy path | `tests/routers/test_auth.py` ✱ | `test_setup_happy_path` | integration | `pytest -x tests/routers/test_auth.py::test_setup_happy_path` |
| AUTH-01 blocked-after-setup | `tests/routers/test_auth.py` ✱ | `test_setup_blocked_after_completion` | integration | `pytest -x tests/routers/test_auth.py::test_setup_blocked_after_completion` |
| AUTH-02 concurrent race (TWO POSTs → exactly ONE user row) | `tests/routers/test_auth.py` ✱ | `test_setup_concurrent_race` | integration (asyncio.gather + AsyncClient) | `pytest -x tests/routers/test_auth.py::test_setup_concurrent_race` |
| AUTH-02 FOR UPDATE held across INSERT+UPDATE in one TX | `tests/services/test_setup.py` ✱ | `test_for_update_atomic` | unit (transaction-state assert) | `pytest -x tests/services/test_setup.py::test_for_update_atomic` |
| AUTH-03 no public `/register` route | `tests/routers/test_auth.py` ✱ | `test_no_register_route` | integration (assert 404) | `pytest -x tests/routers/test_auth.py::test_no_register_route` |
| AUTH-03 happy login | `tests/routers/test_auth.py` ✱ | `test_login_happy_path` | integration | `pytest -x tests/routers/test_auth.py::test_login_happy_path` |
| AUTH-03 wrong password | `tests/routers/test_auth.py` ✱ | `test_login_wrong_password` | integration | `pytest -x tests/routers/test_auth.py::test_login_wrong_password` |
| AUTH-03 unknown user + dummy-verify timing | `tests/services/test_auth.py` ✱ | `test_dummy_verify_timing` | unit (wall-clock floor) | `pytest -x tests/services/test_auth.py::test_dummy_verify_timing` |
| AUTH-04 argon2id roundtrip + format | `tests/services/test_auth.py` ✱ | `test_argon2_roundtrip` | unit | `pytest -x tests/services/test_auth.py::test_argon2_roundtrip` |
| AUTH-04 PasswordHasher params (`m=65536, t=3, p=4`) | `tests/services/test_auth.py` ✱ | `test_password_hasher_params` | unit | `pytest -x tests/services/test_auth.py::test_password_hasher_params` |
| AUTH-06 session cookie attributes (HttpOnly/Secure/SameSite=Lax/Max-Age=2592000/signed) | `tests/routers/test_auth.py` ✱ | `test_session_cookie_attributes` | integration | `pytest -x tests/routers/test_auth.py::test_session_cookie_attributes` |
| AUTH-07 prior session row deleted + new ID on login (fixation defense) | `tests/routers/test_auth.py` ✱ | `test_session_fixation_defense` | integration | `pytest -x tests/routers/test_auth.py::test_session_fixation_defense` |
| AUTH-07 pre-set cookie does NOT inherit new authenticated session | `tests/routers/test_auth.py` ✱ | `test_preset_cookie_does_not_inherit` | integration | `pytest -x tests/routers/test_auth.py::test_preset_cookie_does_not_inherit` |
| AUTH-07 logout deletes session row + clears cookie | `tests/routers/test_auth.py` ✱ | `test_logout_clears_session` | integration | `pytest -x tests/routers/test_auth.py::test_logout_clears_session` |
| AUTH-09 `/admin` three states (anon→401 OR 403 / non-admin→403 / admin→200) | `tests/routers/test_admin.py` ✱ | `test_admin_gate_three_states` | integration | `pytest -x tests/routers/test_admin.py::test_admin_gate_three_states` |
| AUTH-09 `/debug/proxy` admin-only (Phase 1 D-16 follow-through via D-14) | `tests/routers/test_debug_proxy.py` ◆ (extend) | `test_debug_proxy_admin_only` | integration | `pytest -x tests/routers/test_debug_proxy.py::test_debug_proxy_admin_only` |
| `require_admin` dependency raises 403 directly | `tests/dependencies/test_auth.py` ✱ | `test_require_admin_unit` | unit | `pytest -x tests/dependencies/test_auth.py::test_require_admin_unit` |
| D-09 `request.state.user` is `User` (not dict) on authenticated path | `tests/middleware/test_session.py` ◆ (extend) | `test_state_user_shape` | integration | `pytest -x tests/middleware/test_session.py::test_state_user_shape` |
| D-10 `is_active=false` → next request clears cookie + deletes session row | `tests/middleware/test_session.py` ◆ (extend) | `test_deactivated_user_fail_closed` | integration | `pytest -x tests/middleware/test_session.py::test_deactivated_user_fail_closed` |
| D-10 deleted-user row → next request clears cookie + deletes session row | `tests/middleware/test_session.py` ◆ (extend) | `test_deleted_user_fail_closed` | integration | `pytest -x tests/middleware/test_session.py::test_deleted_user_fail_closed` |
| D-15 `CSRFFormFieldShim` — header already present passthrough | `tests/middleware/test_csrf_form_shim.py` ✱ | `test_header_passthrough` | integration | `pytest -x tests/middleware/test_csrf_form_shim.py::test_header_passthrough` |
| D-15 `CSRFFormFieldShim` — form-encoded POST hoists `X-CSRF-Token` field to header | `tests/middleware/test_csrf_form_shim.py` ✱ | `test_form_field_hoisted` | integration | `pytest -x tests/middleware/test_csrf_form_shim.py::test_form_field_hoisted` |
| D-15 `CSRFFormFieldShim` — multipart POST body preserved byte-for-byte | `tests/middleware/test_csrf_form_shim.py` ✱ | `test_multipart_body_preserved` | integration | `pytest -x tests/middleware/test_csrf_form_shim.py::test_multipart_body_preserved` |
| D-15 `CSRFFormFieldShim` — GET passthrough untouched | `tests/middleware/test_csrf_form_shim.py` ✱ | `test_get_passthrough` | integration | `pytest -x tests/middleware/test_csrf_form_shim.py::test_get_passthrough` |
| D-15 `CSRFFormFieldShim` — JSON content-type passthrough (header is the client's job) | `tests/middleware/test_csrf_form_shim.py` ✱ | `test_json_passthrough` | integration | `pytest -x tests/middleware/test_csrf_form_shim.py::test_json_passthrough` |
| CSRF block — POST `/login` without the cookie+header pair → 403 | `tests/routers/test_auth.py` ✱ | `test_login_csrf_blocked` | integration | `pytest -x tests/routers/test_auth.py::test_login_csrf_blocked` |
| CSRF block — POST `/logout` without the cookie+header pair → 403 | `tests/routers/test_auth.py` ✱ | `test_logout_csrf_blocked` | integration | `pytest -x tests/routers/test_auth.py::test_logout_csrf_blocked` |
| Phase 1 D-15 logging — `auth.login_failed reason=user_not_found` carries NO `attempted_username` | `tests/test_logging.py` ◆ (extend) | `test_login_failed_no_username_on_user_not_found` | unit (structlog capsys) | `pytest -x tests/test_logging.py::test_login_failed_no_username_on_user_not_found` |
| Phase 1 D-15 logging — `auth.login_failed reason=bad_password` carries `user_id` | `tests/test_logging.py` ◆ (extend) | `test_login_failed_includes_user_id_on_bad_password` | unit (structlog capsys) | `pytest -x tests/test_logging.py::test_login_failed_includes_user_id_on_bad_password` |
| D-13 `/admin` stub literal body | `tests/routers/test_admin.py` ✱ | `test_admin_stub_body` | integration | `pytest -x tests/routers/test_admin.py::test_admin_stub_body` |
| Smoke — cold container → `/setup` → `/login` → see `/` with "Signed in as <username>" | `tests/test_phase02_smoke.py` ✱ | `test_cold_container_through_login` | integration | `pytest -x tests/test_phase02_smoke.py` |

*Test file status: ✱ NEW (Wave 0) · ◆ EXISTS (extend in-place)*

---

## Wave 0 Requirements

> Wave 0 = test scaffolding that MUST exist before any task in this phase declares
> `<automated>` coverage. The planner sequences these as the first wave so subsequent
> task commits have a real test target.

- [ ] `tests/services/test_auth.py` — NEW; argon2 hash/verify, dummy_verify timing
- [ ] `tests/services/test_setup.py` — NEW; FOR UPDATE atomic, race fixture
- [ ] `tests/routers/test_auth.py` — NEW; replaces `tests/routers/test_auth_stub.py` (delete the stub file in the same plan that creates this one)
- [ ] `tests/routers/test_admin.py` — NEW; admin-gate three states + stub body
- [ ] `tests/dependencies/test_auth.py` — NEW; `require_admin` unit test (creates the `tests/dependencies/` package directory with `__init__.py`)
- [ ] `tests/middleware/test_csrf_form_shim.py` — NEW; D-15 shim five cases
- [ ] `tests/test_phase02_smoke.py` — NEW; cold-container E2E
- [ ] `tests/middleware/test_session.py` — EXTEND (add D-09 / D-10 cases)
- [ ] `tests/routers/test_debug_proxy.py` — EXTEND (admin-gate wrap)
- [ ] `tests/test_logging.py` — EXTEND (D-15 reason-field assertions for the new real handlers)
- [ ] `tests/conftest.py` — EXTEND with:
  - `async_client` fixture (`httpx.AsyncClient` against the ASGI app — required by AUTH-02 concurrent-race test)
  - `fresh_db` fixture (truncate `users` + reset `app_settings.setup_completed = "false"` per-test — required by AUTH-01 / AUTH-02 / setup-flow tests)
  - `seeded_admin_user` fixture (creates an `is_admin=true` user + logs them in via cookie — required by AUTH-09 admin-state tests)
  - `seeded_regular_user` fixture (creates an `is_admin=false` user + logs them in — required by AUTH-09 non-admin test)

*If Wave 0 is incomplete, no task may claim `<automated>` verification. Plan-phase
must place these files in the first wave (typically `02-01-PLAN.md`).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Setup form renders at 375px viewport without horizontal scroll; bottom-padding clears the iOS Safari URL bar | CLAUDE.md mobile-first invariant | Visual; automated viewport tests not in scope for Phase 2 | Open `http://localhost:8000/setup` in Chrome DevTools 375×667 emulation; submit valid creds; confirm 303 → `/` and footer shows "Signed in as …" |
| Login form renders at 375px viewport without horizontal scroll | CLAUDE.md mobile-first invariant | Visual | Same as above for `/login` |
| `/admin` stub renders extending `base.html` (CSP nonce attached, no console errors) | D-13 + CSP enforcement | Visual + DevTools console check | Login as admin; visit `/admin`; open DevTools console; confirm zero CSP violations |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s on full suite
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
