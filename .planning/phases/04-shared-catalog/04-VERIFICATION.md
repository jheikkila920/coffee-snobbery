---
phase: 04-shared-catalog
verified: 2026-05-19T12:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Recipe step builder: open /recipes/new, add 2 steps, verify cumulative water + time update live in the step row delta readout, verify pour-timeline preview reacts in real time"
    expected: "Each step's delta row shows '+Xg · +mm:ss'; the timeline preview shows proportional vertical segments that resize as time values change"
    why_human: "Alpine CSP-build reactivity (x-for + computed getters) cannot be driven by pytest; requires a real browser"
  - test: "Autocomplete-on-create-on-save: open /coffees/new, type 2+ chars in the roaster field, verify the dropdown appears; click '+ Create new roaster', enter a name, save — verify the new roaster is pre-selected in the parent form"
    expected: "Dropdown appears after 350ms debounce; mini-modal opens; after successful POST the HX-Trigger closes the modal and the new roaster name appears in the roaster input"
    why_human: "HX-Trigger → CustomEvent → Alpine listener chain requires a browser event loop; pytest drives HTTP only"
  - test: "Flavor note chip widget: open /coffees/new, type 2+ chars in the flavor note field, select a result — verify a chip appears; add a second flavor note; submit the form — verify both flavor-note IDs land in the DB"
    expected: "Chips render immediately on selection; hidden inputs track the selected IDs; form submits the repeated advertised_flavor_note_ids keys correctly"
    why_human: "Alpine flavorNoteChips x-for blocks + parallel hidden inputs are not observable via pytest HTTP assertions"
  - test: "Mini-modal dirty-check: open the roaster mini-modal, type something, then press ESC or click backdrop — verify a confirm prompt appears"
    expected: "Browser confirm('Are you sure you want to close?') (or equivalent Alpine-driven confirm) fires before the modal closes when the form is dirty"
    why_human: "Alpine dirty flag + browser confirm() behavior requires a real browser or Playwright"
  - test: "Coffee list responsive layout: open /coffees at 375px viewport width"
    expected: "Table header is hidden (hidden md:block class present but not visible); card list is visible (md:hidden block at <768px); no horizontal scrollbar"
    why_human: "CSS visibility at breakpoints requires Playwright or manual browser check at 375px"
  - test: "Bag photo upload with device camera: on a mobile device, tap 'Upload photo' on a bag row"
    expected: "iOS/Android device camera opens (if capture='environment' is present) OR the file picker opens without camera shortcut; either path should still work for upload"
    why_human: "capture='environment' attribute is absent from the file input (see Gaps section). Functional upload still works; mobile camera-shortcut UX needs manual verification"
---

# Phase 4: shared-catalog Verification Report

