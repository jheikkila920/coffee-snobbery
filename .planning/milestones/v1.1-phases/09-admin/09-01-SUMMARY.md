---
phase: "09"
plan: "01"
subsystem: admin
tags: [admin, routing, templates, events, testing, security]
dependency_graph:
  requires: []
  provides:
    - app.routers.admin package with prefix=/admin hub route + import-guarded sub-router includes
    - app/templates/admin_base.html persistent section nav layout
    - app/templates/pages/admin.html hub page extending admin_base.html
    - home.html is_admin-gated Admin link (D-03)
    - New admin.* audit event constants in app/events.py
    - tests/phase_09/ collectable suite with self-seeding fixtures
  affects:
    - app/main.py (admin_router.router import unchanged; package resolves identically)
    - app/templates/pages/home.html (Admin link added to header)
tech_stack:
  added: []
  patterns:
    - Sub-package router with importlib-based import guards for feature sub-modules
    - admin_base.html template chain: sub-pages extend admin_base extends base.html
    - Self-seeding Phase 9 test fixtures using asyncio.run + async_session_factory
key_files:
  created:
    - app/routers/admin/__init__.py
    - app/templates/admin_base.html
    - tests/phase_09/__init__.py
    - tests/phase_09/conftest.py
    - tests/phase_09/test_admin_security.py
  modified:
    - app/templates/pages/admin.html (extends admin_base.html, hub card grid)
    - app/templates/pages/home.html (is_admin-gated Admin link in header)
    - app/events.py (5 new admin.* constants + __all__)
    - .planning/phases/09-admin/09-VALIDATION.md (nyquist_compliant + wave_0_complete)
  deleted:
    - app/routers/admin.py (converted to package; intentional deletion)
decisions:
  - "Admin router uses prefix=/admin on the package router; hub route is GET '' (relative empty path)"
  - "import-guarded sub-router include loop swallows ImportError — feature plans create module files, never edit __init__.py"
  - "admin_base.html fills block content from base.html; defines block admin_content for sub-pages"
  - "Home page Admin link placed inside a flex wrapper alongside Log session button for clean layout at 375px"
  - "test_csrf_required skips via guarded skip (no POST routes yet) — not a false pass"
metrics:
  duration: "5 minutes"
  completed: "2026-05-21T22:44:07Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 5
  files_modified: 4
  files_deleted: 1
---

# Phase 09 Plan 01: Admin Foundation Summary

**One-liner:** Admin router sub-package with import-guarded feature sub-routers, shared admin_base.html section nav, is_admin-gated home link, new audit event constants, and self-seeding Wave 0 test fixtures.

## What Was Built

### Task 1: Admin router sub-package + layout + home link
Converted the Phase 2 stub `app/routers/admin.py` into a sub-package `app/routers/admin/__init__.py`. The hub route `GET /admin` uses `prefix="/admin"` on the router so sub-routes are path-additive. Five feature sub-routers are included via an `importlib.import_module` loop with `try/except ImportError` guards — the hub ships working before any feature plan runs, and Plans 09-02..09-06 only need to create their module files.

Created `app/templates/admin_base.html` extending `base.html`, filling `block content` with a persistent section nav (Users | Credentials | Settings | Backups | System) using `flex flex-wrap gap-2` for mobile-first collapse at 375px (D-01/D-02). Sub-pages fill `block admin_content`.

Updated `pages/admin.html` to extend `admin_base.html` with a card grid hub page. Added is_admin-gated Admin anchor to `pages/home.html` header (D-03) inside a flex wrapper alongside the Log session button.

The `main.py` import `from app.routers import admin as admin_router` resolves identically to the package's `__init__.py` — no main.py changes needed.

### Task 2: Admin audit event constants
Added five new constants to `app/events.py` admin.* block: `ADMIN_USER_UPDATED`, `ADMIN_USER_DEACTIVATED`, `ADMIN_BACKUP_TRIGGERED`, `ADMIN_AI_REFRESH_TRIGGERED`, `ADMIN_PROVIDER_TEST`. Each added to `__all__` in alphabetical position. All six existing constants preserved unchanged.

### Task 3: Phase 9 Wave 0 test scaffolding (TDD)
Created `tests/phase_09/` package with:
- `conftest.py`: self-seeding fixtures extending root conftest — `admin_session`, `regular_session`, `user_with_brews` (coffee + brew_session seed for D-15 block tests), `user_no_brews` (D-15 succeed tests), `user_with_sessions` (2 live sessions for toggle-invalidation), `two_admins`, `single_admin`. Zero pytest.skip on missing seed data.
- `test_admin_security.py`: `test_non_admin_403` (GREEN), `test_unauthenticated_not_200` (GREEN), `test_admin_200` (GREEN), `test_csrf_required` (guarded skip — no POST routes yet).

Flipped `09-VALIDATION.md` frontmatter to `nyquist_compliant: true` + `wave_0_complete: true`.

## Verification Results

```
tests/phase_09/test_admin_security.py::TestRequireAdmin::test_non_admin_403 PASSED
tests/phase_09/test_admin_security.py::TestRequireAdmin::test_unauthenticated_not_200 PASSED
tests/phase_09/test_admin_security.py::TestRequireAdmin::test_admin_200 PASSED
tests/phase_09/test_admin_security.py::TestCsrf::test_csrf_required SKIPPED (guarded: no POST routes yet)
3 passed, 1 skipped — no /admin assertion skips in -rs summary
```

Container started healthy after rebuild. `import app.main` succeeded with `['/admin']` in route list.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The hub page, section nav, and home link are fully functional. Feature sub-pages (Plans 09-02..09-06) are the intended next step.

## Threat Flags

No new threat surface beyond what the plan's threat model covers. The `require_admin` gate is proven by `test_non_admin_403` and `test_admin_200`.

## Self-Check: PASSED

- app/routers/admin/__init__.py — FOUND (created)
- app/templates/admin_base.html — FOUND (created)
- tests/phase_09/test_admin_security.py — FOUND (created)
- Commit 0bb7e2f — FOUND (Task 1)
- Commit b24719f — FOUND (Task 2)
- Commit 40977d6 — FOUND (Task 3)
