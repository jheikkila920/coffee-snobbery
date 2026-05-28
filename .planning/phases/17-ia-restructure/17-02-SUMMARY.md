---
phase: 17-ia-restructure
plan: 02
subsystem: home-page / analytics
tags: [ia-restructure, home-composition, top-coffees, greeting, analytics, tdd]
requires: [Phase 16 brew-header Quick rate (D-09); APP_TIMEZONE setting (Phase 8)]
provides:
  - analytics.get_top_coffees(min_sessions int = 2) keyword-only param (no-floor variant)
  - app.routers.home.derive_greeting(username, *, now=None) helper
  - pages/home.html greeting + 3-button action row + Recent brews + Not tried yet + eager Top Coffees + See-AI link + Wishlist card
  - DIST-07 banner placeholder comment in home.html (plan 17-03 swaps in live include)
affects:
  - app/services/analytics.py (HAVING clause conditional on min_sessions > 0)
  - app/routers/home.py (home_shell context greeting, top_coffees, top_coffees_all_unrated)
  - app/templates/pages/home.html (full composition rewrite)
  - tests/services/test_analytics.py (3 new no-floor tests + seed helper)
  - tests/routers/test_home.py (7 home composition tests + 13 derive_greeting bucket tests; 4 stale Phase 6/7 tests removed)
  - tests/test_happy_path_smoke.py (D-11 fixup assert Top Coffees heading, not cold-start meter)
tech-stack:
  added: []
  patterns: [server-side time-of-day greeting via APP_TIMEZONE, keyword-only conditional HAVING clause, eager template include with with-forwarded context]
key-files:
  created: []
  modified:
    - app/services/analytics.py
    - app/routers/home.py
    - app/templates/pages/home.html
    - tests/services/test_analytics.py
    - tests/routers/test_home.py
    - tests/test_happy_path_smoke.py
metrics:
  duration: ~30 minutes
  tasks: 5
  files_changed: 6
  tests_added_net: 25
  tests_removed_stale: 4
  completed: 2026-05-27
---

# Phase 17 Plan 02: Home Composition Rewrite Summary

Strip every AI surface and the cold-start meter from pages/home.html, add a personalized server-side greeting, render Top Coffees eagerly with a new no-floor variant, replace the AI hero + AI tools blocks with a single See-AI-recommendations link + a Wishlist card. Implements IA-03 / IA-04 / IA-06 + D-06..D-11.

## What changed (composition of pages/home.html)

Before (Phase 6/7): Home H1 + Admin/Guided-Brew/Log-session action row + Recent brews + Not tried yet + cold-start gate branch (below-gate: progress meter; above-gate: AI hero + AI tools + Top Coffees lazy + Preference Profile lazy + Top Flavor Descriptors lazy + Sweet Spots lazy).

After (Phase 17 / Plan 02):
1. DIST-07 banner Jinja-comment placeholder (plan 17-03 swap target).
2. Personalized greeting H1 (Good morning/afternoon/evening, USER) from server-side derive_greeting.
3. Action row: Guided Brew + Log session + Quick rate (no Admin button; symmetric with /brew header from Phase 16 D-09).
4. Recent brews (eager include, unchanged).
5. Not tried yet (lazy /home/cards/unrated-coffees, unchanged).
6. Top Coffees (EAGER include of fragments/home/top_coffees.html, no-floor variant) + small inline See-AI-recommendations link to /ai.
7. Wishlist card (one-line copy + Open-wishlist link to /ai/wishlist).

## Service-layer change

app/services/analytics.py: get_top_coffees signature evolved to (db, user_id, *, min_sessions: int = 2). HAVING clause applied only when min_sessions > 0. Default preserves /home/cards/top-coffees fragment endpoint floor. home_shell calls with min_sessions=0 for the eager render (D-09 / IA-06). LIMIT 5, NULL-rating exclusion, tie-break unchanged.

## Router change

app/routers/home.py: home_shell context expanded by greeting, top_coffees, top_coffees_all_unrated. gate preserved (plans 17-03 / 17-04 reuse it).

derive_greeting(username, *, now=None) helper added at module level. Buckets: [5,12) morning ; [12,17) afternoon ; otherwise evening. username falsy -> literal Home (defensive fallback). now is injectable so tests freeze time without monkeypatching datetime.now.

## Confirmations

