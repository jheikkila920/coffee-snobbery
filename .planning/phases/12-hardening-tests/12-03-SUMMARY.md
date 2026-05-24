---
phase: 12-hardening-tests
plan: "03"
subsystem: tests
tags: [test, smoke, happy-path, e2e, csrf, session]
dependency_graph:
  requires: [12-01]
  provides: [TEST-01]
  affects: []
tech_stack:
  added: []
  patterns:
    - "CSRF triple-send idiom (form field + header + cookie) on every POST"
    - "HTML ID regex extraction for created entity IDs from HTMX row fragments"
    - "_require_wired() hard-fail gate under SNOB_CI=1"
key_files:
  created:
    - tests/test_happy_path_smoke.py
  modified: []
decisions:
  - "Mirror per-request cookies= pattern from test_phase02_smoke.py (pre-existing deprecation warning; not introduced by this plan)"
  - "Detect roaster/coffee/equipment/recipe IDs via regex on response HTML (id='<prefix>-<N>' convention from row templates)"
  - "Assert cold-start progressbar presence (role=progressbar) rather than AI prose, since AI is unconfigured in tests"
metrics:
  duration_minutes: 12
  completed_date: "2026-05-23"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 1
---

# Phase 12 Plan 03: TEST-01 Happy Path Smoke Summary

Single end-to-end smoke covering setup → roaster → coffee → equipment → recipe → brew session → home page, using the production CSRF + session path with hard-fail semantics under SNOB_CI=1.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | TEST-01 end-to-end happy-path smoke | 0095d25 | tests/test_happy_path_smoke.py |

## What Was Built

`tests/test_happy_path_smoke.py` — one test (`test_happy_path_full_chain`) that drives:

1. **Setup bootstrap** — GET /setup → csrftoken → POST /setup → 303 → extract session_id (mirrors Phase 2 smoke exactly)
2. **POST /roasters** — creates "Smoke Roasters"; parses `id="roaster-<N>"` from HTML response
3. **POST /coffees** — creates "Smoke Blend" referencing the roaster (Ethiopia/washed/light)
4. **POST /equipment** x3 — creates brewer (Hario V60), grinder (Comandante C40), kettle (Brewista Artisan)
5. **POST /recipes** — creates "Smoke V60" with a JSON steps array (bloom + main pour)
6. **POST /brew** — logs a session with all FK references; asserts **204 + HX-Redirect: /brew** (not 200)
7. **GET /** — asserts 200 + `"Recent brews"` always-on section + cold-start progress meter (`role="progressbar"`)

Every POST uses the CSRF triple-send idiom (form field + header + cookie) and refreshes the token from each response cookie before the next request. The session cookie is carried throughout via `_cookies()` helper.

## Verification

- `SNOB_CI=1 pytest tests/test_happy_path_smoke.py -rs -x` → **1 passed** (run twice consecutively, both green)
- Full suite `SNOB_CI=1 pytest tests/ --ignore=tests/e2e -rs -q` → **938 passed, 2 skipped, 10 xfailed** (same pre-existing skip/xfail baseline as before this plan)

## Deviations from Plan

None — plan executed exactly as written.

The per-request `cookies=` Starlette deprecation warning appears in output. This is a pre-existing pattern throughout the test suite (present in `test_phase02_smoke.py`, `test_auth.py`, etc.) — not introduced by this plan. The plan explicitly instructs to extend the existing idiom.

## Known Stubs

None. The test creates real DB entities and exercises the real application path.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes introduced — this plan adds test-only code.

## Self-Check

### Files exist:
- `tests/test_happy_path_smoke.py` — FOUND

### Commits exist:
- `0095d25` feat(12-03): add TEST-01 happy-path end-to-end smoke — FOUND

## Self-Check: PASSED
