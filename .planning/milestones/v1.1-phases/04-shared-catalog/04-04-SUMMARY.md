---
phase: 04-shared-catalog
plan: 04
subsystem: roasters-crud
tags: [roasters, crud, htmx, autocomplete, hx-trigger, sec-06, t-04-mass, t-04-csrf, t-04-xss, wave-3]

# Dependency graph
requires:
  - phase: 04-shared-catalog
    provides: app/schemas/roaster.py (RoasterCreate) + app/dependencies/db.py::get_session + app/services/form_validation.py::errors_by_field (plan 04-02); app/models/roaster.py (Roaster — CITEXT unique) (plan 04-03); app/events.py CATALOG_ROASTER_* constants (plan 04-01)
  - phase: 02-auth
    provides: app/routers/auth.py handler shape + app/csrf.py CSRFFormFieldShim + tests/conftest.py seeded_admin_user
  - phase: 01-middleware
    provides: app/templates_setup.py templates + base.html (CSP nonce + HTMX core + listener)
provides:
  - app/services/roasters.py — sync Session CRUD + audit-event emit (CAT-01)
  - app/routers/roasters.py — 8 HTMX endpoints (list / list HTMX-fragment / new / empty-form / create / edit / update / archive / autocomplete) — establishes the universal Phase 4 catalog router template
  - app/templates/pages/roasters.html — list page
  - app/templates/fragments/roaster_list.html, roaster_row.html, roaster_form.html, roaster_modal.html — Roaster-specific fragments
  - app/templates/fragments/autocomplete_list.html — SHARED autocomplete dropdown (plan 04-05 flavor_notes reuses)
  - app/templates/fragments/empty.html — empty <div> for CSP-safe Cancel + modal close round-trips
  - HX-Trigger payload contract: `{"roaster-created": {"roaster_id": <int>, "name": <str>}}` — locked for plan 04-11 to consume
affects:
  - 04-05 (flavor-notes CRUD — reuses autocomplete_list.html shared fragment + the inline-expand + form-validation pattern)
  - 04-06 (coffees CRUD — consumes the inline-expand + form-validation re-render template)
  - 04-07 (equipment CRUD — same template)
  - 04-08 (recipes CRUD — same template)
  - 04-11 (autocomplete + mini-modal — consumes the HX-Trigger roaster-created event to pre-select in parent coffee form)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Phase 4 catalog router template: APIRouter(prefix=...) + sync Session via Depends(get_session) + require_user gate; GET '' returns page or fragment based on HX-Request header; POST '' returns row fragment (or empty body + HX-Trigger when as_modal=true); POST '/{id}/archive' soft-deletes and re-renders the row; GET '/list' is the autocomplete endpoint."
    - "Raw-form-read pattern for T-04-MASS: handlers use `await request.form()` instead of per-field Form(...) params so the Pydantic schema's extra='forbid' sees unknown fields. Per-field Form(...) would silently drop them, leaving the mass-assignment defense to the schema alone — which a probe with no header-set assertions might miss."
    - "Empty-string → None coercion for optional schema fields whose type rejects '' (HttpUrl, etc): the `_coerce_empty_to_none` helper maps blank form values to None before handing to the schema so a blank website doesn't trip HttpUrl validation. `name` and `notes` are deliberately excluded — name is required (blank → desired error), notes has a legitimate '' default."
    - "Error normalization for the form-fragment template: errors keyed outside the rendered fields are folded into the `_form` sentinel via `_normalize_errors`, so an extra-field rejection (T-04-MASS) still renders visibly. The form template renders error paragraphs only for known field keys."
    - "CSP-safe Cancel: Cancel buttons hx-get /roasters/empty-form (returns fragments/empty.html) instead of using onclick to clear the form mount — Phase 1 D-04 bans inline event handlers."
    - "HX-Trigger response header pattern (D-15 substrate): json-encoded `{event_name: payload}` dict on the response; Alpine listener (plan 04-11) dispatches as a CustomEvent. First use in the project; HTMX 2.0.10 documented feature."
    - "Shared autocomplete_list.html fragment with server-side match-highlight: split the name on the case-insensitive query, wrap the matched span with a literal `<strong>`. The three halves are each separately autoescaped by Jinja; no autoescape-bypass filter needed."
    - "OOB form-clear on row fragment: after a successful inline create, the row fragment appends `<div id='roaster-form-mount' hx-swap-oob='innerHTML'></div>` so the form mount empties without a second round-trip (04-RESEARCH Pattern 2)."

