---
phase: 04-shared-catalog
plan: 07
subsystem: coffees-crud
tags: [coffees, crud, htmx, filters, hx-push-url, array-column, mobile-responsive, wave-7]

# Dependency graph
requires:
  - phase: 04-shared-catalog
    provides: app/schemas/coffee.py (CoffeeCreate + extra='forbid') (plan 04-02); app/models/coffee.py (ARRAY(BigInteger) advertised_flavor_note_ids + roaster FK SET NULL) (plan 04-03); app/services/roasters.py (list_roasters + get_roaster — autocomplete + roaster_name lookups) (plan 04-04); app/services/flavor_notes.py (create_flavor_note + list_flavor_notes — chip-builder seed) (plan 04-05); app/events.py CATALOG_COFFEE_* constants (plan 04-01); the universal Phase 4 catalog router template (plan 04-04 — roasters); app/services/form_validation.py::errors_by_field (plan 04-02)
  - phase: 02-auth
    provides: app/dependencies/auth::require_user + tests/conftest.py seeded_admin_user
  - phase: 01-middleware
    provides: starlette-csrf CSRFMiddleware (double-submit), CSRFFormFieldShim hoisting hidden inputs to header, app/templates_setup.py templates + base.html
provides:
  - app/services/coffees.py — sync Session CRUD with four-dim filter list (roaster_id, country, process, archived); ARRAY(BigInteger) round-trip; audit-event emit (CAT-03); list_distinct_countries / list_distinct_processes / flavor_note_name_map helpers
  - app/routers/coffees.py — 9 HTMX endpoints under /coffees with hx-push-url filter bar contract (D-03), HX-Request fragment branch, coffee detail page with bag-form-mount + "Open new bag" affordance contract for plan 04-09
  - app/templates/pages/coffees.html — list page + filter bar (hx-push-url="true")
  - app/templates/pages/coffee_detail.html — coffee detail with bags section + #bag-form-mount mount div for plan 04-09
  - app/templates/fragments/coffee_list.html, coffee_row.html, coffee_form.html, coffee_filters_panel.html — coffee-specific fragments
  - Chip-builder integration contract for plan 04-11 (locked here): #flavor-note-chips wrapper carrying class flavor-note-chips-field; #flavor-note-chip-list children; #flavor-note-hidden-inputs containing one <input type="hidden" name="advertised_flavor_note_ids" value="..."> per selected id; <input name="flavor_note_query"> autocomplete shell
  - Bag-form-mount integration contract for plan 04-09 (locked here): GET /coffees/{id}/bags/new → fragments/bag_form.html target #bag-form-mount; POST /coffees/{id}/bags → fragments/bag_row.html target #bag-list (the list mount div)
  - httpx 0.28 form-encoding gotcha pattern (locked for Phase 4+ tests): when posting repeated form keys via TestClient, use data={"key": [v1, v2]} (dict whose values are lists) — NOT data=[("key", v1), ("key", v2)] (list of 2-tuples — httpx silently drops the body)
