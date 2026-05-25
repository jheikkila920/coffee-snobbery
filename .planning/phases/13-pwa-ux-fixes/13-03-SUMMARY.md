---
phase: 13-pwa-ux-fixes
plan: "03"
subsystem: routers/templates
tags: [htmx, fragments, equipment, coffees, C2, C3, D-03, D-04, tdd]
dependency_graph:
  requires: []
  provides: [correct-create-fragment-responses, equipment-pill-cards]
  affects: [equipment-list, coffee-list, mobile-card-layout]
tech_stack:
  added: []
  patterns: [htmx-list-fragment-on-create, flex-wrap-pill-cards]
key_files:
  created:
    - tests/routers/test_equipment_create_fragment.py
  modified:
    - app/routers/equipment.py
    - app/routers/coffees.py
    - app/templates/fragments/equipment_row.html
    - app/templates/fragments/equipment_form.html
    - app/templates/fragments/coffee_form.html
    - tests/phase_04/test_routers_equipment.py
    - tests/phase_04/test_routers_coffees.py
decisions:
  - "create handlers return the full list fragment so sort/group order is preserved and the form collapses via the hx-target swap (D-04) — no OOB hack needed"
  - "hx-target change lives in the form fragment templates (equipment_form.html, coffee_form.html), not the page templates, because the form sets its own POST target"
  - "Phase 4 tests asserting old OOB behavior updated as Rule 1 auto-fix (not a new plan)"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_changed: 7
---

# Phase 13 Plan 03: C2 + C3 Create Fragment Fix Summary

Equipment and coffee create routes now return the full list fragment on success; equipment mobile cards use flex-wrap pills.

## What Was Built

### Task 1: RED tests (test_equipment_create_fragment.py)
Two TDD RED tests established the correct contract before any fix:
- `test_equipment_create_returns_list_fragment` — POST /equipment must return list-container markup, no `equipment-form-mount` OOB div
- `test_coffee_create_returns_list_fragment` — POST /coffees must return list-container markup, no `coffee-form-mount` OOB div

Both used the `_authed_client` + `_prime_csrf` pattern from `test_brew_router.py` and LIKE-scoped cleanup to prevent cross-module catalog FK pollution.

### Task 2: Equipment fix (GREEN — equipment test)
- `app/routers/equipment.py`: `create_equipment` success branch now calls `list_equipment_grouped_by_type` and returns `fragments/equipment_list.html` with `{"groups": groups, "include_archived": False}`
- `app/templates/fragments/equipment_form.html`: create mode `form_target` changed from `#equipment-form-mount` to `#equipment-list`
- `app/templates/fragments/equipment_row.html`: card mode replaced one-field-per-line with `flex flex-wrap gap-2` pill div containing type + usage_count pills (C3); `include_oob_form_clear` block removed entirely (C2)

### Task 3: Coffee fix (GREEN — both tests)
- `app/routers/coffees.py`: `create_coffee` success branch now rebuilds the full list context (calls `list_coffees`, resolves `flavor_note_names` + `roaster_name_map` across all rows) and returns `fragments/coffee_list.html`
- `app/templates/fragments/coffee_form.html`: create mode `form_target` changed from `#coffee-form-mount` to `#coffee-list`

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 29973bf | test | RED: C2 regression tests for equipment + coffee create fragments |
| 04bb715 | feat | GREEN: fix equipment create route + C3 pill card (C2/C3/D-03/D-04) |
| b21d825 | feat | GREEN: fix coffee create route + form target (C2/D-03/D-04) |
| c64787d | fix | Rule 1: update phase_04 create tests to match corrected behavior |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Phase 4 tests asserted old OOB form-clear behavior**
- **Found during:** Full-suite run after Task 3
- **Issue:** `tests/phase_04/test_routers_equipment.py::test_create_valid_brewer` and `tests/phase_04/test_routers_coffees.py::test_create_coffee_minimal_valid` both asserted `equipment-form-mount` / `coffee-form-mount` was present in the response — testing the old broken behavior that Plan 13-03 fixed
- **Fix:** Updated both assertions to check for list-container markers (`space-y-3` or `hidden md:block`) and assert absence of the form-mount OOB div — matching the corrected behavior
- **Files modified:** `tests/phase_04/test_routers_equipment.py`, `tests/phase_04/test_routers_coffees.py`
- **Commit:** c64787d

**2. [Rule 2 - Note] hx-target lives in form fragment, not page template**
- **Found during:** Task 2 implementation
- The plan description mentioned changing `hx-target` in `equipment.html` and `coffees.html` page templates, but the HTMX `hx-target` for the create form POST is actually set in `equipment_form.html` and `coffee_form.html` (the form fragments themselves via a Jinja variable). The page template only contains the "Add equipment" button that GETs the form fragment into the mount div. Fixed in the correct location.

## Known Stubs

None. All routes return real data from the database.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

Files created:
- tests/routers/test_equipment_create_fragment.py: EXISTS
- All modified files verified via git status

Commits verified:
- 29973bf (RED test): EXISTS
- 04bb715 (equipment GREEN): EXISTS
- b21d825 (coffee GREEN): EXISTS
- c64787d (phase_04 test fix): EXISTS

Test results: 2/2 C2 regression tests GREEN, 944 pass / 2 skipped / 10 xfailed in full suite (the 2 failures from phase_04 resolved by the Rule 1 fix commit).