- gate context preserved. Plan 17-04 /ai page consumes the same dict shape; removing gate would have broken downstream agents. Home template no longer branches on gate.gate_open, but the value is still computed and passed.
- APP_TIMEZONE reused (deviation from RESEARCH Pattern 4 which suggested introducing APP_TZ). APP_TIMEZONE already exists in Settings (Phase 8) and APScheduler consumes it; single source of truth, no new env var.
- DIST-07 banner placeholder is a Jinja comment at the top of <main> in home.html (line ~11). Plan 17-03 swaps for the live include with no merge conflict.
- /home/cards/* fragment endpoint URLs kept unchanged (RESEARCH Open Question #3 resolution). Plan 17-04 mounts the same endpoints from /ai. Minimizes SW cache churn.
- .planning/phases/17-ia-restructure/snippets/ai-surfaces-pre-17-02.html verified present before home.html rewrite. Plan 17-04 Task 6 reads from it to re-mount AI surfaces on /ai.

## Verification

- pytest tests/services/test_analytics.py tests/routers/test_home.py -q -rs -> 65 passed
- pytest tests/ --ignore=tests/e2e -q -> 1187 passed, 3 skipped, 10 xfailed (no new failures)
- ruff format --check . -> clean (223 files already formatted)
- ruff check . -> All checks passed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] tests/test_happy_path_smoke.py::test_happy_path_full_chain asserted cold-start meter present on home**

- Found during: Task 5 full-suite sweep.
- Issue: Pre-Phase-17 happy-path smoke test asserted role=progressbar in the home body after logging 1 brew session (cold-start gate closed). Per D-11, the cold-start meter no longer lives on home (moves to /ai in plan 17-04). The test pinned the old shape.
- Fix: Replaced both the cold_start_active-or-analytics_active either-or check AND the role=progressbar assertion with a single invariant: Top Coffees in r_home.text. The Top Coffees section heading is the new gate-state-invariant marker on home (D-08 eager render).
- Files modified: tests/test_happy_path_smoke.py
- Commit: f2ea569

**2. [Rule 2 - Missing critical scope] Stale Phase 6/7 home-composition tests in tests/routers/test_home.py**

- Found during: Task 1 (TDD red planning).
- Issue: Five pre-existing tests pinned the OLD home composition this plan removes:
  - test_cold_start_branch_renders_meter -- D-11 violation (meter moves to /ai)
  - test_ai_slot_placeholder_present -- D-07 violation (AI hero hx-get gone from home)
  - test_home_shell_staggered_lazy_load -- D-08 violation (aggregate cards no longer lazy on home)
  - test_home_links_to_ai_pages -- D-07 partial violation (/ai/paste-rank link removed; /ai/wishlist still asserted by the new Wishlist test)
  - test_home_has_equipment_button -- D-07 violation (equipment hx-post button moves to /ai)
- Fix: Removed the five tests in-line during Task 1 with a comment block explaining why so a future reviewer does not reintroduce them. Replacement assertions live in the 7 new home-composition tests added in the same task. Fragment-endpoint tests at /home/cards/* are KEPT untouched per the plan neighboring-tests-still-pass expectation.
- Files modified: tests/routers/test_home.py
- Commit: 0687e06

### No other deviations

Plan executed exactly as written for Tasks 2 (analytics signature), 3 (router + helper), and 4 (home.html rewrite).

## Tests Added (25 net new)

tests/services/test_analytics.py:
- test_get_top_coffees_no_floor_includes_single_session_coffees (IA-06 / D-09 backward-compat)
- test_get_top_coffees_no_floor_caps_at_5 (IA-06 LIMIT 5 cap)
- test_get_top_coffees_default_still_enforces_min_two (regression guard)
- _seed_top_coffees_no_floor helper

tests/routers/test_home.py:
- test_home_renders_personalized_greeting (D-10 H1 regex shape)
- test_home_does_not_mount_ai_cards (IA-03 / D-07 negative assertions for the 4 forbidden hx-get URLs)
- test_home_renders_top_coffees_eagerly (D-08 server-render + negative top-coffees hx-get assertion)
- test_home_top_coffees_no_floor_integration (IA-06 / D-09 end-to-end via single-session seed)
- test_home_action_row_has_no_admin_button_for_admin (D-07 scoped to <main> and <header>)
- test_home_action_row_has_quick_rate (D-06 Quick rate anchor)
- test_home_has_see_ai_recommendations_link (D-06 / IA-04 breadcrumb)
- test_derive_greeting_buckets (12 parametrized cases, D-10 bucket coverage)
- test_derive_greeting_falls_back_to_home_when_username_missing (D-10 fallback)
- _seed_single_session_user helper

## Commits

| Task | Hash | Subject |
| ---- | ---- | ------- |
| 1 (RED) | 0687e06 | test(17-02): add failing tests for home composition + no-floor top coffees |
| 2 (GREEN analytics) | d625b33 | feat(17-02): add min_sessions keyword arg to analytics.get_top_coffees |
| 3 (GREEN router) | 9cf6a5a | feat(17-02): wire derive_greeting + top_coffees no-floor into home_shell |
| 4 (GREEN template) | c1c68c2 | feat(17-02): rewrite home.html composition per IA-03/04/06 + D-06..D-11 |
| 5 (style + cleanup) | f2ea569 | style(17-02): ruff format + drop unused idx + happy-path D-11 fixup |

## Threat Surface

Phase 17 introduced two threats in the threat register; this plan touches T-17-01:

- T-17-01 (XSS via personalized greeting): Mitigated by Jinja autoescape globally. derive_greeting does NOT pre-escape the username; Jinja autoescapes at render time. Confirmed by the pre-existing tests/templates/test_autoescape.py suite.

No new security surface introduced beyond the threat model in .planning/phases/17-ia-restructure/17-VALIDATION.md.

## Known Stubs

The DIST-07 banner placeholder in home.html is an intentional Jinja comment, not a stub. It is the documented handoff to plan 17-03 which will replace the comment with the include directive for fragments/ai_key_setup_banner.html. The fragment does not yet exist; until plan 17-03 ships, the comment renders as nothing -- which is the desired no-op state.

## Self-Check: PASSED

Files verified on disk:
- app/services/analytics.py - FOUND
- app/routers/home.py - FOUND
- app/templates/pages/home.html - FOUND
- tests/services/test_analytics.py - FOUND
- tests/routers/test_home.py - FOUND
- tests/test_happy_path_smoke.py - FOUND

Commits verified via git log:
- 0687e06 (Task 1 RED) - FOUND
- d625b33 (Task 2 GREEN analytics) - FOUND
- 9cf6a5a (Task 3 GREEN router) - FOUND
- c1c68c2 (Task 4 GREEN template) - FOUND
- f2ea569 (Task 5 style + happy-path fixup) - FOUND
