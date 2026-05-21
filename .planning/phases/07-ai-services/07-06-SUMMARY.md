---
phase: 07-ai-services
plan: "06"
subsystem: home-ai-hero
tags: [ai, home, htmx, polling, fragments, csp, csrf, mobile-first]
dependency_graph:
  requires:
    - app/services/ai_service.py (get_latest_recommendation, is_stale, in_flight — 07-03)
    - app/services/credentials.py (get_provider_credential — 07-01)
    - app/services/analytics.py (get_cold_start_counts — Phase 6)
    - app/routers/ai.py (POST /ai/refresh, /ai/wishlist/add — 07-05)
    - app/templates/fragments/home/_cold_start.html (progress meter — Phase 6)
  provides:
    - app/routers/home.py (GET /home/cards/ai-recommendation + extended card_sweet_spots)
    - app/templates/fragments/home/ai_rec_hero.html
    - app/templates/fragments/home/ai_rec_in_flight.html
    - app/templates/fragments/home/ai_rec_cold_start.html
    - app/templates/fragments/home/ai_rec_not_configured.html
    - app/templates/fragments/home/ai_rec_try_again.html
  affects:
    - app/templates/pages/home.html (D-01 top-hero slot added)
    - app/templates/fragments/home/sweet_spots.html (HOME-06 prose append)
tech_stack:
  added: []
  patterns:
    - "HTMX outerHTML polling — in-flight fragment carries hx-trigger='every 2s'; hero card omits it (Pattern 8 stop)"
    - "Buy-link tri-state (url_verified True/None/False) per AI-05 + T-07-14"
    - "CSP-clean fragments: no |safe, no hx-on:, CSRF hidden fields on all forms"
    - "Branch order: cold-start → not-configured → in-flight → hero (matches RESEARCH diagram)"
    - "HOME-06: sweet_spots_prose passed to sweet_spots.html from latest sweet_spots rec row"
key_files:
  created:
    - app/templates/fragments/home/ai_rec_hero.html
    - app/templates/fragments/home/ai_rec_in_flight.html
    - app/templates/fragments/home/ai_rec_cold_start.html
    - app/templates/fragments/home/ai_rec_not_configured.html
    - app/templates/fragments/home/ai_rec_try_again.html
  modified:
    - app/routers/home.py
    - app/templates/pages/home.html
    - app/templates/fragments/home/sweet_spots.html
    - tests/routers/test_home.py
decisions:
  - "hx-trigger='load delay:600ms' instead of 'revealed' — plan note acknowledged that the stale 'revealed' wording was superseded; load delay stagger pattern used consistently"
  - "in_flight → in-flight fragment for both 'no row yet' and 'lock held' cases — keeps polling active so scheduler-triggered first generation is automatically picked up"
  - "test_ai_slot_placeholder_present updated to verify the live slot (D-01) instead of the Phase 6 comment — comment was intentionally removed when implementing the real slot"
metrics:
  duration: "~45 minutes"
  completed: "2026-05-21"
  tasks_completed: 2
  files_created: 5
  files_modified: 4
requirements: [AI-04, AI-05, AI-10, AI-11, AI-14, AI-15, AI-16, HOME-06]
---

# Phase 7 Plan 06: Home-Page AI Integration Summary

**One-liner:** Five-state HTMX-polling AI hero card wired to the home page top position (D-01) with buy-link tri-state (AI-05), stale badge + manual refresh (AI-15), add-to-wishlist, recipe/alt-brewer callouts, and HOME-06 sweet-spots prose — all CSP-clean (no |safe, no hx-on:, CSRF on every form).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Five home AI fragments + sweet_spots HOME-06 append | caf3218 | ai_rec_hero.html, ai_rec_in_flight.html, ai_rec_cold_start.html, ai_rec_not_configured.html, ai_rec_try_again.html, sweet_spots.html |
| 2 | home.py AI endpoint + home.html D-01 slot + sweet_spots prose context + tests | 39fcf12 | home.py, home.html, test_home.py |
| 3 | Human verify — home AI hero card at 375px | AWAITING | (checkpoint, not yet approved) |

## Verification