**Phase Goal:** Coffees, roasters, flavor notes, equipment, and recipes are fully CRUD'd via the shared catalog UI; autocomplete-on-create-on-save smooths roaster + flavor-note entry; recipes have a step builder with cumulative water + time offsets and a duplicate action; bag photos upload through a hardened pipeline (magic-byte → Pillow re-encode → EXIF strip → resize → 400px thumbnail). Pydantic v2 form validation with numeric ranges is now the universal pattern for any state-changing endpoint.
**Verified:** 2026-05-19T12:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A logged-in user can create a roaster, flavor note, coffee, equipment item, and a recipe with a multi-step pour timeline — all five visible to every household user (shared catalog). Autocomplete-on-create works for roasters and flavor notes inside the coffee form. | VERIFIED | `app/services/{roasters,flavor_notes,coffees,equipment,recipes}.py` all exist (150–250+ LOC each), real CRUD service functions confirmed. `app/routers/{roasters,flavor_notes,coffees,equipment,recipes}.py` all registered in `app/main.py:222–226`. `app/static/js/alpine-components/autocomplete.js` registers `autocomplete` + `flavorNoteChips` factories; `mini-modal.js` ships the mini-modal. `app/templates/fragments/autocomplete_list.html` carries the `+ Create new` affordance. Router tests (16+ tests each for roasters, coffees, bags, photos, flavor_notes, equipment, recipes) confirm non-stub implementations. |
| 2 | The coffees list renders as a table on desktop (≥768px) and collapses to a card list at <768px; filters by roaster, country, process, and archived state work; archive (not delete) is the default for any entity referenced by other rows. | VERIFIED | `app/templates/fragments/coffee_list.html` contains `class="hidden md:block"` (desktop table) and `class="md:hidden space-y-3"` (mobile cards). `app/routers/coffees.py:246–258` accepts `roaster_id`, `country`, `process`, `archived` query params and composes SQLAlchemy `.where()` clauses. All five entity services expose `archive_*` (not delete) functions: `archive_roaster`, `archive_coffee`, `archive_equipment`, `archive_flavor_note`, `archive_recipe`. |
| 3 | The recipe step builder lets a user add, remove, and reorder pours; cumulative water (grams) and time offset (seconds) computed live; "Duplicate recipe" creates an editable copy; pour-timeline preview renders as a vertical bar with proportional segments. | VERIFIED | `app/static/js/alpine-components/recipe-step-builder.js` implements `addStep()`, `removeStep(i)`, `moveUp(i)`, `moveDown(i)`, `deltaWater(i)`, `deltaTime(i)` (cumulative offsets), `get timelineSegments()` (proportional ratio computation). `app/templates/fragments/pour_timeline.html` renders stacked divs with `:style="'flex-basis: ' + Math.max(seg.ratio, 4) + '%'"`. `app/services/recipes.py::duplicate_recipe` does a deep-copy `[dict(s) for s in src.steps]` + commit. `app/routers/recipes.py::duplicate_recipe_handler` returns `200 + HX-Redirect: /recipes/{new_id}/edit`. |
| 4 | Bag photo upload accepts JPEG/PNG/WebP up to 5MB, rejects anything failing magic-byte check, re-encodes via Pillow (strips trailing/polyglot bytes), strips EXIF, resizes to ≤1600px wide and generates a 400px thumbnail; photos served via routers/photos.py (not StaticFiles) with Content-Type set and Cache-Control: private, max-age=31536000, immutable. | VERIFIED | `app/services/photos.py` (407 LOC): `_verify_magic_bytes` → `probe.verify()` → re-open + load → `getexif().clear()` → `image.convert("RGB")` → `thumbnail((1600,1600))` → `save("JPEG", no exif=)` → `thumbnail((400,400))`. `app/routers/photos.py::serve_photo` returns `FileResponse` with `"Cache-Control": "private, max-age=31536000, immutable"`, `"Content-Type": "image/jpeg"`. 12 real tests in `test_services_photos.py` cover magic-byte reject, EXIF strip, polyglot strip, oversize reject, decompression bomb reject, round-trip, replace, sweep. |
| 5 | Every form (coffee, equipment, recipe, roaster, flavor note, bag) round-trips through a Pydantic v2 schema with explicit numeric ranges. | VERIFIED | All six schemas confirmed: `RecipeCreate` (dose 1-200g, water 1-3000g, temp 0-100°C); `StepSchema` (water 0-2000g, time 0-3600s); `CoffeeCreate` (roaster_id ≥1, advertised_flavor_note_ids ≥1 each); `BagCreate` (coffee_id ≥1, weight_grams 1-10000g); `EquipmentCreate` (type regex + brand/model min_length=1); `RoasterCreate` (name min_length=1). All use `ConfigDict(extra="forbid")`. `test_schemas_form_validation.py` has 37 test functions (range violations, mass-assignment rejection, errors_by_field pivot). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/photos.py` | SEC-07 photo pipeline primitives | VERIFIED | 407 LOC; all functions present: `process_and_save`, `replace_photo`, `unlink_safe`, `sweep_orphans`, `_sweep_unreferenced`, `_is_safe_photo_filename`, `_verify_magic_bytes` |
| `app/events.py` | Full catalog.* taxonomy | VERIFIED | 22 CATALOG_* constants in `__all__`; confirmed in source |
| `app/schemas/{coffee,roaster,flavor_note,equipment,recipe,bag}.py` | 6 Pydantic v2 form schemas | VERIFIED | All 6 exist; all use `ConfigDict(extra="forbid")` + `Field(ge=...,le=...)` constraints |
| `app/services/{roasters,flavor_notes,coffees,equipment,recipes,bags}.py` | 6 CRUD services | VERIFIED | All 6 exist; confirmed substantive implementations |
| `app/routers/{roasters,flavor_notes,coffees,equipment,recipes,bags,photos}.py` | 7 routers | VERIFIED | All 7 exist; all registered in `app/main.py` |
| `app/models/{roaster,flavor_note,coffee,equipment,recipe}.py` | 5 catalog models | VERIFIED | All 5 exist in `app/models/` |
| `app/migrations/versions/p4_shared_catalog.py` | Migration: 5 tables + bag FK + photo_filename | VERIFIED | File exists; creates roasters, flavor_notes, coffees, equipment, recipes tables; adds bags.photo_filename + bags.coffee_id FK with RESTRICT; GIN index via raw op.execute |
| `app/templates/pages/{coffees,equipment,flavor_notes,recipes,roasters,coffee_detail}.html` | 6 page templates | VERIFIED | All 6 exist |
| `app/templates/fragments/{coffee,roaster,flavor_note,equipment,recipe,bag,photo}_*.html` | Entity-specific fragments | VERIFIED | All confirmed present in directory listing |
| `app/templates/fragments/autocomplete_list.html` | Shared autocomplete dropdown | VERIFIED | Present; contains `+ Create new` affordance |
| `app/static/js/alpine-components/recipe-step-builder.js` | Step builder Alpine component | VERIFIED | Substantive: addStep/removeStep/moveUp/moveDown/deltaWater/deltaTime/timelineSegments |
| `app/static/js/alpine-components/autocomplete.js` | Autocomplete + chip widget | VERIFIED | Registers `autocomplete` + `flavorNoteChips`; keyboard nav; HX-Trigger listener |
| `app/static/js/alpine-components/mini-modal.js` | Mini-modal Alpine component | VERIFIED | ESC/backdrop/dirty-check + `#modal-mount` close mechanism |
| `app/static/js/photo-upload.js` | Canvas downscale client-side | VERIFIED | Capture-phase submit listener + DataTransfer file swap + `htmx.trigger` retrigger |
| `tests/phase_04/` | 16 test files | VERIFIED | 16 files present; key files have real tests (12–16+ test functions); conditional postgres-skip guards are not stub skips |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/services/photos.py` | `PIL.Image` | `from PIL import Image` + `Image.open` + `Image.thumbnail` + `Image.save` | VERIFIED | Confirmed in source |
| `app/services/photos.py::process_and_save` | magic-byte gate | `_verify_magic_bytes(raw_bytes[:12])` called before `Image.open` | VERIFIED | Line 193 of photos.py |
| `app/services/photos.py::sweep_orphans` | `bags.photo_filename` | `select(Bag.photo_filename).where(Bag.photo_filename.isnot(None))` | VERIFIED | Lazy import pattern in sweep_orphans body |
| `app/routers/bags.py POST /bags/{id}/photo` | `app/services/photos.py::process_and_save` | `attach_or_replace_photo` → `photos_service.process_and_save(blob)` | VERIFIED | Confirmed in bags router and service |
| `app/routers/photos.py` | `FileResponse` with D-06 headers | Returns `FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable", ...})` | VERIFIED | Confirmed in `app/routers/photos.py:107–115` |
| `app/routers/coffees.py` | Four-dimension filter | Query params `roaster_id`, `country`, `process`, `archived` compose `.where()` clauses | VERIFIED | Confirmed in coffees router list handler |
| `app/routers/recipes.py::duplicate_recipe_handler` | `recipes_service.duplicate_recipe` | `copy = recipes_service.duplicate_recipe(db, source_id=recipe_id, ...)` + `HX-Redirect` | VERIFIED | Router line 461; service function confirmed |
| `app/templates/fragments/coffee_list.html` | Responsive layout markers | `class="hidden md:block"` (table) + `class="md:hidden space-y-3"` (cards) | VERIFIED | Both markers present in the template |
| `app/main.py` | All 7 Phase 4 routers | `include_router(...)` for roasters, flavor_notes, coffees, equipment, recipes, bags, photos | VERIFIED | Lines 222–228 of main.py |
| `autocomplete.js` | HX-Trigger `{entity}-created` events | `document.body.addEventListener(eventName, ...)` in both `autocomplete` and `flavorNoteChips` factories | VERIFIED | D-16 pre-select wired |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `coffee_list.html` | `coffees` list | `coffees_service.list_coffees(db, filters)` → `select(Coffee).where(...)` | Yes — real SQLAlchemy query | FLOWING |
| `recipe_step_builder.html` | `steps` array | `this.$root.dataset.initialSteps` → JSON.parse from Jinja `recipe.steps\|tojson` | Yes — JSONB from DB | FLOWING |
| `pour_timeline.html` | `timelineSegments` | Alpine computed getter from `steps` array | Yes — derived from real steps data | FLOWING |
| `photo_upload_zone.html` | `bag.photo_filename` | `bags_service.attach_or_replace_photo` → `process_and_save` writes file, DB updated | Yes — UUID from photos pipeline | FLOWING |
| `autocomplete_list.html` | query results | `roasters_service.search_by_prefix` / `flavor_notes_service.search_by_prefix` → `select(Roaster)...where(Roaster.name.ilike(...))` | Yes — real DB prefix query | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `photos.py` import succeeds | `python -c "from app.services.photos import process_and_save, replace_photo, unlink_safe, sweep_orphans, PhotoRejected, PHOTOS_DIR, MAX_BYTES, _is_safe_photo_filename; print('ok')"` | `ok` | PASS |
| Schemas import (in container env) | Verified via SUMMARY `docker compose exec coffee-snobbery python -c "from app.services.photos import ..."` | Reported: `ok` | PASS (container) |
| 22 CATALOG_* constants in events.py | `grep -c 'CATALOG_' app/events.py` | 44 matches (22 unique constants, each referenced twice in the file) | PASS |
| Recipe step builder JS serves correct registrations | Alpine.data(`recipeStepBuilder`) and Alpine.data(`autocomplete`) and Alpine.data(`flavorNoteChips`) and Alpine.data(`miniModal`) in their respective files | Confirmed by source read | PASS |

