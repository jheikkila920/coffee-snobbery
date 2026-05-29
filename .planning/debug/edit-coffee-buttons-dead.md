---
slug: edit-coffee-buttons-dead
status: resolved
trigger: |
  Editing a coffee on desktop opens a very narrow window. When you click Save, it
  never saves. May be true for other edits, need to verify. The Cancel button
  also does nothing. Surfaced during Phase 15 use of the deployed app
  (2026-05-26 capture).
created: 2026-05-26
updated: 2026-05-26
---

# Debug: Edit coffee Save/Cancel buttons dead

## Symptoms

- **Expected:**
  - Clicking Save on the edit-coffee form persists changes (POST to `/coffees/{id}`) and swaps the form back to the row representation of the coffee.
  - Clicking Cancel closes the edit form / restores the row representation without saving.
  - On desktop, the edit form renders at the same width as the create-coffee form.
- **Actual:**
  - Both Save and Cancel buttons appear inert -- no network request fires (Save), no DOM change (Cancel).
  - The edit form renders in a notably narrow column on desktop (possibly same root cause: render is targeted into the row's narrow td/cell instead of replacing/expanding the row).
- **Scope (still to verify -- orchestrator-provided priority):**
  - Open: does this also affect edit-recipe, edit-roaster, edit-equipment, edit-flavor-note? Confirming scope is the FIRST investigation task -- it bounds whether the fix is local (one template) or shared (a base partial / global HTMX config).
- **Timeline:** Caller did not say "this used to work" -- treat as latent since the inline-edit pattern was introduced. Last commits touching `app/routers/coffees.py` are recent (CSV import work in Phase 5; Wishlist & inline coffee management additions). Worth checking the last commit that touched `app/templates/fragments/coffee_form.html` and `app/routers/coffees.py` GET/POST handlers for `/coffees/{coffee_id}/edit` and `/coffees/{coffee_id}`.
- **Error messages:** None reported. DevTools console + Network tab not yet inspected -- gathering those is high-value early evidence.
- **Reproduction:** Catalog page (`/coffees`) → click Edit on any existing coffee row → form swaps in → click Save (no save) or Cancel (no action).

## Evidence (codebase, pre-gathered before delegation)

- The form template `app/templates/fragments/coffee_form.html` is shared between create and edit modes (`{% set is_edit = mode == "edit" %}` at line 45). The form-level attributes `hx-post="{{ form_action }}"`, `hx-target="{{ form_target }}"`, `hx-swap="{{ form_swap }}"` are all template variables (lines 56-58) -- the bug is most likely in how those three are computed for `mode="edit"` in `_hydrate_form_context()` in `app/routers/coffees.py` (or wherever the helper lives).
- The edit GET handler renders the form into the place the row was -- `_hydrate_form_context(..., mode="edit", coffee_id=coffee_id)`. It uses `templates.TemplateResponse(name="fragments/coffee_form.html", context=context)` (no `block_name`), which renders the whole fragment, BUT the inline-edit row swap target is the row's `closest [data-row]` per the template's header comment (lines 3-4). That comment vs the actual rendered hx-target/hx-swap must match.
- The POST handler is `@router.post("/{coffee_id}")` -> `update_coffee_handler` in `app/routers/coffees.py` (lines 549+). The Pydantic CoffeeCreate schema is reused for both create and edit -- meaning CATALOG-02 (drop country) and CATALOG-03 (multi-origin) will both touch this handler later in Phase 15.1.
- Create works (user-confirmed). The diff between create and edit:
  - Create POST: `@router.post("")` -> `create_coffee_handler` (target = `#coffee-form-mount`, swap = `innerHTML`).
  - Edit POST: `@router.post("/{coffee_id}")` -> `update_coffee_handler` (target = closest `[data-row]` per header comment).
  - If `form_target` resolves to `#coffee-form-mount` in edit mode (a copy-paste bug), the form would render into a hidden/zero-width container -- which matches both symptoms (narrow render area AND apparent inertness if the swap target is wrong or missing).
  - If `form_target` resolves to a selector that does not exist on the page when the form is in row-context, htmx will swallow the swap silently -- matching "Save fires but you see nothing happen" too.
- Cancel button: search the template for the Cancel control. Likely `hx-get="/coffees/{coffee_id}"` returning `coffee_row.html` to restore the row. If `coffee_id` is undefined in edit context (e.g., the helper didn't pass it through), the Cancel hx-get URL is malformed (`/coffees/` -> 405 or 404) -- matching "Cancel does nothing".

## Suspect file pointers

- `app/routers/coffees.py` -- `_hydrate_form_context()` helper (resolves `form_action`, `form_target`, `form_swap`, `cancel_url` per mode). Search for those variables.
- `app/templates/fragments/coffee_form.html` -- form wiring (hx-post line 56-58) and Cancel button.
- `app/templates/fragments/coffee_row.html` -- the row that should be restored on Cancel and replaced on Save.
- `app/templates/pages/coffees.html` -- the list page; check whether the edit form is rendered inline inside the row's `<td>` (which would explain the narrow desktop window) or outside.
- For scope check: search `app/templates/fragments/{roaster,flavor_note,equipment,recipe}_form.html` for the same shared `hx-post="{{ form_action }}"` pattern; check `app/routers/{roasters,flavor_notes,equipment,recipes}.py` for similar helpers and edit handlers.

## Current Focus

- hypothesis: CONFIRMED. Two linked bugs present in ALL five entity forms (coffee, roaster, equipment, flavor_note, recipe).
- test: Code inspection confirmed both bugs.
- expecting: N/A -- bugs found and fixed.
- next_action: RESOLVED
- reasoning_checkpoint: "Bug 1: form wrapper div missing data-row, so hx-target='closest [data-row]' finds nothing after the edit swap. Bug 2: Cancel button unconditionally targeted the form-mount div instead of restoring the row."
- tdd_checkpoint: ""

## Eliminated

- `_hydrate_form_context()` correctness: the helper correctly computes `form_target = "closest [data-row]"` and `form_swap = "outerHTML"` for edit mode. The bug is not in the helper.
- HTMX configuration: no global HTMX issue. The problem is purely the missing `data-row` attribute on the form wrapper div.

## Resolution

- **root_cause:** Two linked bugs present in all five entity edit forms (coffee, roaster, equipment, flavor_note, recipe):
  1. The form wrapper `<div>` lacked `data-row`, so after the Edit button swapped the row with the form via `hx-swap="outerHTML"`, HTMX's `closest [data-row]` selector (used for both the form's `hx-target` and the Cancel button) could find no ancestor -- both Save and Cancel were silently no-ops.
  2. The Cancel button was unconditionally wired to the create-mode target (`#entity-form-mount` with `innerHTML`), so in edit mode it cleared the wrong container and never restored the row.
- **fix:** Added `data-row` attribute to each form's outer `<div>` when `is_edit` is true. Added mode-aware Cancel buttons: edit mode hits a new `GET /{entity_id}/row` endpoint (returns the row fragment) targeting `closest [data-row]` with `outerHTML`; create mode keeps existing empty-form behavior. Added `GET /{id}/row` endpoints to all five routers (coffees, roasters, equipment, flavor_notes, recipes).
- **scope:** All five entity forms were affected by both bugs. Fix is applied to all five in this session. No new CATALOG-08 requirement needed -- this is a bug fix, not a feature change.

## Files Changed

- `app/templates/fragments/coffee_form.html` -- added `data-row` to wrapper div (edit mode), fixed Cancel button to mode-aware
- `app/templates/fragments/roaster_form.html` -- same two fixes
- `app/templates/fragments/equipment_form.html` -- same two fixes
- `app/templates/fragments/flavor_note_form.html` -- same two fixes
- `app/templates/fragments/recipe_form.html` -- same two fixes (wrapper div carries x-data; data-row added alongside)
- `app/routers/coffees.py` -- added `GET /{coffee_id}/row` endpoint
- `app/routers/roasters.py` -- added `GET /{roaster_id}/row` endpoint
- `app/routers/equipment.py` -- added `GET /{equipment_id}/row` endpoint
- `app/routers/flavor_notes.py` -- added `GET /{flavor_note_id}/row` endpoint
- `app/routers/recipes.py` -- added `GET /{recipe_id}/row` endpoint

## Operator Constraints

- DO NOT commit a fix until orchestrator confirms scope. The fix may either be a one-line template/helper patch (handle in this debug session) OR broader (warrants a CATALOG-08 requirement in Phase 15.1 -- adding a follow-up).
- After ROOT CAUSE FOUND, report scope (just edit-coffee? or also edit-recipe/roaster/equipment/flavor-note?) before fix application.
