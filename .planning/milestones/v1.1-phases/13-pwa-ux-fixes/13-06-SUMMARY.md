---
phase: 13-pwa-ux-fixes
plan: "06"
subsystem: frontend/routing
tags: [guided-brew, data-tools, export-import, recipe-row-test, c5, c8]
dependency_graph:
  requires: [13-05]
  provides: [C5-guided-brew-reachability, C8-export-import-relocation]
  affects: [home.html, sessions.html, session_list.html, config_hub.html, brew.py, main.py]
tech_stack:
  added: []
  patterns:
    - data_router pattern for routes outside /brew prefix (supplemental APIRouter in brew.py)
    - Jinja2 Environment template render in tests (SimpleNamespace recipe fake, parametrize over mode)
key_files:
  created:
    - app/templates/pages/data_tools.html
    - tests/templates/test_recipe_row.py
  modified:
    - app/templates/pages/home.html
    - app/templates/pages/sessions.html
    - app/templates/fragments/session_list.html
    - app/templates/pages/config_hub.html
    - app/routers/brew.py
    - app/main.py
    - tests/routers/test_brew_router.py
decisions:
  - "data_router added to brew.py as a second APIRouter() (no prefix) for GET /data-tools — avoids polluting main.py with a new router module for a single endpoint"
  - "Guided Brew on sessions.html uses secondary-button styling (border) to match header context, distinct from Log session primary button"
metrics:
  duration: "~30 minutes"
  completed: "2026-05-25"
  tasks: 3
  files: 9
---

# Phase 13 Plan 06: C5 Guided Brew Reachability + C8 Export/Import Relocation Summary

Added Guided Brew entry points on Home and Log pages routing to /recipes (C5), created a dedicated /data-tools page for Export/Import linked from the config hub (C8), and wrote the mandated recipe_row regression test covering both fragment shapes.

## What Was Built

**C5 — Guided Brew reachability (D-05):**
- `home.html`: Added "Guided Brew" link (secondary-button style) before "Log session" in the header actions div. Routes to /recipes where the eafc6e3-fixed recipe_row controls already render "Start guided brew" for steps-bearing recipes.
- `sessions.html`: Added "Guided Brew" link in the header (same secondary-button styling); also removed the inline Export CSV / Import sessions controls (C8 removals were done in the same file pass).

**C5 mandated regression test:**
- `tests/templates/test_recipe_row.py`: New file covering `recipe_row.html` in both `mode="card"` and `mode="row"` shapes via `@pytest.mark.parametrize`. With steps: asserts `/brew/guided?recipe_id=<id>` link present, no no-steps edit link as guided-brew control. Without steps: asserts `/recipes/<id>/edit` link + "(add steps)" hint, no /brew/guided link. 4 tests, all green.

**C8 — Export/Import relocation (D-06):**
- `app/templates/pages/data_tools.html` (NEW): Extends `base.html`, `max-w-2xl px-6 py-12`, titled "Export / Import sessions". Export section: `<a href="/brew/export">` (full export, no filters — dedicated page is not filter-context-aware). Import section: `hx-post="/brew/import" hx-encoding="multipart/form-data" hx-target="#import-results"` with CSRF hidden input. Routes `/brew/export` and `/brew/import` are UNCHANGED.
- `app/routers/brew.py`: Added `data_router = APIRouter()` (no prefix) with `GET /data-tools` gated by `require_user`. Template renders `pages/data_tools.html` with `results=None`.
- `app/main.py`: Registered `brew_router.data_router` after `brew_router.router`.
- `app/templates/pages/config_hub.html`: Added `<a href="/data-tools">Export / Import sessions</a>` in the `md:hidden` account section AFTER Plan 05's dark toggle (preserves the darkToggle UI).
- `app/templates/fragments/session_list.html`: Removed the `{% if is_fragment %}...hx-swap-oob...{% endif %}` export-csv-link block (dead — the export link no longer lives on the sessions page).
- `tests/routers/test_brew_router.py`: Added `test_data_tools_authed_returns_page` (authed GET /data-tools → 200 + "/brew/import" in body) and `test_data_tools_requires_auth` (unauthenticated GET /data-tools → 302 or 401). All 24 CSV + router tests green.

## Deviations from Plan

None — plan executed exactly as written. The dark-mode toggle from Plan 05 was preserved in config_hub.html; the data-tools link was appended after it as specified.

## Checkpoint Deferred

**Task 4** (`type="checkpoint:human-verify"`) is deferred to the orchestrator's consolidated batch verification pass per the sequential executor protocol. The checkpoint covers:
- C5: Guided Brew action visible on Home and Log pages; tapping routes to /recipes; steps-bearing recipe launches GBM, no-steps recipe links to editor.
- C8: Log/sessions view no longer shows inline Export CSV / Import controls; config hub shows "Export / Import sessions" link; /data-tools renders with working Export and Import (CSRF enforced on import).

## Threat Surface Coverage

- **T-13-14 mitigated**: The import form in `data_tools.html` carries `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">`. The route itself is the unchanged `POST /brew/import` which enforces CSRF via middleware.
- **T-13-15 mitigated**: `GET /data-tools` gated by `require_user`; route test confirms authed → 200 and unauthenticated → 302/401.
- **T-13-16 accepted**: CSV import pipeline is unchanged (only entry point moved).

## Self-Check

Commits:
- `4a8d762` — test(13-06): C5 mandated recipe_row regression test
- `9c8e4bf` — feat(13-06): C5 Guided Brew action on Home + Log pages
- `5ad3912` — feat(13-06): C8 /data-tools page + auth-gated route + config-hub link; remove inline export/import

Files created/modified confirmed:
- `tests/templates/test_recipe_row.py` — created, 4 tests green
- `app/templates/pages/home.html` — Guided Brew link present
- `app/templates/pages/sessions.html` — Guided Brew link; Export/Import removed
- `app/templates/pages/data_tools.html` — created, contains /brew/import + CSRF + /brew/export
- `app/routers/brew.py` — data_router + GET /data-tools added
- `app/main.py` — data_router registered
- `app/templates/pages/config_hub.html` — /data-tools link added; dark toggle preserved
- `app/templates/fragments/session_list.html` — OOB export block removed
- `tests/routers/test_brew_router.py` — 2 new /data-tools tests; 24/24 pass

All assertion checks passed locally before SUMMARY write.

## Self-Check: PASSED
