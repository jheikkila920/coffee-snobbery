---
phase: 04-shared-catalog
plan: 09
subsystem: bags-photo-upload
tags: [bags, photos, upload, canvas-downscale, multipart, htmx, sec-07, t-04-photo, t-04-exif, t-04-poly, t-04-dos, t-04-csrf, t-04-mass, d-07, mx-1, wave-9]

# Dependency graph
requires:
  - plan: 04-01
    provides: app/services/photos.py — process_and_save / replace_photo / unlink_safe / PhotoRejected / MAX_BYTES / _is_safe_photo_filename; tests/phase_04/conftest.py fixtures (photo_volume, synthetic_jpeg, polyglot_jpeg, exif_jpeg, bad_magic_jpeg); 5 catalog.bag.* + catalog.photo.orphan_swept event constants
  - plan: 04-02
    provides: app/schemas/bag.py::BagCreate (ge=1 / le=10000 weight_grams, extra='forbid', notes max 4000)
  - plan: 04-03
    provides: app/models/bag.py — coffee_id FK (RESTRICT), photo_filename column, finished_at column (archive surrogate)
  - plan: 04-07
    provides: app/templates/pages/coffee_detail.html — #bag-form-mount + #bag-list mount divs + "Open new bag" CTA wired to GET /coffees/{id}/bags/new (contract locked in 04-07); app/services/coffees.py::get_coffee for the FK pre-check
  - plan: 04-10
    provides: GET /photos/{filename} auth-gated FileResponse — bag_row's <img src="/photos/{filename}-thumb.jpg"> resolves through this route
provides:
  - app/services/bags.py — CRUD (create/get/list_for_coffee/update/archive) + photo lifecycle (attach_or_replace_photo + delete_photo) composing app.services.photos; 5 catalog.bag.* audit events
  - app/routers/bags.py — 7 endpoints (mixed coffee-nested + standalone /bags surface): GET /coffees/{coffee_id}/bags/new, POST /coffees/{coffee_id}/bags, GET /bags/{id}/edit, POST /bags/{id}, POST /bags/{id}/archive, POST /bags/{id}/photo, POST /bags/{id}/photo/delete
  - app/templates/fragments/bag_form.html, bag_row.html, photo_upload_zone.html — bag CRUD form + row + per-bag upload zone
  - app/static/js/photo-upload.js — D-05 Canvas downscale (capture-phase submit listener + DataTransfer file swap + htmx.trigger retrigger)
  - app/templates/pages/coffee_detail.html MODIFIED — bag list now iterates fragments/bag_row.html
  - app/templates/base.html MODIFIED — defer-loads /static/js/photo-upload.js with CSP nonce
affects:
  - phase-05 (brew_sessions.bag_id FK has a real bag-creation surface to consume; archive surrogate = finished_at IS NOT NULL drives the active-bag filter for the session form)
  - phase-06 (home page surfaces latest bag thumbnail via the upload zone fragment shape — same /photos/{stem}-thumb.jpg URL convention)
  - phase-08 (orphan sweep — the photo lifecycle here is the write side; sweep is the cleanup side; both go through _is_safe_photo_filename)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mixed-prefix router (no prefix='/...'; routes mix /coffees/{coffee_id}/bags/... nested + /bags/{id}/... standalone). Mirrors the coffee-nested CONTEXT canonical_refs decision while keeping the standalone surface compact — the user reaches edit/archive/photo via the row's buttons; carrying coffee_id in those URLs would be redundant."
    - "URL path coffee_id is authoritative — POST /coffees/{coffee_id}/bags strips any user-submitted coffee_id form field via skip-set + re-injects the path value. Prevents the mismatch-attack shape where the schema would otherwise see a forgeable coffee_id."
    - "D-07 write-new-then-delete-old enforced in service layer (NOT router): attach_or_replace_photo calls process_and_save first → captures old filename → commits new filename to DB → THEN replace_photo unlinks the old pair. The old file outlives the DB write so a unlink-failure leaves an orphan (logged-tolerated; the sweep collects it) but never points the DB at a missing file."
    - "Photo upload defense-in-depth chain: Content-Length pre-check (cheap) → await photo.read() → post-read len check (clients omit CL) → service-layer PhotoRejected catch → 200 + zone re-render with friendly message. All four rejection branches (oversize / bad magic / decode failure / decompression bomb) collapse to the same response shape."
    - "Per-bag upload zone re-render target: hx-target=#bag-photo-zone-{bag.id} hx-swap=outerHTML. Photo upload re-renders ONLY the zone (not the full row) so the rest of the bag row's content (notes / metadata / Edit / Mark finished) isn't disturbed by a photo POST."
    - "Capture-phase form submit listener for client-side downscale (NOT htmx:configRequest). HTMX 2.x serializes the form BEFORE configRequest fires AND configRequest is synchronous — await inside it is not supported. The correct shape: capture-phase 'submit' listener → evt.preventDefault() → async downscale → DataTransfer file swap → htmx.trigger(form, 'submit') retrigger with a processed flag to break the loop. Locked here for future client-side file-mutation patterns."
    - "iOS focus-zoom prevention (MX-1 forward): every form input in the bag form uses Tailwind text-base (16px). The rule is uniform across this plan; Phase 5 globalizes the rule via a base input style."
    - "Multi-file fragment include: bag_row.html includes fragments/photo_upload_zone.html with context — the zone is logically per-bag and is the only piece of the row that changes on photo upload. The include keeps the row template short and the zone re-usable on the standalone /bags/{id}/photo POST response."