key-files:
  created:
    - app/services/roasters.py
    - app/routers/roasters.py
    - app/templates/pages/roasters.html
    - app/templates/fragments/roaster_list.html
    - app/templates/fragments/roaster_row.html
    - app/templates/fragments/roaster_form.html
    - app/templates/fragments/roaster_modal.html
    - app/templates/fragments/autocomplete_list.html
    - app/templates/fragments/empty.html
  modified:
    - app/main.py
    - tests/phase_04/test_routers_roasters.py

key-decisions:
  - "Use `await request.form()` instead of per-field `Form(...)` params in POST handlers so the Pydantic schema's `extra='forbid'` defense at the router boundary actually sees unknown form fields. FastAPI's per-field Form(...) silently drops anything not declared in the signature — leaving T-04-MASS to the schema alone. The async handler is FastAPI-canonical when reading the raw body."
  - "Form(default='') instead of Form(...) for `name`: empty form values would 422 before reaching our handler, breaking the D-04 contract that says validation errors render at 200 with the form re-renderer. The Pydantic schema's `min_length=1` is the single source of truth for the 'name required' rule. (Note: superseded by the raw-form-read pattern in the final implementation — kept here for the audit trail of why per-field Form() was not the right shape.)"
  - "_coerce_empty_to_none for {location, website}: empty form strings → None before schema validation. Without this, an unfilled optional website field would trip HttpUrl validation. The set is intentionally narrow — name (required, blank is the desired error) and notes (legitimate '' default) are excluded."
  - "_normalize_errors folds unknown-field errors into _form: when the schema rejects an extra field like `is_admin=true` (T-04-MASS probe), the `errors_by_field` pivot returns `{'is_admin': ...}` — but the form template only renders paragraphs for the form's own fields. Folding into `_form` keeps the error visible without proliferating template branches."
  - "CSRF primer helper in the test module rather than fixture modification: the conftest `authed_client` fixture pre-sets a literal placeholder cookie + header, but `starlette-csrf` validates tokens via `URLSafeSerializer.loads` (HMAC-signed). The helper deletes the cookie and GETs `/` to force the middleware to mint a real signed token, then rewires the client's default header. Inline rather than fixture-modifying so Phase-2 callers aren't disturbed."
  - "Unified row fragment (mode=row|card) over two row fragments: one template carries both desktop (table tr) and mobile (card div) shapes by inspecting `mode`. The alternative — two separate row fragments — would have duplicated the archived-styling, action-buttons, and Archive-confirm copy across two files."
  - "Page route is `GET /roasters` not `GET /roasters/` (no trailing slash). Matches the `/admin` precedent at `app/routers/admin.py:30`."
  - "Empty-form fragment for Cancel rather than Alpine `x-data` wrapper: keeps the server as single source of truth for the inline-expand flow and avoids loading a small Alpine component for a button that's almost always going to round-trip. CSP-banned `onclick` was not an option (Phase 1 D-04)."