affects:
  - 04-09 (bag CRUD — consumes #bag-form-mount contract on /coffees/{id} detail page; the "Open new bag" button is already wired with hx-get /coffees/{id}/bags/new + hx-target #bag-form-mount)
  - 04-10 (search — the search page links into coffee detail at /coffees/{id})
  - 04-11 (autocomplete + mini-modal — mounts Alpine flavorNoteChips component on the IDs locked here; reuses /roasters/list and /flavor-notes/datalist autocomplete contracts already wired in this plan)
  - 05 (brew sessions — references coffees.id and reads coffees.advertised_flavor_note_ids; the four-dim filter pattern is reusable for brew-session filtering)
  - 07 (AI service — AI-01/AI-02/AI-04 consume coffees + their advertised flavor notes; the flavor_note_name_map helper is the canonical id→name resolver)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Four-dim filter list with hx-push-url contract (D-03 + CAT-07): single GET /coffees handler with optional roaster_id/country/process/archived query params; SQLAlchemy parameterized .where() composition (no string concatenation, no SQLi); HX-Request header branches to fragment-only response so the filter form's hx-target=#coffee-list swaps a fragment while hx-push-url=true keeps the browser URL synced. Reusable for Phase 5 brew-session filtering."
    - "Responsive list-vs-card layout marker pattern: desktop wrapped in <div class='hidden md:block'> with a <table>; mobile wrapped in <div class='md:hidden space-y-3'> with the same coffee_row.html fragment rendered with mode='card'. Test ``test_list_coffees_includes_responsive_layout_markers`` asserts both marker classes are present once a coffee is seeded; Phase 12 Playwright will assert no-horizontal-scroll at 375px (deferred per 04-VALIDATION Manual-Only table)."
    - "archived=False vs archived=True filter dichotomy (UI-SPEC lock): archived=False (default) returns only non-archived rows; archived=True returns ONLY archived rows (NOT a union). Test ``test_filter_archived_true_returns_only_archived`` locks the contract."
    - "ARRAY(BigInteger) round-trip via SQLAlchemy 2.0 + psycopg 3 native: assign a list[int] directly to the Coffee.advertised_flavor_note_ids column on create or update; Postgres array assignment replaces the entire value on update (no merge). The flavor_note_name_map helper resolves id→name in a single IN query so the list template never N+1s."
    - "Pre-resolved roaster_name_map + flavor_note_names dicts passed to the row template — avoids both N+1 SELECTs (the router fans out one query per shape and hands the dict to the template) AND the relationship-loading complexity of selectinload(Coffee.roaster). Simpler to reason about than ORM relationship eagerness for a fan-out of arbitrary array ids."
    - "List query for distinct dropdown values (list_distinct_countries): SELECT DISTINCT coffees.country WHERE country IS NOT NULL ORDER BY country — repopulated on every list-page render. Plan-time deviation noted: the GET /filters-panel endpoint (Open Question 2 — partial-refresh of the filter dropdowns without a full page reload) is shipped despite the plan flagging it as 'optional'. The endpoint is identical to the page filter form, reuses the same helper, and adds no new query path."
    - "_parse_form_payload: raw_view / schema_input split. raw_view carries string values + raw list of id strings (for the form re-render on validation failure so the user's submitted text is preserved per D-04); schema_input is the parsed dict handed to Pydantic with empty-string optional fields coerced to None, advertised_flavor_note_ids cast to list[int], non-int chip values mapped to [0] sentinel so the field_validator(ge=1) path raises a clean field-level error message."
    - "_NON_SCHEMA_FORM_KEYS strip: form fields like roaster_query, flavor_note_query, X-CSRF-Token are autocomplete-shell / middleware-only inputs that must NOT reach the schema (they would trip extra='forbid'). Stripped in _parse_form_payload before constructing schema_input. Locked for plan 04-11's chip-builder which adds the same shape (flavor_note_query autocomplete + hidden inputs for selected ids)."
    - "httpx-0.28 form-data shape lock (TEST WRITERS READ THIS): TestClient.post(url, data=[('key', v1), ('key', v2)]) silently sends NO body — Content-Length absent, Content-Type absent, transfer-encoding chunked but no payload. Use TestClient.post(url, data={'key': [v1, v2]}) instead. Locked for all Phase 4+ tests that POST repeated form keys (array fields, multi-select widgets, future tag inputs). The handler reads getlist() either way once the body actually arrives."

key-files:
  created:
    - app/services/coffees.py
    - app/routers/coffees.py
    - app/templates/pages/coffees.html
    - app/templates/pages/coffee_detail.html
    - app/templates/fragments/coffee_list.html
    - app/templates/fragments/coffee_row.html
    - app/templates/fragments/coffee_form.html
    - app/templates/fragments/coffee_filters_panel.html
    - tests/phase_04/test_coffee_filters.py
  modified:
    - app/main.py
    - tests/phase_04/test_routers_coffees.py

key-decisions:
  - "Pre-resolved id→name dicts (roaster_name_map, flavor_note_names) passed to the row template — NOT SQLAlchemy relationship + selectinload. The row template avoids the N+1 trap because the router fans out one extra SELECT per shape (one for roaster names, one for flavor-note names) and hands the resulting dict to the template. Simpler than wiring a relationship on Coffee for a fan-out of arbitrary ARRAY ids (which selectinload doesn't even handle natively for non-FK arrays)."
  - "list_distinct_countries via SELECT DISTINCT country WHERE country IS NOT NULL ORDER BY country. Rebuilt on every list-page render so new coffees with new countries surface immediately. Alternative (Phase 5+ optimisation if the list grows) is a materialized view refreshed by APScheduler — deferred."
  - "archived=True filter returns ONLY archived rows (NOT a union with non-archived). UI-SPEC lock per the filter-bar spec; the ☐ Show archived checkbox toggles between two views, not a union. Test test_filter_archived_true_returns_only_archived locks the behavior."
  - "GET /filters-panel shipped (plan flagged optional). The endpoint is ~20 LOC: same context shape as the page filter form, same templates, useful when a new roaster is created via mini-modal (plan 04-11) without a full page reload. Punting on it would have left a dangling hint in the page template; shipping it now avoids that."
  - "Form-validation error normalization via local _normalize_errors: any error key outside _FORM_FIELDS (e.g., the extra-field rejection on is_admin from a T-04-MASS probe) folds into a synthetic '_form' banner so the user still sees the rendered error. Mirrors the recipes router's pattern."
  - "Non-schema form keys (roaster_query, flavor_note_query, X-CSRF-Token) stripped in _parse_form_payload BEFORE constructing CoffeeCreate. Otherwise extra='forbid' would trip a false error on what are autocomplete-shell or middleware-only inputs."
  - "Tasks 1 + 2 (service + router + 9 endpoints, 2 pages + 4 fragments) were landed in a prior worktree (commits a76d82b + 211a1c6). Task 3 (tests) was interrupted mid-execution and committed WIP-style with --no-verify as 96017ba. This SUMMARY's resume agent fixed two failing tests (httpx form-data shape bug), formatted with ruff, ran the full Phase 4 suite green (163 passed, 2 skipped), and committed the final test work hook-clean as 7aabfc5. The WIP commit's content is functionally superseded; its parent commits remain accurate."

patterns-established:
  - "Four-dim filter list with hx-push-url=true on the form + hx-include='this' + hx-target=#<list-id> + hx-trigger='change from:select, change from:input[type=checkbox]'. Form submits NEVER fire (no submit button + no hx-trigger='submit'); HTMX intercepts change events and fires GET with all named inputs included. Reusable for Phase 5 brew-session filtering and Phase 4 future entity filters."
  - "Responsive list-vs-card via `hidden md:block` + `md:hidden` wrappers on the SAME fragment file (coffee_row.html) selected by a `mode` flag. One template file, two visual modes, both data-row + id='coffee-N' so HTMX edit/archive swaps work in either viewport."
  - "Pre-resolved id→name dict pattern for array-column rendering: when a row carries an ARRAY of FK ids that need name resolution in the template, the router fans out ONE extra SELECT … IN (ids) and hands the resulting dict to the template. Avoids both N+1 and the complexity of SQLAlchemy relationship eagerness for arbitrary-id arrays."
  - "httpx 0.28 TestClient form-data shape: data={'key': [v1, v2]} for repeated form keys, NOT data=[('key', v1), ('key', v2)]. The second shape silently drops the body. Locked across Phase 4+ tests that post array fields."

requirements-completed:
  - CAT-03
  - CAT-07

# Metrics
duration: 65min
completed: 2026-05-19
---

# Phase 4 Plan 07: Coffees CRUD Summary

**Ships CAT-03 (coffees CRUD with ARRAY(BigInteger) advertised_flavor_note_ids) + CAT-07 (mobile card-list collapse + four-dimension filter bar with hx-push-url URL state). The most complex CRUD surface in Phase 4 — array column round-trip, four filter dimensions with browser URL state, responsive table↔card layout, two HTMX autocomplete fields, and a coffee detail page that doubles as the launching pad for bag CRUD (plan 04-09).**

## Performance

- **Duration:** ~65 minutes wall-clock work across two executor agents (the original worktree built tasks 1+2 and crashed mid-task 3 on an API error; this resume agent fixed the test bug and finished hook-clean).
- **Tasks:** 3
- **Files created:** 9 (1 service + 1 router + 2 pages + 4 fragments + 1 new test file)
- **Files modified:** 2 (`app/main.py`, `tests/phase_04/test_routers_coffees.py` — replacing the Wave-0 stub)

## Accomplishments

### Task 1 — service + router + main.py wire-up (commit a76d82b)

- **`app/services/coffees.py`** ships full CAT-03 CRUD mirroring the roasters service shape: sync Session, kwargs-only API after a leading `*`, single commit per write, structlog audit event at the end of each write. Functions: `create_coffee`, `get_coffee`, `get_coffee_with_bags` (for the detail page; bags ordered `opened_at DESC NULLS LAST, created_at DESC`), `list_coffees` (four-dim filter — roaster_id / country / process / archived), `update_coffee` (Core `update()` so `updated_at = func.now()` is stamped in the same statement), `archive_coffee` (soft-delete). Plus three helpers: `list_distinct_countries` (SELECT DISTINCT for the filter dropdown), `list_distinct_processes` (returns the locked 6-value enum constant tuple), and `flavor_note_name_map` (id→name dict for advertised-flavor-pill resolution — single IN query, never N+1). Audit events: `CATALOG_COFFEE_CREATED`, `CATALOG_COFFEE_UPDATED`, `CATALOG_COFFEE_ARCHIVED`.
- **`app/routers/coffees.py`** implements 9 endpoints under `/coffees`:
  - `GET /coffees` — list page or fragment (HX-Request branch), four query params: `roaster_id`, `country`, `process`, `archived`. Builds the four context dicts (`coffees`, `filters`, `flavor_note_names`, `roaster_name_map`) plus full-page-only `roasters` / `countries` / `processes` dropdown sources.
  - `GET /coffees/new` — empty form fragment with `mode="create"`.
  - `GET /coffees/empty-form` — empty fragment for the Cancel button (CSP-safe round-trip).
  - `POST /coffees` — create. Async + reads raw form via `await request.form()` so the `_parse_form_payload` helper can collect `advertised_flavor_note_ids` via `form_data.getlist`. Validation errors → 200 + form-fragment re-render with errors. Success → row fragment + `include_oob_form_clear=True`.
  - `GET /coffees/filters-panel` — HTMX-fetched filter dropdown panel (Open Question 2 — refresh dropdowns without a full page reload). Declared BEFORE `/{coffee_id}` so the literal path isn't captured by the int param matcher.
  - `GET /coffees/{id}` — detail page (`pages/coffee_detail.html`) with coffee + bags + "Open new bag" affordance + `#bag-form-mount` mount div (consumed by plan 04-09).
  - `GET /coffees/{id}/edit` — pre-populated form fragment with the array ids rendered as hidden inputs.
  - `POST /coffees/{id}` — update. Same validation re-render pattern; on success returns the row fragment.
  - `POST /coffees/{id}/archive` — soft-delete; re-renders the row with archived styling.
- **`app/main.py`** wires `app.routers.coffees.router` into the FastAPI app after the equipment router.

### Task 2 — 2 pages + 4 fragments with desktop/mobile responsive layout + filter bar (commit 211a1c6)

- **`app/templates/pages/coffees.html`** — list page wrapped in `max-w-6xl` (wider for the data-dense coffees table). Header with "Add coffee" button (`hx-get="/coffees/new"` → `#coffee-form-mount`). Filter bar (id `coffee-filters`) with `hx-get="/coffees"` + `hx-trigger="change from:select, change from:input[type='checkbox']"` + **`hx-push-url="true"`** (D-03 lock) + `hx-target="#coffee-list"` + `hx-include="this"`. Four labeled inputs: Roaster `<select>` (sourced from `roasters` context), Country `<select>` (from `countries` distinct list), Process `<select>` (from the locked 6-value enum), and a checkbox for Show archived.
- **`app/templates/pages/coffee_detail.html`** — `max-w-3xl` layout. Back-to-list breadcrumb. Header with coffee name (italic + archived pill if archived) + Edit / Archive buttons. Metadata `<dl>` grid for country/origin/process/roast_level/varietal. Advertised flavor-note pill row. Notes block (whitespace-preserving). Bags section with `#bag-form-mount` + `#bag-list` div + "Open new bag" button (`hx-get="/coffees/{id}/bags/new"` — contract for plan 04-09). Empty-state copy "No bags yet. 'Open new bag' to start logging brews against this coffee."
- **`app/templates/fragments/coffee_list.html`** — desktop table (`hidden md:block` wrapper, `<table>` with Name · Roaster · Origin · Process · Roast level · Flavor notes · Actions columns) + mobile cards (`md:hidden` wrapper, cards via `{% include "fragments/coffee_row.html" %}` with `mode="card"`). Both layouts iterate the same `coffees` context; empty-state copy is UX-04 snobbery-tone ("No coffees yet. Click 'Add coffee' to begin building the catalog.")
- **`app/templates/fragments/coffee_row.html`** — dual-mode (row vs card) selected by `mode`. Both modes carry `data-row` + `id="coffee-{N}"` so HTMX swaps work in either viewport. Roaster name resolved via `roaster_name_map.get(coffee.roaster_id)` (falls back to "—" when the FK was SET NULL). Advertised flavor pills up to 3, then "+N more" affordance. Archive confirm copy locked from UI-SPEC microcopy: *"Archive coffee — stops appearing in selectors but keeps brew history."* OOB form-clear via `<div id="coffee-form-mount" hx-swap-oob="innerHTML"></div>` when `include_oob_form_clear` is set.
- **`app/templates/fragments/coffee_form.html`** — inline-expand form, two modes (`create` vs `edit`) selected by `mode`. Carries CSRF hidden input (CSRFFormFieldShim hoists it to the X-CSRF-Token header). Fields: name (required), roaster autocomplete (text + hidden `roaster_id` + `#roaster-dropdown` mount; D-13 + HX-4 attrs: `hx-trigger="input changed delay:350ms[target.value.length >= 2]"` + `hx-sync="this:replace"`), country, origin, process `<select>`, roast_level `<select>`, varietal, flavor-note chip-builder shell (the **plan-04-11 integration contract** documented in the template header — `#flavor-note-chips` / `#flavor-note-chip-list` / `#flavor-note-hidden-inputs` + the `name="flavor_note_query"` autocomplete input), notes textarea, Cancel ghost + Save accent.
- **`app/templates/fragments/coffee_filters_panel.html`** — same shape as the page filter form, exposed as a swap target via `GET /filters-panel` for partial-refresh of the dropdowns without a full page reload (Open Question 2).

### Task 3 — real router tests + filter integration tests (commit 96017ba WIP → 7aabfc5 hook-clean)

The original task 3 commit landed as WIP `96017ba` with `--no-verify` because an API interruption cut the execution short with two tests red and the file unformatted. This resume agent:

1. **Identified the test-side bug** in `test_create_coffee_with_array_round_trip` + `test_update_persists_array_change`: both tests posted repeated form keys via `data=[("name", "Geometry"), ("notes", ""), ("advertised_flavor_note_ids", str(fn1)), ("advertised_flavor_note_ids", str(fn2))]` — a **list of 2-tuples**. **httpx 0.28 silently drops the body** in that shape: the built request has `transfer-encoding: chunked` but no `content-type`, no `content-length`, and no payload bytes. The handler received an empty form, the schema's required `name` field tripped the validator, and the POST re-rendered the form at 200 with the row never persisted. The documented httpx shape for repeated keys is `data={"key": [v1, v2], ...}` (dict whose values can be lists), which the handler's `form_data.getlist` reads identically once the body actually arrives.

2. **Fixed both tests** to use `data={"name": "Geometry", "notes": "", "advertised_flavor_note_ids": [str(fn1), str(fn2)]}`. Added a docstring on the array round-trip test calling out the gotcha for future readers + a one-line cross-reference comment on the update test. Locked the pattern in `patterns-established` for any future Phase 4+ test that posts repeated form keys.

3. **Ran `ruff format`** on both test files (2 files reformatted — line-width adjustments). `ruff check` clean.

4. **Ran the full Phase 4 suite green**: 163 passed, 2 skipped (the skipped ones are Postgres-reachability pre-existing skips on the host environment, not coffee-related). Plan-3 verification command (`pytest -q tests/phase_04/test_routers_coffees.py tests/phase_04/test_coffee_filters.py`) returns **23 passed** — exceeding the plan's required ≥15 router + ≥8 filter = 23 minimum.

5. **Committed hook-clean as `7aabfc5`**. No `--no-verify`. The WIP commit `96017ba` remains in history (it was already merged into main via `0520130`), but its content is functionally superseded by `7aabfc5`.

#### Test coverage (15 + 8 = 23 tests, all passing)

`tests/phase_04/test_routers_coffees.py`:

1. `test_list_coffees_renders_page` — authed GET `/coffees` → 200 + page HTML with `<h1` + "Coffees" + the filter form id.
2. `test_list_coffees_hx_request_returns_fragment_only` — HX-Request: true → body lacks `<html>` / `<!doctype>`.
3. `test_list_coffees_includes_responsive_layout_markers` — body contains both `hidden md:block` AND `md:hidden` after seeding one coffee (CAT-07 dual-layout shipped).
4. `test_create_coffee_minimal_valid` — POST minimal valid form → 200 + row fragment + `coffee-form-mount` OOB clear.
5. `test_create_coffee_with_array_round_trip` — POST with `advertised_flavor_note_ids=[fn1, fn2]` → array preserved as `[fn1, fn2]` on read-back.
6. `test_create_coffee_rejects_unknown_process` — POST `process="cold_brewed"` → 200 + form re-render with `text-red-700` styling + submitted name preserved.
7. `test_create_coffee_rejects_blank_name` — POST `name=""` → 200 + form re-render + submitted country preserved.
8. `test_create_coffee_extra_field_rejected` — POST with `is_admin="true"` → 200 + form re-render (T-04-MASS via `extra='forbid'`).
9. `test_coffee_detail_page_renders` — seed coffee + bag → GET /{id} → body contains coffee name + "Bags" + "Open new bag" + `id="bag-form-mount"`.
10. `test_coffee_detail_page_404_for_unknown_id` — GET /999999 → 404.
11. `test_edit_pre_populates_advertised_array` — seed coffee with `[fn1, fn2]` → GET /{id}/edit body contains hidden inputs for both ids.
12. `test_update_persists_array_change` — POST /{id} with `[fn1]` only → array becomes `[fn1]` on read-back.
13. `test_archive_marks_archived` — POST /archive → DB row.archived = True.
14. `test_csrf_missing_returns_403` — mismatched CSRF → 403.
15. `test_form_renders_roaster_autocomplete_attributes` — GET /new body contains the locked HX-4 + D-13 autocomplete attrs (`hx-trigger="input changed delay:350ms[target.value.length >= 2]"` + `hx-sync="this:replace"` + `id="roaster-dropdown"` + `name="roaster_id"`).

`tests/phase_04/test_coffee_filters.py`:

1. `test_filter_by_roaster_returns_only_matching`
2. `test_filter_by_country_returns_only_matching`
3. `test_filter_by_process_returns_only_matching`
4. `test_filter_archived_false_excludes_archived` — default behavior locks "non-archived only".
5. `test_filter_archived_true_returns_only_archived` — UI-SPEC lock — archived=true is NOT a union.
6. `test_filter_combinations_logical_and` — three-dim intersection.
7. `test_hx_request_with_filters_returns_fragment` — HX-Request + filter params → fragment branch, no `<html>`.
8. `test_filter_form_hx_push_url_present` — D-03 contract test: the filter form carries `hx-push-url="true"`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] httpx 0.28 list-of-tuples form data silently sends no body**