key-files:
  created:
    - app/services/bags.py
    - app/routers/bags.py
    - app/templates/fragments/bag_form.html
    - app/templates/fragments/bag_row.html
    - app/templates/fragments/photo_upload_zone.html
    - app/static/js/photo-upload.js
  modified:
    - app/main.py — adds bags_router import + include_router(bags_router.router) between recipes_router and photos_router
    - app/templates/pages/coffee_detail.html — bag list now iterates fragments/bag_row.html
    - app/templates/base.html — adds <script defer src="/static/js/photo-upload.js" nonce="..."> after htmx-listeners.js
    - tests/phase_04/test_routers_bags.py — replaces 1-line Wave-0 skip stub with 16 real router tests

key-decisions:
  - "Bag archive == finished_at IS NOT NULL (no archived column). Locked in the plan; the service stamps finished_at = func.now() in archive_bag, and the bag_row template branches on `bag.finished_at is not none` to render the 'Finished' pill + hide the 'Mark finished' button. Downstream Phase 5 active-bag filters can read `WHERE finished_at IS NULL`."
  - "URL coffee_id is authoritative on POST /coffees/{coffee_id}/bags — the form's user-submitted coffee_id is stripped via the skip set, then re-injected from the path. Prevents the mismatch-attack shape; mirrors the BagCreate schema's required coffee_id field."
  - "Per-bag upload zone re-render target — POST /bags/{id}/photo returns ONLY the zone (id=bag-photo-zone-{bag.id}), not the whole bag row. The bag row's content outside the zone is stable across a photo upload (metadata, notes, Edit, Mark finished); re-rendering the whole row would needlessly redraw."
  - "Capture-phase submit listener for client-side Canvas downscale instead of htmx:configRequest. HTMX 2.x serializes form bodies BEFORE configRequest fires AND configRequest is synchronous (no await). The capture-phase listener intercepts the user-initiated submit, runs the async downscale, swaps the File via DataTransfer, then `htmx.trigger(form, 'submit')` re-fires the submit with a `__photoUploadProcessed` flag breaking the loop."
  - "Client-side downscale is bandwidth optimization ONLY. The server STILL re-encodes via app.services.photos.process_and_save (SEC-4 polyglot defense). The test test_upload_photo_polyglot_strip_at_route asserts the server's re-encode strips the trailer end-to-end — proving the client downscale doesn't cancel the server defense."
  - "EXIF orientation skipped at v1 per 04-RESEARCH Pattern 7. Server-side Pillow re-encode strips EXIF entirely; preview may display sideways but the canonical stored copy is consistent. Future revisitable when orientation-correct previews become a usability ask."
  - "Cancel button on bag form rounds to /coffees/empty-form (the existing coffees-router empty-form endpoint) instead of adding a /bags/empty-form endpoint. The fragment served is fragments/empty.html (literal `<div></div>`); no need to duplicate the route."