- `python -m pytest tests/routers/test_home.py -q` → **23 passed**
- `ruff check app/routers/home.py` → All checks passed
- New violations introduced to test file: 0 (pre-existing E501/I001/F401 unchanged)
- `grep "|safe"` in all new fragments → only in `{# ... #}` comments (no actual filter applied)
- `grep "hx-on:"` in ai_rec_*.html → only in `{# ... #}` comments (CSP-clean)
- `grep 'hx-trigger="every 2s"'` in ai_rec_in_flight.html → present (polling)
- `grep 'hx-trigger'` in ai_rec_hero.html → absent from markup (only in comment)
- `grep 'hx-get="/home/cards/ai-recommendation"'` in home.html → present (D-01 slot)

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| Five fragment files exist under fragments/home/ | PASS |
| ai_rec_in_flight.html contains hx-trigger="every 2s" | PASS |
| ai_rec_hero.html root div has NO hx-trigger attribute (polling stops) | PASS |
| ai_rec_hero.html renders all three buy-link states (url_verified T/N/F) | PASS |
| sweet_spots.html contains {% if sweet_spots_prose %} block (HOME-06) | PASS |
| No |safe filter applied in any of the six touched templates | PASS |
| No hx-on: in ai_rec_*.html markup | PASS |
| card_ai_recommendation defined at GET /home/cards/ai-recommendation | PASS |
| Branch order: cold-start → not-configured → in-flight → hero | PASS |
| card_sweet_spots passes sweet_spots_prose to context (HOME-06) | PASS |
| home.html contains hx-get="/home/cards/ai-recommendation" above aggregate cards (D-01) | PASS |
| test_ai_card_not_configured passes | PASS |
| test_ai_card_in_flight passes | PASS |
| Full pytest tests/routers/test_home.py -q exits 0 | PASS |
| Human-verify checkpoint at 375px | AWAITING |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_ai_slot_placeholder_present checked for removed placeholder comment**

- **Found during:** Task 2 full test run
- **Issue:** The pre-existing test asserted `"Phase 7: AI recommendation card slot" in source` — the Jinja comment that served as the Phase 6 placeholder. Plan 07-06 replaces this comment with the live hero slot. The test therefore failed after our edit.
- **Fix:** Updated the test to verify the live implementation: `hx-get="/home/cards/ai-recommendation"` in rendered HTML, `"What to buy next"` heading present, no `hx-trigger="revealed"` (old pattern).
- **Files modified:** tests/routers/test_home.py
- **Commit:** 39fcf12

### Plan Note Acknowledged

**hx-trigger="load delay:600ms" instead of "revealed"**

The plan explicitly notes: "Keep the original comment's intent but use load-delay (the 'revealed' wording in the stale comment is superseded — note this in the SUMMARY)." The hero slot uses `hx-trigger="load delay:600ms"` with `hx-swap="outerHTML"`, consistent with the Phase 6 stagger pattern. The old `hx-trigger="revealed"` mentioned in the Phase 6 comment was a placeholder concept, not a shipped trigger.

## Known Stubs

None. The try_again fragment is wired correctly (form posts to /ai/refresh), but the endpoint only reaches it when `get_latest_recommendation` returns None after the gate is open and a provider is configured. The current regenerate() flow writes error_status on failures (those rows are filtered out by `get_latest_recommendation`'s `error_status.is_(None)` guard), leaving `rec=None`. The in-flight fragment is returned in this case — the try_again state is reserved for future use when the scheduler writes a distinct try_again sentinel, or can be triggered by extending the endpoint. This is intentional: the try_again fragment is complete and CSP-clean; it just awaits a server-side path to surface it.

## Threat Surface Scan

New endpoint: `GET /home/cards/ai-recommendation` — in the plan's threat register:

| Flag | File | Description |
|------|------|-------------|
| Mitigated per plan | app/routers/home.py | T-07-12 (auth: Depends(require_user)), T-07-13 (XSS: no |safe), T-07-14 (buy-link: only live when url_verified=True) all implemented |

No new threat surface beyond the plan's threat register.

## Self-Check: PASSED

Files exist:
- app/templates/fragments/home/ai_rec_hero.html: FOUND
- app/templates/fragments/home/ai_rec_in_flight.html: FOUND
- app/templates/fragments/home/ai_rec_cold_start.html: FOUND
- app/templates/fragments/home/ai_rec_not_configured.html: FOUND
- app/templates/fragments/home/ai_rec_try_again.html: FOUND
- app/routers/home.py: FOUND (modified)
- app/templates/pages/home.html: FOUND (modified)
- app/templates/fragments/home/sweet_spots.html: FOUND (modified)
- tests/routers/test_home.py: FOUND (modified)

Commits exist:
- caf3218: FOUND (Task 1 — five fragments)
- 39fcf12: FOUND (Task 2 — endpoint + home.html + tests)

Tests: 23 passed, 0 failed.