### Probe Execution

No `probe-*.sh` scripts declared for this phase. Phase 4 is not a migration/tooling phase with probe contracts. SKIPPED.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| CAT-01 | 04-04, 04-11 | Roasters table + autocomplete-on-create-on-save | SATISFIED | `app/models/roaster.py` (CITEXT unique name); `app/services/roasters.py::search_by_prefix`; `/roasters/list` autocomplete endpoint; mini-modal via `autocomplete.js` + `mini-modal.js` |
| CAT-02 | 04-05, 04-11 | Flavor notes table (normalized) + 9-value category enum + autocomplete-on-create-on-save | SATISFIED | `app/models/flavor_note.py` (CITEXT unique + category CHECK); `app/services/flavor_notes.py::search_by_prefix`; `/flavor-notes/datalist` endpoint; chip widget in `autocomplete.js` |
| CAT-03 | 04-07 | Coffees table with advertised_flavor_note_ids array + archived + CRUD UI | SATISFIED | `app/models/coffee.py` (ARRAY(BigInteger) + GIN index); `app/services/coffees.py`; full CRUD router |
| CAT-05 | 04-06 | Equipment table with 6-value type enum + archived + usage count | SATISFIED | `app/models/equipment.py`; `app/services/equipment.py::archive_equipment`; usage_count column ships at 0 (Phase 5 increments) |
| CAT-06 | 04-08 | Recipes table with JSONB steps + step builder + duplicate + pour-timeline | SATISFIED | `app/models/recipe.py` (JSONB steps); `recipe-step-builder.js`; `pour_timeline.html`; `duplicate_recipe` service + router endpoint |
| CAT-07 | 04-07 | Coffees list table/card responsive + filters roaster/country/process/archived | SATISFIED | `coffee_list.html` has `hidden md:block` / `md:hidden` markers; router accepts four filter params |
| CAT-08 | 04-01, 04-09, 04-10 | Bag photo upload pipeline + EXIF strip + resize + thumbnail + auth-gated serving | SATISFIED (with WARNING) | Full pipeline in `app/services/photos.py`; serving route in `app/routers/photos.py`; `capture="environment"` HTML attribute absent from `photo_upload_zone.html` — see Anti-Patterns |
| SEC-06 | 04-02 | Pydantic v2 schemas with numeric ranges on all state-changing endpoints | SATISFIED | All 6 schemas confirmed with `ConfigDict(extra="forbid")` and `Field(ge=...,le=...)` |
| SEC-07 | 04-01, 04-09, 04-10 | Image upload: magic-byte + Pillow decode + EXIF strip + oversize rejection | SATISFIED | 12 passing tests in `test_services_photos.py` covering all four threat vectors (T-04-PHOTO, T-04-EXIF, T-04-POLY, T-04-DOS) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/templates/fragments/photo_upload_zone.html` | 34, 65 | `<input type="file" name="photo" ...>` missing `capture="environment"` attribute | Warning | CAT-08 (REQUIREMENTS.md) specifies `<input capture="environment">` to open the device camera directly on mobile. The attribute is absent. Upload still works via the file picker; users on mobile must manually navigate to the camera. This is NOT in the 5 roadmap success criteria, so it does not block the phase. |
| `app/services/sessions.py` | 185 | `# Phase 8 TODO: schedule a periodic DELETE FROM sessions...` | Info | Pre-existing Phase 1 code; not a Phase 4 modified file. The TODO references a formal follow-up phase (Phase 8 APScheduler). No action required for Phase 4. |