patterns-established:
  - "Mixed-prefix router pattern (coffee-nested + standalone) — applicable when an entity belongs to a parent (bags-of-coffee) but operates standalone after creation (edit/archive/photo via row buttons that don't carry the parent id)."
  - "Photo lifecycle in service layer (NOT router) — attach_or_replace_photo composes process_and_save + DB update + replace_photo in the correct D-07 order. Routers stay thin: catch PhotoRejected → 200 + zone re-render."
  - "Per-fragment scoped re-render target — multipart POSTs that affect a sub-region of a row (photo zone) target a per-bag id (bag-photo-zone-{id}) instead of the whole row. Keeps the swap surface minimal and avoids redrawing stable content."
  - "Client-side file mutation via capture-phase submit listener + DataTransfer file swap. Reusable for any future file-input form that wants client-side processing before HTMX submits."

requirements-completed:
  - CAT-08

# Metrics
duration: 50min
completed: 2026-05-19
---

# Phase 4 Plan 09: Bags CRUD + Photo Upload Pipeline Summary

**Ships CAT-08 — bags CRUD nested under coffee detail + the full photo upload pipeline (client Canvas downscale → multipart POST → server magic-byte + Pillow re-encode + EXIF strip + atomic main+thumb save + write-new-then-delete-old replace → thumbnail render via /photos/{stem}-thumb.jpg from plan 04-10). The first user-uploaded file surface in the app; converges the 5MB cap, magic-byte gate, polyglot defense, EXIF strip, decompression-bomb cap, and atomic file replace into one end-to-end test surface.**

## Performance

- **Duration:** ~50 minutes
- **Tasks:** 3
- **Files created:** 6 (1 service + 1 router + 3 templates + 1 JS)
- **Files modified:** 4 (app/main.py, app/templates/pages/coffee_detail.html, app/templates/base.html, tests/phase_04/test_routers_bags.py)

## Accomplishments

### Task 1 — service + router + main.py wire-up (commit `ecdc078`)

- **`app/services/bags.py`** (289 LOC): full CAT-08 CRUD mirroring the coffees/roasters template — sync `Session`, kwargs-only API after a leading `*`, single commit per write, audit-event emission at end of write. Functions: `create_bag`, `get_bag`, `list_bags_for_coffee` (opened_at DESC NULLS LAST, created_at DESC), `update_bag` (Core `update()` with explicit `updated_at = func.now()`), `archive_bag` (stamps `finished_at = now()` — the archive surrogate), `attach_or_replace_photo` (D-07 write-new-then-delete-old: `process_and_save → DB update → replace_photo unlink old`), `delete_photo` (clears `photo_filename` + `unlink_safe(old)`). 5 audit events emitted: `CATALOG_BAG_CREATED`, `CATALOG_BAG_UPDATED`, `CATALOG_BAG_ARCHIVED`, `CATALOG_BAG_PHOTO_UPLOADED` (with `replaced=True|False`), `CATALOG_BAG_PHOTO_DELETED`.
- **`app/routers/bags.py`** (449 LOC): 7 endpoints with the universal Phase 4 catalog router shape adapted for the coffee-nested surface:
  - `GET /coffees/{coffee_id}/bags/new` — empty form fragment (404 if coffee missing).
  - `POST /coffees/{coffee_id}/bags` — async + raw-form-read pattern for T-04-MASS; URL coffee_id is authoritative (form value discarded via skip set + re-injected). Validation errors → 200 + form re-render. Success → bag_row fragment + OOB form-clear.
  - `GET /bags/{bag_id}/edit` — pre-populated form fragment (datetime-local formatted for the input type).
  - `POST /bags/{bag_id}` — update.
  - `POST /bags/{bag_id}/archive` — `finished_at = now()` archive surrogate.
  - `POST /bags/{bag_id}/photo` — async multipart upload. Defense-in-depth: Content-Length pre-check → `await photo.read()` → post-read len check → service layer (which raises `PhotoRejected` on bad magic / decode failure / decompression bomb). All rejection branches → 200 + `fragments/photo_upload_zone.html` with `error=...` message.
  - `POST /bags/{bag_id}/photo/delete` — clears photo + re-renders zone.
