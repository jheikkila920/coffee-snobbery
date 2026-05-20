---
phase: "06-analytics-home-page"
plan: "02"
subsystem: "home-router"
tags: ["htmx", "analytics", "cold-start", "home-page", "templates", "auth-gate"]
dependency_graph:
  requires:
    - "06-01: app/services/analytics.py — all nine query functions"
    - "01-middleware: FragmentCacheHeadersMiddleware — no-store + Vary:HX-Request"
    - "02-auth: require_user dependency — 401 gate"
  provides:
    - "app/routers/home.py: GET / shell, GET /home/cards/recent-brews, GET /home/cards/unrated-coffees"
    - "app/templates/pages/home.html: eager shell with gate branch + 5 staggered lazy slots"
    - "app/templates/fragments/home/_cold_start.html: progress meter empty state"
    - "app/templates/fragments/home/recent_brews.html: card list at all viewports"
    - "app/templates/fragments/home/unrated_coffees.html: catalog suggestions"
  affects:
    - "06-03: aggregate card fragment endpoints extend home.py (top-coffees, preference, etc.)"
    - "Phase 7: AI card insertion point in home.html (Jinja comment, not live trigger)"
tech_stack:
  added: []
  patterns:
    - "Eager analytics shell: all three service calls (gate, recent-brews, unrated) before render"
    - "Jinja2 include for always-on recent-brews (no HTMX request on first paint)"
    - "HTMX load delay:Nms stagger for aggregate card lazy slots (HOME-09)"
    - "Server-side progress meter pct via Jinja2 list|min filter (no Alpine)"
    - "Jinja2 comment as cross-phase insertion point (not a live trigger)"
key_files:
  created:
    - "app/routers/home.py"
    - "app/templates/pages/home.html"
    - "app/templates/fragments/home/_cold_start.html"
    - "app/templates/fragments/home/recent_brews.html"
    - "app/templates/fragments/home/unrated_coffees.html"
    - "tests/routers/test_home.py"
  modified:
    - "app/main.py"
decisions:
  - "Recent brews rendered via eager {% include %} on first paint (no HTMX request), consistent with D-01"
  - "Unrated coffees lazy-loaded via load delay:150ms (no gate dependency per D-01)"
  - "Phase 7 AI-card slot implemented as Jinja comment only — Jinja strips it at render; test_ai_slot_placeholder_present checks template source file not HTTP response"
  - "No roaster_name in recent_brews card: get_unrated_coffees returns id/name/origin/roast_level only (service scope from 06-01); origin+roast_level shown as secondary context"
metrics:
  duration: "35 minutes"
  completed: "2026-05-20T22:15:00Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 6
  files_modified: 1
---

# Phase 6 Plan 2: Home Shell Route + Templates Summary

Analytics home page shell replacing the Phase 0 placeholder: `app/routers/home.py` with three auth-gated endpoints, the Jinja2 page template with cold-start gate branching and five staggered HTMX lazy slots, three fragment templates, and router smoke tests proving auth, cache headers, gate branches, and the Phase 7 AI-slot placeholder.

## What Was Built

### `app/routers/home.py`

Three handlers, each `Depends(require_user)` + `Depends(get_session)` with `# noqa: B008`:

| Handler | Route | Purpose |
|---|---|---|
| `home_shell` | `GET /` | Eager shell: all 3 analytics calls → full page render |
| `card_recent_brews` | `GET /home/cards/recent-brews` | Partial refresh fragment for recent-brews card |
| `card_unrated_coffees` | `GET /home/cards/unrated-coffees` | Lazy-load + partial refresh for unrated coffees |

`user.id` from `request.state.user` is the only source of `user_id` (T-06-05 IDOR defense).

### `app/main.py`

- Added `from app.routers import home as home_router` (alphabetically after `flavor_notes`)
- Added `app.include_router(home_router.router)`
- Removed Phase 0 placeholder `@app.get("/") def home(...)` that rendered `pages/index.html`

### Templates

