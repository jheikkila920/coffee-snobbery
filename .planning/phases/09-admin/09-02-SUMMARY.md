---
phase: 09-admin
plan: "02"
subsystem: admin-user-management
tags: [admin, users, csrf, d15, d16, tdd, session-invalidation]
dependency_graph:
  requires: [09-01]
  provides: [ADMIN-01]
  affects: [users, sessions, brew_sessions]
tech_stack:
  added: []
  patterns:
    - D-15 hard-delete guard (brew count + RESTRICT FK backstop)
    - D-16 last-admin/self-lockout guard (SELECT FOR UPDATE in transaction)
    - T-09-04 async bulk session eviction on privilege change
    - CSRFFormFieldShim + await request.form() on every write handler
    - Admin READ handlers sync def, WRITE handlers async def
key_files:
  created:
    - app/routers/admin/users.py
    - app/schemas/admin_user.py
    - app/templates/pages/admin_users.html
    - app/templates/fragments/admin_user_list.html
    - app/templates/fragments/admin_user_row.html
    - app/templates/fragments/admin_user_form.html
    - app/templates/fragments/admin_error.html
    - app/templates/fragments/admin_user_deleted.html
  modified:
    - tests/phase_09/test_admin_users.py
decisions:
  - D-16 uses SELECT COUNT(*) ... FOR UPDATE to prevent last-admin race (Pitfall 7); self-lockout guard checks target_id == acting admin id
  - async def for all write handlers (mandatory await request.form() for CSRFFormFieldShim; session eviction via async_session_factory)
  - _delete_user_sessions imports async_session_factory inside the function to avoid circular import at module load
  - CSRF test pattern fixed to client-level cookie+header (canonical Phase 4/5 pattern from test_brew_router)
  - D-15 returns 409 + admin_error.html fragment; RESTRICT FK is the DB backstop if count guard is bypassed
  - password hash never passed to template context; edit form has no password value prefill
metrics:
  duration_minutes: 30
  completed_date: "2026-05-21"
  tasks_completed: 2
  files_created: 9
  files_modified: 1
  tests_passed: 10
  tests_skipped: 0
---

# Phase 9 Plan 02: Admin User Management Summary

ADMIN-01 user management with D-15 hard-delete guard, D-16 last-admin/self-lockout, and T-09-04 immediate session eviction via argon2id hashing and async bulk delete.

## What Was Built

Full ADMIN-01 user management surface at `/admin/users`:

- **List/create/edit** — GET /admin/users, /admin/users/new, /admin/users/{id}/edit
- **Create** — POST /admin/users with argon2id hashing, 12-char password floor, duplicate-username 200 re-render
- **Update** (edit save) — POST /admin/users/{id}; optional password reset via AdminPasswordReset; D-16 guard when demoting is_admin
- **Toggle admin** — POST /admin/users/{id}/toggle-admin; D-16 guard + immediate session eviction (T-09-04)
- **Deactivate/reactivate** — POST /admin/users/{id}/deactivate with D-16 self-lockout + last-admin guard + session eviction; POST /admin/users/{id}/reactivate (no guard needed)
- **Hard-delete** — POST /admin/users/{id}/delete; D-15 brew count guard + D-16 guard + session eviction + RESTRICT FK backstop

Schemas: `AdminUserCreate` (username 3-32, password min 12, email optional, is_admin=False) and `AdminPasswordReset` (password min 12), both `extra="forbid"`.

Templates: page + list fragment + row fragment + create/edit form with mandatory CSRF hidden field + error fragment + empty deleted fragment.

## TDD Gate Compliance

RED gate commit: `d9df347` — `test(09-02): add failing tests for admin user management ADMIN-01`
GREEN gate commit: `4231bec` — `feat(09-02): implement ADMIN-01 user management (GREEN)`

All 10 tests pass, 0 skips.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| d9df347 | test | RED: add failing tests for admin user management ADMIN-01 |
| 4231bec | feat | GREEN: implement ADMIN-01 user management (schemas, handlers, templates) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CSRF test pattern: per-request cookies did not satisfy double-submit-cookie**
- **Found during:** Task 1 verification (test_create_user_short_password got 403 instead of 200)
- **Issue:** Initial test helper passed `cookies=admin_session` on each POST, which only sent session_id. The double-submit-cookie pattern requires BOTH csrftoken cookie AND X-CSRF-Token header on the same request. Per-request cookies kwarg only provides one.
- **Fix:** Rewrote `_prime_csrf(client, signed_cookie)` to set cookies on the client instance (not per-request): (1) set session_id cookie, (2) GET /admin/users to mint csrftoken, (3) set csrftoken on client.cookies, (4) set X-CSRF-Token on client.headers. Canonical pattern from test_brew_router.py.
- **Files modified:** tests/phase_09/test_admin_users.py
- **Commit:** 4231bec (included in GREEN commit alongside implementation)

**2. [Rule 2 - Missing safety] CSRF hidden field initially missing from admin_user_form.html**
- **Found during:** Task 1 template creation review
- **Issue:** Without `<input type="hidden" name="X-CSRF-Token" value="...">`, every POST from the form would fail CSRFMiddleware before reaching the handler (T-09-09).
- **Fix:** Added the mandatory CSRF hidden field per the CSRFFormFieldShim pattern (already required by plan, confirmed present in final template).
- **Files modified:** app/templates/fragments/admin_user_form.html

## Test Results

```
tests/phase_09/test_admin_users.py ..........   10 passed, 0 skips
```

Tests cover:
- `TestListUsers`: list with admin session (200 + username present), non-admin 403
- `TestCreateUserValidation`: 11-char password rejected with error fragment at 200
- `TestCreateUser`: argon2id hash stored, plaintext absent from response, row returned
- `TestDeleteUserGuards`: D-15 block (user with brews), D-15 allow (empty user), D-16 last-admin, D-16 self-deactivation
- `TestToggleAdmin`: sessions deleted post-toggle (count == 0)
- `TestDeactivateRequiresCsrf`: no-CSRF 403, with-CSRF 200 + sessions deleted

## Known Stubs

None. All handlers return real data; no placeholder text or hardcoded empty values in templates.

## Threat Surface Scan

All threats from the plan's threat model are mitigated:

| Threat | Mitigation | Test |
|--------|-----------|------|
| T-09-04 session not invalidated on privilege change | _delete_user_sessions on toggle/deactivate/delete | test_toggle_admin_invalidates_sessions, test_deactivate_requires_csrf |
| T-09-05 last-admin lockout | _count_active_admins FOR UPDATE + self-id check | test_delete_last_admin_blocked, test_self_demote_blocked |
| T-09-06 hard-delete cascades brew history | brew count guard + RESTRICT FK backstop | test_delete_user_with_sessions_blocked |
| T-09-07 IDOR on target user_id | user_id from path param only + require_admin | all write handler tests |
| T-09-08 password hash/plaintext in response | edit form never renders password_hash | test_create_user (plaintext absent check) |
| T-09-09 CSRF on mutations | CSRFFormFieldShim + hidden field + await request.form() | test_deactivate_requires_csrf |

No new threat surface introduced beyond the plan's registered threats.

## Self-Check: PASSED

All 9 created files exist. Both commits (d9df347, 4231bec) confirmed in git log.