- **`app/main.py`** modified to import + include `bags_router` between `recipes_router` and `photos_router`. Order matters only for declarative-path conflicts; bags has its own paths so the position is cosmetic.

### Task 2 — three fragments + coffee_detail integration + photo-upload.js + base.html (commit `969e786`)

- **`app/templates/fragments/bag_form.html`** (98 LOC): inline-expand form with two modes (`create` / `edit`). Fields: `roast_date` (date), `weight_grams` (number, min=1, max=10000, inputmode=decimal), `opened_at` / `finished_at` (datetime-local), `notes` (textarea). Hidden `coffee_id` input. Every input carries Tailwind `text-base` per MX-1 (iOS focus-zoom prevention). CSRF hidden input verbatim from `setup.html:10`. Cancel rounds to `/coffees/empty-form` (existing endpoint).
- **`app/templates/fragments/bag_row.html`** (72 LOC): root `<div data-row id="bag-{bag.id}">`. Header line: roast_date + weight_grams. Metadata line: opened_at + finished_at. Notes preview (truncated). Edit + "Mark finished" affordances; the latter hidden when `bag.finished_at is not None`. Includes `fragments/photo_upload_zone.html` with context. OOB form-clear when `include_oob_form_clear` is set.
- **`app/templates/fragments/photo_upload_zone.html`** (77 LOC): root `<div id="bag-photo-zone-{bag.id}">`. Two branches:
  - When `bag.photo_filename` is set: thumbnail `<img src="/photos/{stem}-thumb.jpg">` + Replace form + Delete button.
  - When unset: friendly file-input upload form with `data-photo-form` + `data-photo-input` hooks for `photo-upload.js`.
  - When `error` in context: renders `<p class="text-sm text-red-700">` above the form.
  - CSRF hidden input on every form/branch.
- **`app/templates/pages/coffee_detail.html`** (modified): bag list section now iterates `bags` through `fragments/bag_row.html` instead of an ad-hoc `<ul>`. Empty state unchanged.
- **`app/static/js/photo-upload.js`** (135 LOC): vanilla JS Canvas downscale (D-05). LOCKED HOOK STRATEGY documented in the file header: capture-phase form `submit` listener (NOT `htmx:configRequest`). On user submit → `evt.preventDefault()` → downscale to ~2000px max edge JPEG q=0.85 via Canvas + `toBlob` → wrap in `File` → swap `fileInput.files` via `DataTransfer` → `htmx.trigger(form, 'submit')` retrigger with `__photoUploadProcessed` flag to break the loop. Idempotent re-wire on `htmx:afterSettle` for fragment swaps. Skips files <500KB (already small). CSP-compliant: no inline handlers, no eval, no innerHTML.
- **`app/templates/base.html`** (modified): defer-loads `/static/js/photo-upload.js` with CSP nonce after `htmx-listeners.js`.

### Task 3 — 16 real router tests (commit `3e7a067`)

`tests/phase_04/test_routers_bags.py` (557 LOC) replaces the 1-line Wave-0 stub. Coverage by section:

**Bag CRUD (5 tests):**
- `test_open_new_bag_returns_form_fragment` — 200 + form with hidden coffee_id.
- `test_create_bag_valid` — 200 + bag row fragment + OOB form-clear + DB row asserted with `weight_grams == 250`.
- `test_create_bag_unknown_coffee_id_returns_404` — pre-check at router.
- `test_create_bag_zero_weight_rejected` — 200 + form re-render with `text-red-700` styling (field-level validation).
- `test_create_bag_extra_field_rejected` — T-04-MASS via `extra='forbid'`.

**Edit / Update / Archive (3 tests):**
- `test_edit_bag_pre_populates_fields` — form fragment carries existing weight + notes.
- `test_update_bag_persists` — DB reflects.
- `test_archive_bag` — `bag.finished_at is not None` after archive (locked archive surrogate).

