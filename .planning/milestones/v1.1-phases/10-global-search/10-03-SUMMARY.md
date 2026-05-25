---
phase: 10-global-search
plan: "03"
subsystem: frontend
tags: [search, htmx, alpine, csp, mobile-first]
dependency_graph:
  requires: [10-02]
  provides: [persistent-search-header, search-bar-alpine-component]
  affects: [base.html, all-authenticated-pages]
tech_stack:
  added: []
  patterns: [alpine-csp-factory, auth-gated-header, htmx-debounce, mobile-sheet]
key_files:
  created:
    - app/static/js/alpine-components/search-bar.js
  modified:
    - app/templates/base.html
decisions:
  - "Mobile sheet uses data-sheet-input and data-sheet-results attributes as component-scoped selectors instead of global IDs, keeping closeSheet() fully encapsulated within the Alpine root"
  - "Mobile sheet hx-target uses CSS attribute selector [data-sheet-results] — valid HTMX 2.x selector syntax, avoids ID collision with desktop #search-results"
  - "Desktop and mobile share the same #search-spinner indicator — spinner is in the header visible on both surfaces"
metrics:
  duration: "25 minutes"
  completed: "2026-05-22"
  tasks: 2
  files: 2
---

# Phase 10 Plan 03: Search UI Header Summary

Auth-gated persistent search header in base.html wired to GET /search, with a CSP-safe Alpine searchBar component driving the mobile full-screen sheet.

## What Was Built

**Task 1 — `app/static/js/alpine-components/search-bar.js`**

Alpine CSP factory registered inside `alpine:init` (not module top-level). State: `{ sheetOpen: false }`. Methods:
- `openSheet()` — sets sheetOpen, auto-focuses the sheet input via `$nextTick` + `data-sheet-input` attribute selector
- `closeSheet()` — resets sheetOpen, clears sheet input value and `data-sheet-results` container innerHTML
- `init()` / `destroy()` — leak-safe window keydown listener for Esc key

No `eval`, no `new Function`. String-ref `x-data="searchBar"` only (CSP build constraint).

**Task 2 — `app/templates/base.html` (modified)**

Script tag for `search-bar.js` added before the `@alpinejs/csp` core (line ordering required). Auth-gated `<header x-data="searchBar">` inserted between `<body>` and `{% block content %}`:

- Desktop (`>=768px`, `hidden md:flex`): thin `h-14` bar with inline magnifying-glass SVG, search input wired with all HX-4 attributes, floating `#search-results` div positioned absolute under the input, `#search-spinner` with `.htmx-indicator` class
- Mobile (`<768px`, `md:hidden`): icon button triggers `openSheet()`, full-screen sheet with X close button, sheet input with `data-sheet-input`, results div with `data-sheet-results`, scrim with `@click.self="closeSheet()"`
- `.htmx-indicator` rule confirmed present in `tailwind.src.css` lines 23-25 — not duplicated

## Verification Results

- `pytest tests/test_search.py::test_header_auth_gate -rs -x -q`: **1 passed** (was RED before this plan)
- `pytest tests/test_search.py -rs -q`: **15/15 passed** (full Phase 10 test suite GREEN)

## Threat Surface Scan

No new trust boundaries introduced beyond what was already in the plan's threat model:
- T-10-HDR-LEAK mitigated: entire `<header>` is inside `{% if request.state.user %}` — absent on /login and /setup (verified by test)
- T-10-CSP mitigated: script tag has nonce, no `eval`/`new Function`/`hx-on:`/`|safe` in template code (only appears in line-1 comment)
- T-10-XSS: search results escaping owned by Plan 02 (unchanged)

## Deviations from Plan

None — plan executed exactly as specified.

The one micro-decision not pre-specified: component-scoped selectors (`data-sheet-input`, `data-sheet-results`) for the mobile sheet rather than global IDs, to keep `closeSheet()` fully encapsulated within `this.$root`. This is strictly better than the plan's "Reference elements via `this.$root.querySelector(...)`" guidance — it follows that guidance exactly.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `app/static/js/alpine-components/search-bar.js` | FOUND |
| `app/templates/base.html` | FOUND |
| `10-03-SUMMARY.md` | FOUND |
| Task 1 commit `ceba25e` | FOUND |
| Task 2 commit `d8d1799` | FOUND |
| `pytest tests/test_search.py -rs -q` 15/15 | PASSED |