- **Found during:** Task 3 resume (after the original WIP commit's pytest failure).
- **Issue:** Two tests (`test_create_coffee_with_array_round_trip`, `test_update_persists_array_change`) posted repeated form keys via `data=[("k","v"), ("k","v2"), ...]`. httpx 0.28 does not support that shape — the request is built with no Content-Type / Content-Length / body. The handler received an empty form, `name=""` tripped the required-field check, and the POST re-rendered the form at 200 with the row never persisted. Both tests then failed at `assert len(rows) == 1` (the row was never inserted).
- **Fix:** Switched both tests to the documented httpx shape `data={"k": [v1, v2], ...}` (dict whose values can be lists). The handler's `form_data.getlist("advertised_flavor_note_ids")` reads them identically once the body arrives.
- **Files modified:** `tests/phase_04/test_routers_coffees.py` (both tests + a docstring callout on the array round-trip test for future readers).
- **Commit:** `7aabfc5`

### Plan-acknowledged ship/defer choices (NOT deviations — documented per plan)

- **`GET /coffees/filters-panel` shipped** (plan flagged optional). ~20 LOC, identical context shape to the page filter form, useful when a new roaster surfaces via plan-04-11's mini-modal without a full page reload.
- **`selectinload(Coffee.roaster)` NOT used** — the router pre-resolves `roaster_name_map` + `flavor_note_names` dicts via single fan-out SELECTs and hands them to the template. Simpler than wiring SQLAlchemy relationship eagerness for a mix of FK lookups + arbitrary-id arrays (which selectinload doesn't natively handle).
- **CAT-07 mobile card-list collapse visual verification (375px no-horizontal-scroll) deferred** to Phase 12 Playwright per 04-VALIDATION.md Manual-Only Verifications table. The HTML markers are asserted in `test_list_coffees_includes_responsive_layout_markers`.

## Threat Surface

No new threat surface beyond the plan's threat register (T-04-CSRF, T-04-XSS, T-04-MASS, SQLi via filter params, array injection). All mitigations in place:

- CSRF: hidden input verbatim on every form; CSRFMiddleware enforces.
- XSS: Jinja autoescape ON globally; no `|safe`; filter values rendered via standard echo.
- Mass-assignment: `CoffeeCreate.model_config = ConfigDict(extra="forbid")`.
- SQLi: every filter param bound via SQLAlchemy `.where(Column == :param)` — no f-strings.
- Array injection: FastAPI `Form()` casts each entry to int; `field_validator(ge=1)` rejects non-positive ids.

## Contracts Locked for Downstream Plans

### For plan 04-09 (Bags CRUD)

- `app/templates/pages/coffee_detail.html` includes `<div id="bag-form-mount">` and `<div id="bag-list">` with the "Open new bag" button wired to `hx-get="/coffees/{coffee.id}/bags/new"` + `hx-target="#bag-form-mount"`. Plan 04-09's executor adds the endpoint + the `bag_form.html` fragment.
- Bag-list rendering on `coffee_detail.html` is a placeholder (`<ul>` over `bags` with date/weight metadata, empty-state copy). Plan 04-09's bag rows can replace this placeholder or render alongside.

### For plan 04-11 (Autocomplete + Mini-modal)

- `app/templates/fragments/coffee_form.html` contains the **chip-builder mount-point shell**:
  - `<div id="flavor-note-chips" class="flavor-note-chips-field">` — plan 04-11 adds `x-data="flavorNoteChips"`.
  - `<div id="flavor-note-chip-list">` — plan 04-11 replaces children with `<template x-for="chip in selectedChips">` rendering chip pills.
  - `<div id="flavor-note-hidden-inputs">` — plan 04-11 fills with a parallel `<template x-for>` emitting `<input type="hidden" name="advertised_flavor_note_ids" :value="chip.id">` per chip.
  - `<input name="flavor_note_query" autocomplete="off" hx-get="/flavor-notes/datalist" hx-trigger="input changed delay:350ms[target.value.length >= 2]" hx-sync="this:replace" hx-target="#flavor-note-dropdown" hx-swap="innerHTML">` — the autocomplete text input with the HX-4 mitigation attrs.
  - Server-rendered seed: 04-07 fills `#flavor-note-chip-list` and `#flavor-note-hidden-inputs` from `selected_flavor_notes` so the form survives a 200 re-render before Alpine hydrates. Plan 04-11's `flavorNoteChips` Alpine component takes over on client mount.
- Roaster autocomplete shell already wired: `<input name="roaster_query">` (text) + `<input type="hidden" name="roaster_id">` + `<div id="roaster-dropdown">` mount, all with the HX-4 + D-13 attrs locked.

### For Phase 5 (Brew Sessions)

- The four-dim filter list pattern (single GET handler with optional query params + HX-Request fragment branch + `hx-push-url="true"` on the filter form + `hx-include="this"`) is the reusable template for brew-session filtering.
- `flavor_note_name_map(db, ids=...)` is the canonical id→name resolver — Phase 5 brew-session views that surface advertised flavor notes should call it directly (same single-IN-query shape).

## Self-Check: PASSED

- **Files created (9):** all present at the documented paths in the worktree.
  - `app/services/coffees.py` (322 lines)
  - `app/routers/coffees.py` (645 lines)
  - `app/templates/pages/coffees.html` (71 lines)
  - `app/templates/pages/coffee_detail.html` (124 lines)
  - `app/templates/fragments/coffee_list.html` (50 lines)
  - `app/templates/fragments/coffee_row.html` (155 lines)
  - `app/templates/fragments/coffee_form.html` (237 lines)
  - `app/templates/fragments/coffee_filters_panel.html` (56 lines)
  - `tests/phase_04/test_coffee_filters.py` (255 lines)
- **Files modified (2):** `app/main.py` + `tests/phase_04/test_routers_coffees.py`.
- **Commits referenced** (all present in `git log`):
  - `a76d82b` — service + router + main.py wire-up
  - `211a1c6` — pages + fragments
  - `96017ba` — WIP test commit (superseded but kept in history via the merge `0520130`)
  - `7aabfc5` — hook-clean test finalization (this resume)
- **Tests:** 23 passed (15 router + 8 filter) per plan minimum; full Phase 4 suite green at 163 passed / 2 skipped.
- **Hooks:** `ruff format` clean; `ruff check` clean; this final test commit was created WITHOUT `--no-verify`.