**Photo upload pipeline (6 tests):**
- `test_upload_photo_valid_jpeg_round_trip` — main + thumb on disk inside `photo_volume`; `bag.photo_filename` set; zone fragment carries `/photos/{stem}-thumb.jpg`.
- `test_upload_photo_oversize_rejected` — 5MB+ payload → 200 + "too large" message in zone (T-04-DOS).
- `test_upload_photo_bad_magic_rejected` — HTML/PHP bytes → 200 + "unsupported" or "couldn't read" in zone (T-04-POLY magic-byte gate).
- `test_upload_photo_polyglot_strip_at_route` — JPEG + PHP trailer → server re-encode strips the trailer; saved file ends at `\xff\xd9` (T-04-POLY second line).
- `test_upload_photo_exif_stripped_at_route` — EXIF-laden JPEG → saved file's `getexif()` is empty (T-04-EXIF end-to-end).
- `test_upload_photo_replace_unlinks_old` — second upload unlinks the first pair (main + thumb); bag points at the new pair (D-07 verified).

**Delete + CSRF (2 tests):**
- `test_delete_photo` — clears `photo_filename` + unlinks main + thumb.
- `test_csrf_missing_returns_403_on_photo_upload` — multipart CSRF gate (T-04-CSRF).

## Task Commits

Each task committed atomically:

1. **Task 1: service + router + main.py wire-up** — `ecdc078` (feat)
2. **Task 2: 3 fragments + photo-upload.js + coffee_detail + base.html** — `969e786` (feat)
3. **Task 3: 16 real router tests** — `3e7a067` (test)

## Decisions Made

- **Bag archive surrogate `finished_at IS NOT NULL`** (no `archived` column on bags). Locked in the plan; the service stamps `finished_at = func.now()` and the bag_row template branches on it. Downstream Phase 5 active-bag filters can read `WHERE finished_at IS NULL`. The 16th test (`test_archive_bag`) asserts the contract.
- **URL `coffee_id` is authoritative on POST `/coffees/{coffee_id}/bags`** — the form's user-submitted `coffee_id` is stripped via the skip set, then re-injected from the path. Prevents the mismatch-attack shape; mirrors the `BagCreate` schema's required `coffee_id` field. Documented in the router docstring.
- **Per-bag photo upload zone re-render target** — POST `/bags/{id}/photo` returns ONLY the zone (id=`bag-photo-zone-{bag.id}`), not the whole bag row. The bag row's content outside the zone (metadata, notes, Edit, Mark finished) is stable across a photo upload; re-rendering the whole row would needlessly redraw and risk losing user-affected DOM state (e.g., an open hx-confirm dialog on a sibling button).
- **Capture-phase form `submit` listener for client-side Canvas downscale** instead of `htmx:configRequest`. HTMX 2.x serializes form bodies BEFORE `configRequest` fires AND `configRequest` is synchronous (no `await`). The capture-phase listener intercepts the user-initiated submit, runs the async downscale, swaps the File via `DataTransfer`, then `htmx.trigger(form, 'submit')` re-fires the submit with a `__photoUploadProcessed` flag breaking the loop. This is the canonical pattern for any future client-side file-mutation case.
- **Client-side downscale is bandwidth optimization ONLY.** The server STILL re-encodes via `app.services.photos.process_and_save` (SEC-4 polyglot defense). The test `test_upload_photo_polyglot_strip_at_route` asserts the server's re-encode strips the trailer end-to-end — proving the client downscale doesn't cancel the server defense.
- **EXIF orientation skipped at v1** per 04-RESEARCH Pattern 7. Server-side Pillow re-encode strips EXIF entirely; preview may display sideways but the canonical stored copy is consistent. Revisitable in a future plan when orientation-correct previews become a usability ask.
- **Cancel button on bag form rounds to `/coffees/empty-form`** (the existing coffees-router empty-form endpoint) instead of adding a `/bags/empty-form` endpoint. The fragment served is `fragments/empty.html` (literal `<div></div>`); no need to duplicate the route. The `/coffees/empty-form` route was declared before `/coffees/{coffee_id}` in the coffees router so the literal path wins over the parameterized matcher.

## Deviations from Plan

### Auto-fixed Issues

None. All three tasks landed on the first run after a single ruff format pass. The plan's prescriptions matched the actual surface 1:1 — bag archive surrogate, photo-upload hook strategy, oversize-rejection threshold flow, and the per-bag re-render target all worked as written.

### Plan-acknowledged ship choices

