---
phase: 17-ia-restructure
plan: 01
subsystem: nav-ia
tags: [nav, ia, admin, ai-tab, config]
requires: []
provides:
  - "Bottom nav slots: Home / Log / AI / Config (no Admin)"
  - "Top nav slots (>=768px): Home / Log / AI / Config / Admin (admin-gated, D-18)"
  - "activeTab routing for /ai/* pathnames"
  - "Administration entry section on /config (admin-gated, visible mobile + desktop)"
affects:
  - app/templates/base.html
  - app/static/js/alpine-components/nav-bar.js
  - app/templates/pages/config_hub.html
  - tests/test_nav.py
tech-stack:
  added: []
  patterns:
    - "Pathname startsWith chain in activeTab getter (existing pattern)"
    - "Catalog-card layout reused for Admin entry tile (existing pattern)"
    - "re.search bottom-nav block scoping in tests (new helper)"
key-files:
  created: []
  modified:
    - app/templates/base.html
    - app/static/js/alpine-components/nav-bar.js
    - app/templates/pages/config_hub.html
    - tests/test_nav.py
decisions:
  - "D-01: Bottom nav order Home / Log / AI / Config; Admin removed from bottom"
  - "D-02: AI tab label \"AI\" with Heroicons sparkles outline SVG (no new asset)"
  - "D-03: AI tab always visible to authed users (not is_admin-gated)"
  - "D-04: Config tab label retained; <h1>Catalog</h1> on /config NOT renamed (min churn)"
  - "D-05: activeTab gets /ai branch BEFORE /config; /admin branch removed entirely"
  - "D-17: Admin entry on /config below catalog grid, above mobile sign-out, is_admin-gated, NOT md:hidden"
  - "D-18: Top-nav Admin link at >=768px stays (admin-gated)"
metrics:
  duration_minutes: ~12
  completed: 2026-05-28
  tasks_completed: 5
  files_modified: 4
  commits: 4
---

# Phase 17 Plan 01: IA-01/IA-02 Nav Reshape Summary

Reshape the persistent nav so the bottom tab bar reflects daily-use priority — drop the Admin tab from the bottom nav and surface it from a dedicated section on the Config page, insert a new always-visible AI tab between Log and Config, route `/ai/*` pathnames to the new active tab, and mirror the slot order in the >=768px top nav while preserving the admin-gated top-nav Admin link.

## Files Touched (4)

| File | Change | Lines |
| ---- | ------ | ----- |
| `app/templates/base.html` | Top nav: insert `<a href="/ai">AI</a>` between Log and Config (Admin link preserved per D-18). Bottom nav: insert AI tab between Log and Config; delete is_admin-gated Admin slot. Comment updated. | +11 / -12 |
| `app/static/js/alpine-components/nav-bar.js` | `activeTab` getter: add `if (p.startsWith('/ai')) return 'ai';` before `/config` branch; remove the `/admin` branch. | +1 / -1 |
| `app/templates/pages/config_hub.html` | Append is_admin-gated `Administration` section between catalog grid and mobile sign-out block; single Admin tile reusing catalog-card classes. | +19 / -0 |
| `tests/test_nav.py` | Five new test functions + `import re` + `_bottom_nav_block` helper (158 lines added). | +158 / -0 |

## Tests Added (5)

| Test | Asserts |
| ---- | ------- |
| `test_admin_home_has_no_admin_bottom_nav_tab` | Admin's GET / response has no `href="/admin"` inside the `<nav x-data="navBar">...</nav>` bottom-nav block. Scoped via `_bottom_nav_block(html)` regex helper. (D-01 / IA-01) |
| `test_admin_config_page_has_admin_entry` | Admin's GET /config contains the literal `Administration` heading AND `href="/admin"` (the new tile in the Administration section). (D-17 / IA-01) |
| `test_non_admin_config_page_has_no_admin_entry` | Non-admin's GET /config contains no `href="/admin"` anywhere — both the top-nav admin link and the Administration section are is_admin-gated. |
| `test_home_has_ai_bottom_nav_tab` | Regular user's GET / response has `href="/ai"` AND the literal `>AI<` text inside the bottom-nav block (D-03 confirms AI tab is not is_admin-gated). (D-02 / IA-02) |
| `test_top_nav_still_has_admin_link_for_admin` | Admin's GET / still contains `href="/admin"` somewhere — D-18 regression guard. Pairs with `test_admin_home_has_no_admin_bottom_nav_tab` to pin "removed from bottom nav, kept in top nav" precisely. |

Test totals: 6 pre-existing + 5 new = 11 collected. All 11 pass in-container.

## Decisions Reflected in Rendered Output