| File | Key behavior |
|---|---|
| `pages/home.html` | h1 header, eager recent-brews include, unrated lazy (150ms), gate branch (meter vs 5 staggered slots), Phase 7 Jinja comment |
| `fragments/home/_cold_start.html` | `role="progressbar"` meter, server-computed pct via `[n, cap]|min`, 3-branch dynamic copy |
| `fragments/home/recent_brews.html` | Card list all viewports, Edit + Brew-again links, empty state "No brews logged yet. The snobbery awaits." |
| `fragments/home/unrated_coffees.html` | Log session links with `aria-label`, empty state "You've brewed every coffee in the catalog." |

### `tests/routers/test_home.py` (7 tests)

All 7 pass:
- `test_home_shell_authenticated` — 200 + "Home"/"Snobbery" for authed user
- `test_home_unauthenticated_returns_401` — 401 on bare GET /
- `test_recent_brews_fragment_headers` — `no-store` + `Vary:HX-Request`
- `test_unrated_coffees_fragment_headers` — same cache headers
- `test_unrated_coffees_fragment_requires_auth` — 401 on fragment
- `test_cold_start_branch_renders_meter` — `role="progressbar"` + "Build your taste profile."
- `test_ai_slot_placeholder_present` — gate-open renders "Top Coffees"; no live AI trigger; Phase 7 comment in template source

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Jinja2 comment stripped at render time**

- **Found during:** Task 3 (first test run — `test_ai_slot_placeholder_present`)
- **Issue:** The plan specified asserting "Phase 7: AI recommendation card slot" in `resp.text`, but Jinja2 `{# ... #}` comments are stripped from HTML output. The string is in the template source but not in the rendered response.
- **Fix:** Updated `test_ai_slot_placeholder_present` to: (a) assert `"Top Coffees"` in `resp.text` (proves gate-open branch renders), (b) assert live AI trigger absent from `resp.text`, (c) verify the Phase 7 comment exists in the template source file via `pathlib.Path.read_text()`.
- **Files modified:** `tests/routers/test_home.py`
- **Commit:** 4d4ae31

**2. [Rule 1 - Bug] CSP probe false-positive on comment text**

- **Found during:** Task 2 (first template probe run)
- **Issue:** Template comments contained the literal strings "no |safe", "hx-on:", and "hx-vals='js:'" as documentation of what's forbidden. The CSP probe regex matched these comment strings as violations.
- **Fix:** Rewrote template file-header comments to avoid embedding the exact forbidden patterns (changed to "All values autoescaped. CSP-clean.").
- **Files modified:** All four template files
- **Commit:** 3cddf50

### Intentional Scope Gap (documented, not fixed)

**roaster_name absent from unrated-coffees card:** `get_unrated_coffees()` in `analytics.py` (Plan 06-01) returns `(id, name, origin, roast_level)` — no roaster join. The UI-SPEC says "Coffee name + roaster name" but fixing the service is Plan 06-01's scope. Template shows `origin + roast_level` as secondary context instead. Plan 06-03 may add a roaster join when it extends the service, or Phase 11 can refine this.

## Performance

No new queries introduced in this plan (shell calls existing analytics functions from 06-01). All three service calls in `home_shell` are proven <50ms in Plan 06-01's performance test.

## Known Stubs

None. All three endpoints call real analytics functions and render real DB data. The five aggregate-card lazy slots reference endpoints implemented in Plan 06-03 (not yet wired); the HTMX request will get a 404 until 06-03 lands. This is expected and documented — the slots are intentional "promise" markup for 06-03.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes beyond the three routes planned in the threat model (T-06-04, T-06-05, T-06-06, T-06-07, T-06-12). All mitigations implemented as specified.

## Self-Check: PASSED

- `app/routers/home.py` exists and imports cleanly
- `app/templates/pages/home.html` exists with ≥5 staggered triggers and Phase 7 comment
- `app/templates/fragments/home/_cold_start.html` exists with `role="progressbar"`
- `app/templates/fragments/home/recent_brews.html` exists with empty-state string
- `app/templates/fragments/home/unrated_coffees.html` exists with aria-label links
- `tests/routers/test_home.py` exists with 7 tests — all pass
- `app/main.py` no longer contains `pages/index.html` placeholder
- Commits verified: 18f5f3e (Task 1), 3cddf50 (Task 2), 4d4ae31 (Task 3)
- Routes `/`, `/home/cards/recent-brews`, `/home/cards/unrated-coffees` all register
- Template probe prints `templates ok`
- `pytest tests/routers/test_home.py -q` → 7 passed