- **Cancel button rounds to `/coffees/empty-form`** instead of a new `/bags/empty-form`. The plan didn't specify; reusing the existing endpoint saves a route.
- **`hx-encoding="multipart/form-data"` set explicitly on photo upload forms** in addition to the standard `enctype` attribute. HTMX 2.x respects both, but `hx-encoding` is the documented HTMX path for multipart; setting both is defense in depth at zero cost.

## Issues Encountered

- **Docker container is image-baked, not bind-mounted.** Every verification step required `docker cp <file> coffee-snobbery:/app/<path>` before running tests inside the container. Same friction documented in plans 04-01..04-07; the structural fix (split runtime/test stages or add a bind-mount dev compose profile) is logged as ops work.
- **`docker compose exec` resolves `.env` from cwd; the worktree has no `.env`.** Used `docker exec coffee-snobbery ...` directly throughout, which bypasses the env-file resolution. Same workaround documented in earlier plans.

## User Setup Required

None — this plan ships routes + templates + tests + JS only. No new env vars, no external service configuration, no DB migration (the `photo_filename` column landed in plan 04-03).

## Verification

Plan-stated verify commands + `<done>` criteria:

- **Task 1 verify:** `docker exec coffee-snobbery python -c "from app.routers.bags import router; from app.services.bags import create_bag, attach_or_replace_photo, delete_photo; print('ok')"` → `ok` ✓
- **Task 1 done criteria:**
  - `grep -c 'CATALOG_BAG' app/services/bags.py` → `10` ✓ (≥5 required)
  - `grep -c 'UploadFile' app/routers/bags.py` → `3` ✓ (≥1 required)
  - `grep -c 'PhotoRejected' app/routers/bags.py` → `4` ✓ (≥1 required)
  - `grep -c 'bags_router' app/main.py` → `2` ✓ (1 import + 1 include)
- **Task 2 verify:** `test -f app/static/js/photo-upload.js && grep -c 'data-photo-form' app/templates/fragments/photo_upload_zone.html` → file exists; `3` ✓ (≥1 required — 2 real `<form data-photo-form>` attrs + 1 comment mention).
- **Task 2 done criteria:**
  - `photo-upload.js` file exists ✓
  - `data-photo-form` attribute present in upload-zone fragment ✓
  - `grep -c 'photo-upload.js' app/templates/base.html` → `1` ✓
  - No `|safe` or `hx-on:` in any bag template (grep clean) ✓
  - CSRF hidden input in bag_form (2 occurrences) + photo_upload_zone (4 occurrences across both branches and comment) ✓
- **Task 3 verify:** `docker exec coffee-snobbery python -m pytest -q tests/phase_04/test_routers_bags.py -x` → `16 passed, 1 warning in 5.45s` ✓ (≥16 required)

**Wave-wide regression check:** `docker exec coffee-snobbery python -m pytest -q tests/phase_04/` → `179 passed, 1 skipped, 7 warnings in 25.69s`. The +16 net is the new bag router tests.

**Full repo suite:** `docker exec coffee-snobbery python -m pytest -q` → `297 passed, 3 skipped, 10 xfailed, 34 warnings in 34.37s`. No regressions traced to this plan.

## Threat Coverage