No `TBD`, `FIXME`, or `XXX` markers found in any Phase 4 modified files.

### Human Verification Required

#### 1. Recipe Step Builder Live Reactivity

**Test:** Open `/recipes/new` in a browser. Add a "Bloom" step (50g / 45s). Add a second step (150g / 120s). Observe the delta readout below step 2 and the pour-timeline preview.

**Expected:** Step 2's delta row shows "+100g · +1:15". The pour-timeline preview shows two segments proportional to 45s and 120s. Remove step 1 — the preview should collapse to a single segment for step 2.

**Why human:** Alpine CSP-build reactivity (`x-for` + computed getters) cannot be driven by pytest; requires a live browser.

#### 2. Autocomplete-on-Create-on-Save (Roaster)

**Test:** Open `/coffees/new`. Type "Onyx" in the roaster field (wait 350ms). Verify the dropdown appears with prefix-matching results. Click "+ Create new roaster". In the mini-modal, enter "Onyx Coffee Roasters" and save.

**Expected:** Dropdown appears after the debounce; the mini-modal opens; after successful POST the modal closes and "Onyx Coffee Roasters" is pre-selected in the roaster input (Alpine D-16 pre-select).

**Why human:** HX-Trigger → CustomEvent → Alpine listener chain requires a browser event loop.