patterns-established:
  - "Phase 4 catalog router universal template — plans 04-05 (flavor-notes), 04-06 (coffees), 04-07 (equipment), 04-08 (recipes), 04-09 (bags) all mirror the roasters router shape: APIRouter(prefix='/...') + sync Session via get_session + require_user gate + GET/POST handler pairs for create-update-archive + dedicated form/row/list fragments + (where applicable) autocomplete endpoint reusing autocomplete_list.html."
  - "Form-validation re-render at HTTP 200 (D-04 + SEC-06): every state-changing POST catches ValidationError, runs errors_by_field, normalizes unknown keys to _form, and re-renders the form fragment with values preserved. The template renders per-field error paragraphs (text-red-700) + input border-red-300 styling."
  - "HX-Trigger emit on `as_modal=true` POST (D-15): json-encoded `{event_name: payload}` dict on the response header; the Alpine listener in plan 04-11 consumes the event to pre-select the new entity in the parent form. Empty body + the trigger header is the contract; the response is otherwise a no-op."
  - "Shared autocomplete dropdown fragment (autocomplete_list.html): one template, both `/roasters/list` and (plan 04-05) `/flavor-notes/datalist` render through it. Context keys: items, query, entity (used in the + Create new copy), exact_match (suppresses + Create new when query matches an existing item), create_new_endpoint (the mini-modal launch URL)."

requirements-completed:
  - CAT-01

# Metrics
duration: 55min
completed: 2026-05-18
---

# Phase 4 Plan 04: Roasters CRUD Summary

**First complete CRUD entity surface in Phase 4 — establishes the inline-expand HTMX-fragment + Pydantic-v2 form-validation re-render + HX-Trigger mini-modal substrate + shared autocomplete-dropdown patterns that plans 04-05 through 04-09 follow verbatim.**

## Performance

- **Duration:** ~55 minutes
- **Tasks:** 2
- **Files created:** 9 (1 service + 1 router + 7 templates)
- **Files modified:** 2 (app/main.py + tests/phase_04/test_routers_roasters.py)

## Accomplishments

- **`app/services/roasters.py`** ships the full CAT-01 CRUD surface mirroring `app/services/credentials.py`'s structural template: sync `Session`, kwargs-only API after a leading `*`, single commit per write, structlog audit event at the end of each write transaction. Functions: `create_roaster`, `get_roaster`, `list_roasters` (with `include_archived` filter), `update_roaster` (Core `update()` so we can stamp `updated_at = func.now()` in the same statement), `archive_roaster` (soft-delete), `search_by_prefix` (D-13 autocomplete helper using CITEXT-native case-insensitive `ilike`).
- **`app/routers/roasters.py`** implements 8 endpoints under `/roasters`: list (page + HTMX fragment), new (form fragment, inline or modal), empty-form (Cancel round-trip), POST create (row fragment + OOB form-clear, OR empty body + HX-Trigger when `as_modal=true`), edit form, POST update, POST archive, GET autocomplete. POST handlers are async + read raw form via `await request.form()` so unknown fields reach the schema's `extra='forbid'` defense.
- **Seven templates** establish the visual + interaction contract for all Phase 4 catalog list surfaces:
  - `pages/roasters.html` — list page + h1 + 'Add roaster' CTA + form mount.
  - `fragments/roaster_list.html` — desktop table (md+) + mobile cards (md-) layouts, both delegating to `roaster_row.html` with a `mode` flag.
  - `fragments/roaster_row.html` — unified row partial covering both `mode="row"` (`<tr>`) and `mode="card"` (`<div>`) shapes; archived styling (italic + 'Archived' pill); Edit + Archive HTMX buttons; hx-confirm copy carrying UI-SPEC Q2 warning text; OOB form-clear when `include_oob_form_clear` is set.
  - `fragments/roaster_form.html` — inline-expand form fragment, three modes (`create` / `edit` / `modal`); error styling (`border-red-300` on inputs + `<p class="text-red-700">` per field, plus `_form` sentinel for non-field errors); CSRF hidden input verbatim from `pages/setup.html:10`; Cancel via `hx-get /roasters/empty-form`.
  - `fragments/roaster_modal.html` — mini-modal chrome wrapping the same form with `as_modal=true`; static markup only (the Alpine miniModal driver lands in plan 04-11).
  - `fragments/autocomplete_list.html` — **shared** `<ul role="listbox">` fragment, server-side match-highlight via literal `<strong>`, '+ Create new' affordance when no exact match. Plan 04-05 (flavor-notes) reuses this fragment.
  - `fragments/empty.html` — `<div></div>` for the Cancel + modal-close round-trips.