| Threat ID | Component | Mitigation | Test |
|-----------|-----------|------------|------|
| T-04-PHOTO | POST /bags/{id}/photo filename gen | Server-side UUID4 hex via process_and_save; user never controls the path; bag.photo_filename is regex-validated by the serving route (plan 04-10). | `test_upload_photo_valid_jpeg_round_trip` (asserts the on-disk path matches the bag's filename) |
| T-04-EXIF | Photo upload pipeline | Pillow re-encode strips EXIF (no `exif=` kwarg); `getexif().clear()` belt-and-braces. | `test_upload_photo_exif_stripped_at_route` (asserts saved file's EXIF is empty end-to-end) |
| T-04-POLY | Photo upload pipeline | Magic-byte gate rejects bad magic before Pillow; Pillow re-encode strips trailing data past `\xff\xd9`. | `test_upload_photo_bad_magic_rejected` + `test_upload_photo_polyglot_strip_at_route` |
| T-04-DOS | POST /bags/{id}/photo | Content-Length pre-check + post-read len check before Pillow; `Image.MAX_IMAGE_PIXELS = 16M` cap (plan 04-01). | `test_upload_photo_oversize_rejected` (decompression-bomb pixel-cap covered by plan-04-01 unit test) |
| T-04-CSRF | All state-changing bag routes incl. multipart photo upload | CSRF hidden input verbatim in every form template; CSRFFormFieldShim hoists; CSRFMiddleware enforces. | `test_csrf_missing_returns_403_on_photo_upload` (multipart CSRF gate) |
| T-04-MASS | POST /coffees/{id}/bags | `BagCreate.model_config = ConfigDict(extra='forbid')` rejects unknown fields; router uses raw-form-read pattern (await request.form()) so the schema sees the unknown field. | `test_create_bag_extra_field_rejected` |
| T-04-XSS | bag_row + photo_upload_zone templates | Jinja autoescape ON globally; bag.notes auto-escaped; photo filename embedded in img src is regex-shaped (UUID hex, no separators) so safe even before the serving route's regex re-check. | Grep check: `grep -E '\|safe'` on new templates → no matches ✓ |
| (path traversal via filename) | bag_row template img src | photo_filename is only ever set by photos_service.process_and_save (UUID4 hex); never user input. Serving route (plan 04-10) re-validates via _is_safe_photo_filename + Path.resolve().relative_to(PHOTOS_DIR.resolve()). | Plan 04-10 covers this surface; this plan asserts the filename round-trips correctly via `test_upload_photo_valid_jpeg_round_trip` |

## Contracts Locked for Downstream Plans

### For Phase 5 (brew sessions)

- **Active-bag filter pattern**: `WHERE finished_at IS NULL` returns "open" bags; `WHERE finished_at IS NOT NULL` returns "finished" bags. The session form's bag selector should filter to `finished_at IS NULL` so finished bags don't pollute the brewing flow.
- **`bags_service.list_bags_for_coffee(db, coffee_id=...)`** returns bags ordered `opened_at DESC NULLS LAST, created_at DESC` — same ordering as the coffee detail page so session and detail surfaces stay consistent.
- **Bag photo URL convention** — `<img src="/photos/{bag.photo_filename|replace('.jpg', '-thumb.jpg')}">` resolves to the 400px thumb. Phase 5's session detail can re-use this expression directly.

### For Phase 8 (orphan sweep)

- **`bags.photo_filename`** is the column the sweep queries. This plan ensures every value in that column points at a real file on disk at commit time (`attach_or_replace_photo` writes the file before updating the column). The sweep collects files NOT in the column.

### For future client-side file-mutation features (not in this plan)

- **Capture-phase form `submit` listener + DataTransfer file swap + htmx.trigger retrigger** is the canonical pattern. Code template lives in `app/static/js/photo-upload.js`; future similar features (e.g., audio recordings, document uploads) can copy the shape.

## Self-Check: PASSED

- `app/services/bags.py` exists (289 LOC): FOUND
- `app/routers/bags.py` exists (449 LOC): FOUND
- `app/templates/fragments/bag_form.html` exists (98 LOC): FOUND
- `app/templates/fragments/bag_row.html` exists (72 LOC): FOUND
- `app/templates/fragments/photo_upload_zone.html` exists (77 LOC): FOUND
- `app/static/js/photo-upload.js` exists (135 LOC): FOUND
- `app/templates/pages/coffee_detail.html` modified (bag-list uses fragments/bag_row.html): FOUND
- `app/templates/base.html` modified (photo-upload.js script tag): FOUND
- `app/main.py` modified (bags_router import + include): FOUND
- `tests/phase_04/test_routers_bags.py` has 16 real tests (no Wave-0 skip stub): FOUND
- Commit `ecdc078` (Task 1) in `git log`: FOUND
- Commit `969e786` (Task 2) in `git log`: FOUND
- Commit `3e7a067` (Task 3) in `git log`: FOUND
- Container verify `pytest -q tests/phase_04/test_routers_bags.py` returns `16 passed`: FOUND
- Container verify `pytest -q tests/phase_04/` returns `179 passed, 1 skipped`: FOUND
- Container verify `pytest -q` (full repo) returns `297 passed, 3 skipped, 10 xfailed`: FOUND
- No file deletions across the three commits: VERIFIED

---
*Phase: 04-shared-catalog*
*Plan: 09*
*Completed: 2026-05-19*