#### 3. Flavor Note Chip Widget

**Test:** Open `/coffees/new`. Type "berr" in the flavor note field. Select "Berry" from the dropdown. Add "Citrus" via the same field. Submit the form with a valid name and roaster.

**Expected:** Two chips appear immediately on selection; after submit, the coffee record in the DB has `advertised_flavor_note_ids` containing both IDs.

**Why human:** Alpine `flavorNoteChips` `x-for` blocks + parallel hidden inputs not observable via HTTP.

#### 4. Mini-Modal Dirty Check

**Test:** Open the roaster mini-modal (click "+ Create new roaster" from coffee form). Type something in the Name field. Press ESC (or click the backdrop).

**Expected:** A browser confirm dialog appears ("Are you sure...?") before the modal closes when the form is dirty. If the user cancels, the modal stays open.

**Why human:** Alpine dirty flag + browser `confirm()` behavior requires a real browser or Playwright.

#### 5. Coffee List Responsive Layout at 375px

**Test:** Open `/coffees` with at least one coffee in the catalog. Resize browser to 375px width (or use DevTools device simulation).

**Expected:** The table is hidden (`hidden md:block` not rendered); the card list is visible (`md:hidden` becomes visible); no horizontal scrollbar anywhere on the page.

**Why human:** CSS breakpoint behavior requires Playwright or manual browser check.

#### 6. Photo Upload camera capture on Mobile

**Test:** Open a bag row on iOS or Android. Tap "Upload photo".

**Expected:** Either the camera opens directly (if `capture="environment"` were present), or the file picker opens. The upload should work via either path. The gap is that the camera shortcut is missing.

**Why human:** `capture="environment"` is absent from the file input (Anti-Patterns above). This verifies whether the missing attribute is acceptable for the household use case.

### Gaps Summary

No BLOCKER gaps. The phase goal is achieved across all 5 success criteria. One WARNING:

**`capture="environment"` missing from bag photo upload input.** The HTML attribute `capture="environment"` (which opens the device camera directly on mobile) is specified in REQUIREMENTS.md CAT-08 but is absent from `app/templates/fragments/photo_upload_zone.html`. The upload pipeline itself (magic-byte, Pillow re-encode, EXIF strip, resize, thumbnail) is fully implemented and passes tests. This is a UX gap on mobile (requires navigating to camera via the file picker) not a security or functional gap. It is NOT in the 5 roadmap success criteria, so it does not block the phase. A one-line template fix would resolve it.

---

_Verified: 2026-05-19T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
