---
phase: "16"
plan: "02"
subsystem: cafe-logs
tags: [crud, router, pydantic, idor-defense, mass-assignment, sec-06, csrf, tests]
dependency_graph:
  requires: [16-01]
  provides: [cafe-log-service-layer, cafe-logs-router, cafe-log-tests]
  affects: [app/main.py, brew-tab-16-04]
tech_stack:
  added: []
  patterns: [SEC-06-validation-rerender, IDOR-sentinel-404, POST+_method=DELETE, skip-gate-pattern]
key_files:
  created:
    - app/schemas/cafe_log.py
    - app/services/cafe_logs.py
    - app/routers/cafe_logs.py
    - tests/services/test_cafe_logs.py
    - tests/routers/test_cafe_logs.py
  modified:
    - app/main.py
decisions:
  - "photo field added to _NON_SCHEMA_FORM_KEYS to prevent UploadFile reaching Pydantic extra=forbid"
  - "logged_at omitted from update_fields when None to preserve existing NOT NULL value"
  - "6 template-dependent router tests skip on missing pages/cafe_log_form.html (16-03 lands it)"
metrics:
  duration: "~45 min (continuation session)"
  completed: "2026-05-27"
  tasks: 4
  files: 6
---

# Phase 16 Plan 02: /cafe-logs Router + Service Layer Summary

Pydantic schemas, service CRUD, /cafe-logs router (5 routes + origin-country autocomplete), and registration in main.py. Full test pair: 11 service tests + 13 router tests. All code lint-clean under ruff.

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | CafeLogCreate/Update schemas + cafe_logs service | 11f7131 | Done |
| 2 | /cafe-logs router (5 routes + autocomplete) + main.py | 6f793f8 | Done |
| 3 | Service + router test pair | c8b6c47 | Done |
| 4 | Lint clean gate (ruff format + check, all 6 files) | c8b6c47 | Done |

## What Was Built

**Task 1 — Schema + Service**

`app/schemas/cafe_log.py`: `CafeLogCreate` / `CafeLogUpdate` (subclass) with `ConfigDict(extra="forbid")`, `Decimal` rating (0-5, 0.25 steps via `multiple_of`), no `user_id` or `photo_filename` fields (T-16-02-01 mass-assignment defense).

`app/services/cafe_logs.py`: five CRUD functions with kwargs-after-`*` API, all scoped by `by_user_id`. IDOR sentinel: `get`/`update` return `None`; `delete` returns `False` for non-owned rows. `_WRITABLE_FIELDS` frozenset excludes `user_id`. No equipment counters, no flavor-notes sync, no audit events (all No-at-v1 per CONTEXT).

**Task 2 — Router**

`app/routers/cafe_logs.py`: `APIRouter(prefix="/cafe-logs")`. Five routes in declaration order (literals before `/{cafe_log_id}` — Starlette route-order gotcha):
- `GET /new` — create-mode form (requires 16-03 template)
- `GET /origin-country-autocomplete` — merges DB distinct + 19 seeded countries, no `+ Create new`
- `POST /` — create; ValidationError → 200 re-render (SEC-06)
- `GET /{id}/edit` — edit-mode form with existing values; `?layout=desktop` for D-21 dual-button
- `POST /{id}` — update or `_method=DELETE` branch (HTMX 2.x convention)

`_NON_SCHEMA_FORM_KEYS` includes `"photo"`, `"layout"`, `"_method"`, autocomplete query fields.
`_hydrate_form_context` dispatches D-21 HTMX target/swap based on `mode` + `layout`.
Success path: `Response(status_code=204, headers={"HX-Redirect": "/brew?tab=cafe"})`.

`app/main.py`: `cafe_logs_router` registered adjacent to `brew_router`.

**Task 3 — Tests**

`tests/services/test_cafe_logs.py`: 11 tests, real Postgres + `_require_cafe_logs_table` skip gate. Covers create minimal/full, get owner/cross-user, list rating/date filter + DESC sort, update owner/cross-user, delete owner/cross-user. All 11 pass.

`tests/routers/test_cafe_logs.py`: 13 tests (matching 16-VALIDATION.md exact names). 7 pass now (create minimal/full, mass-assignment rejected, rating OOR, cross-user 404, update/delete own/cross-user, autocomplete). 6 skip on missing `pages/cafe_log_form.html` — those tests require plan 16-03's template and are gated by `_require_cafe_log_form_template()`.

**Task 4 — Lint gate**

All 6 plan files pass `ruff format --check` and `ruff check` with zero warnings.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `photo` UploadFile trips `extra=forbid` before photo handling**
- **Found during:** Task 3 test run (`test_photo_rejection_paths`)
- **Issue:** `_parse_form_payload` iterates `form_data.multi_items()` and included the `photo` UploadFile in `schema_input`. `CafeLogCreate(extra="forbid")` raised `ValidationError` with an `UploadFile` value before the photo handling code could run.
- **Fix:** Added `"photo"` to `_NON_SCHEMA_FORM_KEYS` so it is stripped from `schema_input`. Router reads it directly from `form_data` after schema validation.
- **Files modified:** `app/routers/cafe_logs.py`
- **Commit:** c8b6c47

**2. [Rule 1 - Bug] Update with blank `logged_at` sets NULL, violating NOT NULL constraint**
- **Found during:** Task 3 test run (`test_update_own_succeeds`)
- **Issue:** `update_fields` always included `logged_at: form.logged_at`, which is `None` when the date input is omitted. The `update_cafe_log` service then wrote `NULL` to a NOT NULL column.
- **Fix:** `logged_at` is only added to `update_fields` when `form.logged_at is not None` — blank date input on update preserves the stored value.
- **Files modified:** `app/routers/cafe_logs.py`
- **Commit:** c8b6c47

**3. [Rule 2 - Correctness] Template-dependent router tests need skip gate**
- **Found during:** Task 3 test run
- **Issue:** 6 router tests that render `pages/cafe_log_form.html` raised `TemplateNotFound` because plan 16-03 has not run yet. Without a skip gate, these would show as errors rather than deferred-dependency skips.
- **Fix:** Added `_require_cafe_log_form_template()` skip gate checking for the template path. These tests will activate automatically when 16-03 lands the template.
- **Files modified:** `tests/routers/test_cafe_logs.py`
- **Commit:** c8b6c47

## Test Results

```
tests/services/test_cafe_logs.py: 11 passed
tests/routers/test_cafe_logs.py:   7 passed, 6 skipped (template pending 16-03)
Total:                            18 passed, 6 skipped, 0 failed
```

Skipped tests will activate when plan 16-03 lands `pages/cafe_log_form.html`.

## Known Stubs

None. All routes wire to real service functions. The origin-country autocomplete returns
real DB data merged with a seeded country list. No placeholder text or hardcoded empty
responses in the plan-critical paths.

## Threat Flags

None. No new network endpoints beyond the 5 declared in the plan. All endpoints are
auth-gated via `require_user`. IDOR defense applied throughout. No new trust-boundary
crossings.

## Self-Check: PASSED

All 5 key files present in worktree. All 3 task commits verified in git log.
- app/schemas/cafe_log.py: FOUND
- app/services/cafe_logs.py: FOUND
- app/routers/cafe_logs.py: FOUND
- tests/services/test_cafe_logs.py: FOUND
- tests/routers/test_cafe_logs.py: FOUND
- Commit 11f7131: FOUND
- Commit 6f793f8: FOUND
- Commit c8b6c47: FOUND
