---
phase: "09"
plan: "05"
subsystem: admin
tags: [admin, backups, file-io, security, path-traversal, tdd]
dependency_graph:
  requires:
    - app.routers.admin (09-01 sub-package + import guard)
    - app.services.backup (run_backup, BackupResult, ArtifactResult)
    - app.events.ADMIN_BACKUP_TRIGGERED (09-01)
    - app.dependencies.auth.require_admin
    - app.templates.admin_base.html (09-01)
  provides:
    - GET /admin/backups — backup file list (size + timestamp)
    - GET /admin/backups/{filename} — admin-gated FileResponse, strict filename + resolve containment
    - POST /admin/backups/run — sync def handler calling run_backup in threadpool
    - pages/admin_backups.html + fragments/admin_backup_list.html + fragments/admin_backup_result.html
  affects:
    - app/routers/admin/__init__.py (auto-includes backups via import guard — no edit needed)
tech_stack:
  added: []
  patterns:
    - FileResponse + dual path-traversal defense (regex FIRST + Path.resolve().is_relative_to())
    - Sync def run-now handler (FastAPI threadpool; never blocks event loop or APScheduler)
    - hx-swap-oob for file-list refresh after run-now
    - _prime_csrf helper for CSRF-compliant POST tests (from test_admin_users pattern)
key_files:
  created:
    - app/routers/admin/backups.py
    - app/templates/pages/admin_backups.html
    - app/templates/fragments/admin_backup_list.html
    - app/templates/fragments/admin_backup_result.html
  modified:
    - tests/phase_09/test_admin_backups.py (RED commit + GREEN update)
decisions:
  - "Backup filename regex is module-level constant (monkeypatchable by tests); same for _BACKUP_DIR"
  - "run_backup_now is sync def — D-07 constraint; FastAPI routes sync handlers to threadpool automatically"
  - "hx-swap-oob in admin_backup_result.html refreshes #admin-backup-list so file list updates without page reload"
  - "Test uses monkeypatch on app.services.backup.run_backup to avoid real pg_dump in container tests"
  - "_prime_csrf helper follows Phase 4/9 pattern: GET /admin/backups first to get csrftoken cookie"
metrics:
  duration: "7 minutes"
  completed: "2026-05-21T23:22:02Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 1
---

# Phase 09 Plan 05: Admin Backups Page Summary

**One-liner:** Admin backups page with file listing (size + timestamp), per-file FileResponse download with strict regex + resolve-containment path-traversal defense, and a sync-def "Run backup now" button calling the shared run_backup service.

## What Was Built

### Task 1: Backup list page + admin-gated download (TDD RED + GREEN)

**RED phase (commit c7c6b2a):** Created `tests/phase_09/test_admin_backups.py` with the full ADMIN-04 test suite — 14 tests covering list, empty-state, download (valid sql + tar.gz), path traversal (encoded + raw), non-admin 403, missing-file 404, sync-def assertion, and run-now fragment rendering. All failed before implementation (router returned 404 — module didn't exist).

**GREEN phase:** Created `app/routers/admin/backups.py` with:

- `_BACKUP_DIR = Path("/app/data/backups")` + `_BACKUP_FILENAME_RE` as module-level constants (monkeypatchable by tests per the photos.py pattern note in RESEARCH.md).
- `GET /backups` — sync def, disk-walks `_BACKUP_DIR`, collects (filename, size, mtime) for regex-matching files sorted newest-first. HTMX branch returns the list fragment; full-page returns the page template.
- `GET /backups/{filename}` — dual path-traversal defense: (1) strict regex check; (2) `Path.resolve().is_relative_to(_BACKUP_DIR.resolve())`; (3) `is_file()`. `media_type` is `application/gzip` for `.gz`, `application/octet-stream` for `.sql`.
- `POST /backups/run` — sync def (D-07). Calls `run_backup(db, by_user_id=user.id)` from the service layer, emits `ADMIN_BACKUP_TRIGGERED` with `user_id` only, then renders the result fragment with an hx-swap-oob refresh of `#admin-backup-list`.

Created templates:
- `pages/admin_backups.html` — extends `admin_base.html`; Run backup now form + `#backup-result-mount` + `#admin-backup-list`.
- `fragments/admin_backup_list.html` — iterates files with filename/size/mtime and a download link; empty-state when list is empty.
- `fragments/admin_backup_result.html` — status badge (ok/error), db + photos artifact cards, duration/pruned-count, plus hx-swap-oob to refresh the file list.

### Task 2: "Run backup now" handler (no separate commit — merged into Task 1 implementation)

The `run_backup_now` handler and `admin_backup_result.html` were implemented as part of the single GREEN commit. The TDD RED test already covered the run-now behavior.

## Verification Results

```
tests/phase_09/test_admin_backups.py - 14 passed, 0 skips
tests/phase_09/ (full suite) - 47 passed, 0 skips
```

Container rebuilt successfully. Import guard in `__init__.py` auto-included `backups` router on restart. Routes registered at `/admin/backups`, `/admin/backups/{filename}`, `/admin/backups/run`.

## Deviations from Plan

None — plan executed exactly as written.

One deviation from test approach (Rule 1 auto-fix): The initial `test_run_backup_now_returns_result_fragment` used `client.cookies.get("csrftoken", "dummy")` to pass the CSRF token, which doesn't work because the test client needs the double-submit-cookie pattern (csrftoken cookie + matching X-CSRF-Token header). Added `_prime_csrf` helper following the established `test_admin_users._prime_csrf` pattern — GET /admin/backups first to get the real csrftoken cookie, then set both the cookie and header on the client instance.

## Known Stubs

None. All three routes are fully functional and wired.

## Threat Flags

No new threat surface beyond what the plan's threat model covers. The path-traversal defense is tested by `test_download_path_traversal_encoded` and `test_download_path_traversal_raw`.

## Self-Check: PASSED

- app/routers/admin/backups.py — FOUND (created)
- app/templates/pages/admin_backups.html — FOUND (created)
- app/templates/fragments/admin_backup_list.html — FOUND (created)
- app/templates/fragments/admin_backup_result.html — FOUND (created)
- tests/phase_09/test_admin_backups.py — FOUND (modified)
- Commit c7c6b2a — FOUND (RED: test suite)
- Commit 3a4bcc6 — FOUND (GREEN: implementation)