- **`app/main.py`** modified to include the roasters router after the admin router. No middleware changes — middleware order is locked by Phase 1 D-17 + Phase 2 D-15.
- **16 real router tests** replace the Wave-0 stub in `tests/phase_04/test_routers_roasters.py`. Coverage: anon→401, authed page render, HX-Request→fragment, create-valid→row, create-blank→form-with-error, create-extra-field→form-rejection (T-04-MASS), create-as_modal→HX-Trigger, edit-pre-populated, update-persists, archive-marks, autocomplete-short-q→empty, autocomplete-matches, autocomplete-+Create-new, autocomplete-no-+Create-on-exact-match, CSRF-missing→403, service-layer prefix search case-insensitive.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement service + router + main.py wiring** — `6395fc2` (feat)
2. **Task 2: Author 7 templates + 16 real router tests + router refinements** — `35b7f09` (feat)

## Files Created/Modified

### Service + router (created)

- `app/services/roasters.py` (175 LOC) — full CAT-01 CRUD + autocomplete helper; CATALOG_ROASTER_{CREATED,UPDATED,ARCHIVED} events emitted with `user_id` (NOT `by_user_id`) per Phase 1 D-14 alignment.
- `app/routers/roasters.py` (290 LOC) — 8 endpoints, raw-form-read pattern for T-04-MASS, empty-to-None coercion for optional fields, error normalization for unknown-field rejections, HX-Trigger emit on `as_modal=true` create.

### Templates (created)

- `app/templates/pages/roasters.html` — list page; extends base.html; h1 `text-2xl font-semibold`; 'Add roaster' CTA using `bg-espresso-700` (UI-SPEC Q1).
- `app/templates/fragments/roaster_list.html` — desktop table + mobile cards.
- `app/templates/fragments/roaster_row.html` — unified row partial (mode=row|card); archived styling; Edit/Archive HTMX buttons with hx-confirm; conditional OOB form-clear.
- `app/templates/fragments/roaster_form.html` — three-mode inline form (create/edit/modal); error styling; CSRF hidden input; Cancel via empty-form round-trip.
- `app/templates/fragments/roaster_modal.html` — mini-modal chrome (Phase 4-11 wires the Alpine driver).
- `app/templates/fragments/autocomplete_list.html` — SHARED autocomplete dropdown with server-side match-highlight; reused by plan 04-05.
- `app/templates/fragments/empty.html` — `<div></div>`.

### Config + tests (modified)

- `app/main.py` — added `from app.routers import roasters as roasters_router` + `app.include_router(roasters_router.router)` after the admin router include.
- `tests/phase_04/test_routers_roasters.py` — replaced the 1-line `pytest.skip` Wave-0 stub with 16 real tests + a `_prime_csrf` helper + a `clean_roasters` fixture.

## Decisions Made