| Decision | Reflected |
| -------- | --------- |
| D-01 — Bottom nav: Home / Log / AI / Config; Admin removed from bottom | base.html bottom-nav block: 4 `<a>` slots in that order, no `href="/admin"` |
| D-02 — AI tab label "AI" with sparkles SVG | `<span class="text-xs">AI</span>` + 24x24 stroke-currentColor Heroicons sparkles outline, no new asset |
| D-04 — Config tab label retained | Bottom-nav + top-nav Config link unchanged; route still `/config`; `<h1>Catalog</h1>` left as-is |
| D-05 — activeTab gets /ai before /config; /admin removed | `nav-bar.js`: branch order home → brew → ai → config → fallback; zero references to `/admin` or `'admin'` |
| D-17 — Admin entry on /config below catalog grid, above mobile sign-out, is_admin-gated, NOT md:hidden | `config_hub.html`: new `{% if request.state.user.is_admin %}<div class="mt-8">...Administration...{% endif %}` block, sits between catalog grid close and `md:hidden` sign-out block, no `md:hidden` class on the new section |
| D-18 — Top-nav Admin link at >=768px stays | `base.html` lines ~91-99: `{% if request.state.user.is_admin %}<a href="/admin">Admin</a>{% endif %}` preserved |
| IA-01 — Admin reachable from Config button, not bottom nav | Admin's home: bottom-nav block has no `href="/admin"`; Admin's /config: Administration section contains `href="/admin"` |
| IA-02 — AI tab present in bottom nav | Every authed user's home contains `<a href="/ai">` inside the `<nav x-data="navBar">` block |

## Verification Run

In-container, against the live coffee-snobbery service (templates + JS copied via `docker compose cp` per project memory `docker-cp-into-container-nesting`):

```
$ docker compose exec coffee-snobbery python -m pytest tests/test_nav.py -q -rs
11 passed, 11 warnings in 6.66s
```

Collateral check — home router tests still pass:

```
$ docker compose exec coffee-snobbery python -m pytest tests/routers/test_home.py -q -rs
24 passed, 1 warning in 6.55s
```

Style gates (CI gates both per project memory `executors-skip-ruff-ci-gates-both`):

```
$ ruff format --check .
223 files already formatted

$ ruff check .
All checks passed!
```

## Commits (4)

| Hash | Type | Subject |
| ---- | ---- | ------- |
| `d1cbf68` | test | `test(17-01): add IA-01/IA-02 nav reshape assertions (RED)` |
| `3848507` | feat | `feat(17-01): reshape base.html nav — drop bottom Admin tab, add AI tab` |
| `7b59d4a` | feat | `feat(17-01): nav-bar.js activeTab — add /ai branch, remove /admin (D-05)` |
| `8a90ff3` | feat | `feat(17-01): add Administration section to /config (D-17 / IA-01)` |

TDD flow honored: tests landed RED first (`d1cbf68`), then the three source commits drove them GREEN. After the test commit, exactly 3 of the 5 new tests failed (the two negative-state tests already passed because pre-change state happened to satisfy them); after all source commits, all 11 nav tests pass.

## Deviations from Plan

None — plan executed exactly as written.

Notes on deliberate plan-adherent choices:

- **`<h1>Catalog</h1>` heading preserved** — D-04 left this to the planner, who chose minimum churn. A future cycle can rename to `Config` to align with the route name; not required for IA-01.
- **No Task 5 source-file commit** — Task 5 in the plan covers running tests + ruff + a final consolidating commit, but the four files modified are already committed atomically across Tasks 1-4. Task 5's verify/style steps ran successfully; no additional commit needed (would have been empty).

## Deferred Items

- **IA-05 on-device PWA cache verification** — deferred to plan 17-05 per the plan's own `<verification>` section. Cannot be verified from this plan because:
  - The container-baked image is not rebuilt yet (we used `docker compose cp` for fast iteration), so `__BUILD_HASH__` in the SW cache name has not advanced.
  - All wave-2 Phase 17 templates need to land before a deploy + PWA verification cycle makes sense.
  - Acceptance environment per `17-CONTEXT.md` is John's iPhone PWA, which is a manual check after the merged Phase 17 build deploys.

## Self-Check

Created/modified files exist:
- `app/templates/base.html` — FOUND
- `app/static/js/alpine-components/nav-bar.js` — FOUND
- `app/templates/pages/config_hub.html` — FOUND
- `tests/test_nav.py` — FOUND

Commits exist:
- `d1cbf68` — FOUND
- `3848507` — FOUND
- `7b59d4a` — FOUND
- `8a90ff3` — FOUND

## Self-Check: PASSED