- **Async POST handlers + `await request.form()` over per-field `Form(...)` params.** The schema's `extra='forbid'` defense (T-04-MASS) only fires when unknown fields are actually passed to the schema constructor. Per-field `Form(...)` signatures silently drop anything not declared, so a `is_admin=true` probe would have gone undetected at the router boundary. The async path reads the raw `FormData` and hands every non-flow-flag key to the schema — exercising the defense as intended.
- **`_coerce_empty_to_none` for `{location, website}` only.** Blank optional fields → `None` before schema validation; without this, an empty `website=""` form field would trip Pydantic's `HttpUrl` validation. The set is intentionally narrow: `name` is required (blank → desired error), `notes` has a legitimate `""` default that survives schema validation (`Field("", max_length=4000)` accepts empty string).
- **`_normalize_errors` folds unknown-field errors into `_form`.** The form template renders error paragraphs only for known fields (name/location/website/notes) plus a `_form` sentinel for non-field errors. The T-04-MASS rejection lands on `is_admin` — without normalization, the error would silently disappear in the rendered HTML. Folding into `_form` surfaces the error to the user.
- **Unified row fragment (mode=row|card) over two fragments.** One template carries both desktop (`<tr>`) and mobile (`<div>`) shapes via a `mode` flag. The alternative — `roaster_row_desktop.html` + `roaster_row_mobile.html` — would have duplicated archived-styling, action buttons, and confirm copy across two files. The HTMX edit-swap target works either way because both shapes carry `id="roaster-{{ id }}" data-row`.
- **OOB form-clear via `hx-swap-oob` on the row fragment** rather than a separate fragment include. After a successful inline create, the row response includes `<div id="roaster-form-mount" hx-swap-oob="innerHTML"></div>` which HTMX swaps out-of-band into the form mount, clearing it. Saves a round-trip vs. having the client `hx-get /roasters/empty-form` after every successful create.
- **CSP-safe Cancel via `hx-get /roasters/empty-form`** rather than Alpine `x-data="{ ... }"` wrapper or banned `onclick`. The empty-form route returns `fragments/empty.html` (literal `<div></div>`) and keeps the server as single source of truth for the inline-expand flow. Alpine would add load for a button that's almost always going to round-trip; `onclick` is CSP-banned (Phase 1 D-04).
- **`_prime_csrf` helper in the test module rather than fixture modification.** The conftest `authed_client` fixture is Phase-2 substrate consumed by every Phase 4 test plan; mutating it would risk regressions in plans 04-05..04-11. The helper is inline and explicit — every test that POSTs documents its CSRF prime up front. Future Phase 4 router tests copy the same helper (or import it).
- **Page route is `GET /roasters` not `GET /roasters/`** (no trailing slash). Matches the `/admin` precedent at `app/routers/admin.py:30`. FastAPI/Starlette serves both with `redirect_slashes=True`, but the canonical URL is the one without the trailing slash.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] T-04-MASS defense was not actually exercised at the router boundary**

- **Found during:** Task 2 (running `test_create_roaster_extra_field_rejected`)
- **Issue:** The plan's action body specified per-field `Form(...)` signatures: `name: str = Form(...)`, `location: str | None = Form(None)`, etc. With this shape, FastAPI silently drops form keys that aren't in the signature — so an `is_admin=true` form field never reaches the Pydantic schema, and the `extra='forbid'` defense never fires. The test was failing because the router responded with a successful row create (the schema only saw `name`).
- **Fix:** Converted POST handlers to `async def` and replaced per-field params with `await request.form()` + filter out the CSRF/flow-flag keys + hand the rest to the schema. The schema now correctly rejects unknown fields with a ValidationError, the router re-renders the form fragment at 200, and the test passes.
- **Files modified:** `app/routers/roasters.py` (committed in `35b7f09`)
- **Verification:** `test_create_roaster_extra_field_rejected` passes — POST with `is_admin=true` returns 200 + form fragment containing `text-red-700`.

---

**2. [Rule 1 — Bug] `Form(...)` rejects empty form values with 422 instead of falling through to the schema's `min_length=1`**

- **Found during:** Task 2 (running `test_create_roaster_blank_name_returns_form_with_error`)
- **Issue:** FastAPI's `Form(...)` (with `Ellipsis` as default) treats an empty form value (`name=`) as a missing field and returns 422. The D-04 contract says validation errors must render at 200 with the form fragment + errors. So `name=""` was 422'ing before reaching our handler.
- **Fix:** Changed signatures to `Form("")` so empty strings reach the handler — then the Pydantic schema's `min_length=1` does the validation and the router re-renders the form at 200. (Subsequently superseded by the raw-form-read refactor in Deviation 1, which moot this — but the rationale is the same: the schema layer is the single source of truth for required-field rules per SEC-06.)
- **Files modified:** `app/routers/roasters.py` (committed in `35b7f09`)
- **Verification:** `test_create_roaster_blank_name_returns_form_with_error` passes — POST with `name=""` returns 200 + form fragment with `text-red-700` + the user's submitted `location="Somewhere"` preserved in the re-render.

---

**3. [Rule 1 — Bug] Empty website form value trips Pydantic `HttpUrl` validation**

- **Found during:** Task 2 (running `test_update_roaster_persists_changes`)
- **Issue:** The update test submits `{name, location, website, notes}` all with empty strings except name. `website=""` passes through the raw-form read into `RoasterCreate(website="")`, which fails because `HttpUrl` rejects the empty string. The update was silently re-rendering the form (200) instead of persisting the change.
- **Fix:** Added `_coerce_empty_to_none` helper that maps `""` → `None` for the `{location, website}` set before handing to the schema. Schema sees `website=None` and validates cleanly (`HttpUrl | None = None`). The router proceeds to update the row.
- **Files modified:** `app/routers/roasters.py` (committed in `35b7f09`)
- **Verification:** `test_update_roaster_persists_changes` passes — DB shows the new name after the POST.

---

**4. [Rule 2 — Missing Critical] Unknown-field validation errors don't render in the form fragment**

- **Found during:** Task 2 (debugging `test_create_roaster_extra_field_rejected` after Deviation 1)
- **Issue:** After the raw-form-read fix, the schema correctly rejects `is_admin=true` with a `ValidationError` whose `errors_by_field` pivot returns `{"is_admin": "..."}`. But the form fragment template renders error paragraphs only for the four known field keys (`name`, `location`, `website`, `notes`) + the `_form` sentinel. The `is_admin` error was silently dropped from the rendered HTML — the user would see a clean form re-render with no indication of what went wrong.
- **Fix:** Added `_normalize_errors` helper that folds any error key outside `{name, location, website, notes, _form}` into the `_form` sentinel. The form template's `{% if errors.get('_form') %}` branch now renders the rejection as a top-of-form generic message ("`is_admin: Extra inputs are not permitted`").
- **Files modified:** `app/routers/roasters.py` (committed in `35b7f09`)
- **Verification:** `test_create_roaster_extra_field_rejected` passes — POST with `is_admin=true` returns 200 + form fragment containing `text-red-700`.

---

**5. [Rule 1 — Bug] `authed_client` fixture's placeholder CSRF token fails `starlette-csrf` signature verification**

- **Found during:** Task 2 (first run of any test that POSTs)
- **Issue:** The `tests/phase_04/conftest.py` `authed_client` fixture pre-sets the literal string `"test-csrf-token-phase04-fixture"` as both the `csrftoken` cookie and the `X-CSRF-Token` header. But `starlette-csrf`'s `_csrf_tokens_match` runs `URLSafeSerializer.loads` (HMAC-signed) on both — and a literal string fails the signature check. Every POST 403'd before reaching the handler.
- **Fix:** Added a `_prime_csrf` helper in the test module: it deletes the placeholder cookie, GETs `/` (which forces `CSRFMiddleware.send` to mint a real signed token because the request now has no cookie), then re-wires the client's default cookie + `X-CSRF-Token` header to the freshly minted token. Every POST-exercising test calls `_prime_csrf(authed_client)` before its first POST.
- **Files modified:** `tests/phase_04/test_routers_roasters.py` (committed in `35b7f09`)
- **Verification:** All 16 router tests pass. The conftest fixture is unchanged — the helper is the per-plan workaround.

---

**Total deviations:** 5 auto-fixed (3 Rule 1 bugs, 2 Rule 2 missing-critical).

**Impact on plan:** All five deviations stay inside the files the plan already names in `files_modified`. The CSRF-primer helper is a test-time workaround for a conftest substrate quirk that downstream Phase 4 plans (04-05..04-11) will encounter too — documenting the helper here means future plans can copy it instead of rediscovering the issue. The router refinements (async + raw-form-read + coerce-empty-to-none + normalize-errors) are the canonical Phase 4 catalog router shape — plans 04-05..04-09 should mirror them verbatim.

## Issues Encountered

- **Docker container is image-baked, not bind-mounted.** Every verification step required `docker cp app/services/roasters.py coffee-snobbery:/app/app/services/roasters.py` (and equivalent for each file) before running tests inside the container. Plan 04-03 documented this same friction; the structural fix is a `dev` compose profile or a `docker compose build && docker compose up -d coffee-snobbery` cycle per task — out of scope for this plan.
- **`docker compose exec` resolves `.env` from cwd; the worktree has no `.env`.** Used `docker exec coffee-snobbery ...` directly throughout, which bypasses the env-file resolution.
- **Pre-existing test-isolation flake** in `tests/services/test_credentials.py::test_orphan_ciphertext_returns_none_and_emits` (predates this plan; documented in 04-01 SUMMARY). Did not fire during this plan's runs.
- **Worktree base SHA does not include the Phase 4 context docs** (CONTEXT/RESEARCH/PATTERNS/UI-SPEC/VALIDATION/DISCUSSION-LOG). Read them from absolute paths in the parent repo (`C:/Claude/Coffee-Snobbery/.planning/phases/04-shared-catalog/04-*.md`). Same friction documented in 04-01 / 04-02 / 04-03 issues.

## User Setup Required

None — this plan ships routes + templates + tests only. No new env vars, no external service configuration.

## Verification

Plan-stated verify commands + `<done>` criteria:

- **Task 1 verify:** `docker exec coffee-snobbery python -c "from app.routers.roasters import router; from app.services.roasters import create_roaster, list_roasters, search_by_prefix; print(router.prefix, 'ok')"` → `/roasters ok` ✓
- **Task 1 done criteria:**
  - `grep -c "HX-Trigger" app/routers/roasters.py` → `6` ✓ (≥1 required)
  - `grep -c "include_router(roasters_router" app/main.py` → `1` ✓
  - `grep -c "CATALOG_ROASTER" app/services/roasters.py` → `6` ✓ (≥3 required)
  - `docker exec coffee-snobbery curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/roasters/list?q=x` → `401` ✓ (unauthenticated)
- **Task 2 verify:** `docker exec coffee-snobbery python -m pytest -q tests/phase_04/test_routers_roasters.py -x` → `16 passed, 1 warning in 3.55s` ✓
- **Task 2 done criteria:**
  - 16 tests passing (≥15 required) ✓
  - `grep -E '\|safe' app/templates/fragments/roaster*.html app/templates/pages/roasters.html app/templates/fragments/autocomplete_list.html` → no matches ✓
  - `grep -E 'hx-on:' app/templates/fragments/roaster*.html app/templates/pages/roasters.html` → no matches ✓
  - `grep -c 'X-CSRF-Token' app/templates/fragments/roaster_form.html` → `2` ✓ (≥1 required — one is the hidden input, one is in the comment doc)
  - GET `/roasters` with valid session cookie → 200 + HTML containing `<h1` with `Roasters` ✓ (verified via direct TestClient probe)
  - `SELECT COUNT(*) FROM roasters` works (table exists from plan 04-03) ✓

**Wave-wide regression check:** `docker exec coffee-snobbery python -m pytest -q tests/phase_04/` → `80 passed, 7 skipped, 7 warnings in 5.16s` (was 49 passed, 10 skipped after plan 04-03; this plan adds 16 router tests + replaces 1 Wave-0 stub = net +17 passed, +1 file no longer skipped, −1 stub still skipped that was the original; the remaining 7 skipped are the un-replaced Wave-0 stubs that subsequent plans 04-05..04-11 fill).

**Full suite:** `docker exec coffee-snobbery python -m pytest -q` → `193 passed, 9 skipped, 10 xfailed, 34 warnings in 12.27s` (was 176 passed; net +17). No regressions traced to this plan.

## Threat Coverage

| Threat ID | Component | Mitigation | Test |
|-----------|-----------|------------|------|
| T-04-CSRF | All state-changing roaster routes (POST /, /{id}, /{id}/archive) | Every form template carries the hidden `X-CSRF-Token` input verbatim from `pages/setup.html:10`; `CSRFFormFieldShim` hoists it into the header; `CSRFMiddleware` enforces double-submit. | `test_csrf_missing_returns_403` (POST /roasters with mismatched CSRF → 403) ✓ |
| T-04-XSS | All templates rendering `roaster.name`, `roaster.location`, `roaster.website`, `roaster.notes`, autocomplete query `q` | Jinja autoescape ON globally (`templates_setup.py:43`); `|safe` not used anywhere in the new templates; match-highlight wraps with literal `<strong>` around already-autoescaped halves. | Grep check: `grep -E '\|safe'` → no matches ✓ |
| T-04-MASS | POST /roasters, POST /roasters/{id} | `RoasterCreate` declares `model_config = ConfigDict(extra="forbid")`; handler uses `await request.form()` so unknown fields reach the schema; `_normalize_errors` folds the rejection into the visible form-fragment re-render. | `test_create_roaster_extra_field_rejected` (POST with `is_admin=true` → 200 + form with error rendered) ✓ |
| (SQLi) | GET /roasters/list (CITEXT prefix filter) | `select(Roaster).where(Roaster.name.ilike(f"{q}%"))` — `q` is interpolated into the LIKE pattern string but SQLAlchemy parameterizes the result; no raw SQL concatenation. CITEXT makes `ilike` case-insensitive natively. | `test_autocomplete_returns_matches` (probes prefix-only behavior) + `test_search_by_prefix_case_insensitive` (service-layer) ✓ |
| (tab-nabbing) | Roaster website link in row/card | Template renders `<a href="..." rel="noopener noreferrer" target="_blank">` per UI-SPEC §Security. Roaster URLs are admin-curated, so risk is low. | Manual template review — no test (UI-SPEC compliance check). |

## Next Plan Readiness

- **Plan 04-05 (flavor-notes CRUD router)** ready — can `from app.services import roasters as roasters_service` as the structural template; reuses `fragments/autocomplete_list.html` directly via `/flavor-notes/datalist`. The CSRF primer helper + `_coerce_empty_to_none` + `_normalize_errors` + the raw-form-read async POST shape are the canonical pattern.
- **Plan 04-06 (coffees CRUD)** ready — mirror the roasters router shape; add the autocomplete-on-roaster-and-flavor-note input wiring per UI-SPEC §"Autocomplete Dropdown".
- **Plan 04-07 (equipment CRUD)** ready — same template minus the autocomplete endpoint (equipment isn't autocompleted from another form).
- **Plan 04-08 (recipes CRUD)** ready — same template; adds the `HX-Redirect` response header for the D-12 duplicate flow (separate net-new pattern, not derived from this plan).
- **Plan 04-09 (bag photo upload)** ready — independent of this plan (operates on bags directly).
- **Plan 04-11 (autocomplete + mini-modal)** ready — consumes `HX-Trigger: roaster-created` with the documented `{roaster_id, name}` payload to pre-select the new roaster in the parent coffee form. The autocomplete_list.html shared fragment and the `/roasters/list` endpoint are the contracts.

## Self-Check

- `app/services/roasters.py` exists: FOUND
- `app/routers/roasters.py` exists: FOUND
- `app/main.py` modified (include_router(roasters_router.router)): FOUND
- `app/templates/pages/roasters.html` exists: FOUND
- `app/templates/fragments/roaster_list.html` exists: FOUND
- `app/templates/fragments/roaster_row.html` exists: FOUND
- `app/templates/fragments/roaster_form.html` exists: FOUND
- `app/templates/fragments/roaster_modal.html` exists: FOUND
- `app/templates/fragments/autocomplete_list.html` exists: FOUND
- `app/templates/fragments/empty.html` exists: FOUND
- `tests/phase_04/test_routers_roasters.py` 16 real tests (replaced Wave-0 stub): FOUND
- Commit `6395fc2` (Task 1) in `git log`: FOUND
- Commit `35b7f09` (Task 2) in `git log`: FOUND
- Container verify `pytest -q tests/phase_04/test_routers_roasters.py` returns `16 passed`: FOUND
- Wave-wide phase_04 regression `pytest -q tests/phase_04/` returns `80 passed, 7 skipped`: FOUND
- Full suite `pytest -q` returns `193 passed, 9 skipped, 10 xfailed`: FOUND

## Self-Check: PASSED

---
*Phase: 04-shared-catalog*
*Plan: 04*
*Completed: 2026-05-18*
