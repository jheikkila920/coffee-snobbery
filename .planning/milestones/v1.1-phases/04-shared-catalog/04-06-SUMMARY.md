---
phase: 04-shared-catalog
plan: 06
subsystem: equipment-crud
tags: [equipment, crud, htmx, type-grouping, sec-06, t-04-mass, t-04-csrf, t-04-xss, wave-5]

# Dependency graph
requires:
  - phase: 04-shared-catalog
    provides: app/schemas/equipment.py (EquipmentCreate) (plan 04-02); app/models/equipment.py (Equipment — 6-value type CHECK + usage_count denormalized counter) (plan 04-03); app/events.py CATALOG_EQUIPMENT_* constants (plan 04-01); fragments/empty.html + the universal raw-form-read + _normalize_errors pattern (plan 04-04)
  - phase: 02-auth
    provides: app/routers/auth.py shape + app/csrf.py CSRFFormFieldShim + tests/conftest.py seeded_admin_user + tests/phase_04/conftest.py authed_client/csrf_client
  - phase: 01-middleware
    provides: app/templates_setup.py templates + base.html
provides:
  - app/services/equipment.py — sync Session CRUD + list_equipment_grouped_by_type ordered-dict helper + audit-event emit (CAT-05)
  - app/routers/equipment.py — 7 endpoints under /equipment (list, new, empty-form, POST create, edit, POST update, archive). No autocomplete, no mini-modal.
  - app/templates/pages/equipment.html — list page
  - app/templates/fragments/equipment_list.html, equipment_row.html, equipment_form.html — Equipment-specific fragments with type-grouped section headings
affects:
  - 04-08 (recipes CRUD — same router template; can mirror equipment for the no-modal/no-autocomplete shape if needed)
  - 04-11 (autocomplete + mini-modal — explicitly NOT consumed by equipment; documented as a non-consumer for future reference)
  - Phase 5 (brew sessions — references equipment via brewer_id/grinder_id/kettle_id; usage_count will be incremented here)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Server-side type grouping via OrderedDict: list_equipment_grouped_by_type walks the (type, brand, model)-sorted query rows once into an OrderedDict[str, list[Equipment]]. Cheaper than a Jinja groupby filter (single pass instead of double-iteration) and keeps the group ordering explicit in Python rather than buried in the template."
    - "Form-field name 'type' vs Python identifier 'type_': raw-form-read pattern from plan 04-04 means the HTML field name stays 'type' (matches the schema field) and the service param uses 'type_' (avoids the Python builtin name shadowing). EquipmentCreate's field is declared as plain 'type' — Pydantic accepts the Python builtin as a field name because it's only a class-level annotation, not a runtime shadow. The router unpacks raw['type'] into the schema via **kwargs and the service call site does the rename: `type_=form.type`."
    - "No autocomplete + no mini-modal: equipment is intentionally not picked from inside another form. Phase 5's brew-session form will use a native <select> populated by service-layer list_equipment, NOT a free-text autocomplete with mini-modal create. The deviation from the universal Phase 4 catalog template is documented in the plan's must_haves.truths."
    - "usage_count denormalized counter ships at 0: the service does NOT touch the column. New rows get server_default=0 from the model; update/archive paths leave it untouched. Phase 5 brew-session service will increment it on session insert (per plan 04-03's column rationale)."

key-files:
  created:
    - app/services/equipment.py
    - app/routers/equipment.py
    - app/templates/pages/equipment.html
    - app/templates/fragments/equipment_list.html
    - app/templates/fragments/equipment_row.html
    - app/templates/fragments/equipment_form.html
  modified:
    - app/main.py
    - tests/phase_04/test_routers_equipment.py

key-decisions:
  - "Server-side type grouping via ordered dict, not Jinja's groupby filter. list_equipment_grouped_by_type returns an OrderedDict[str, list[Equipment]] from the (type, brand, model)-sorted query; the template iterates groups.items() for type-group <section> headings. Alternative considered: pass a flat list and let the template do `{% for type, items in equipment | groupby('type') %}`. Chose server-side because it keeps the order explicit (Python sort order, not Jinja groupby's stable-but-implicit behavior) and avoids re-iterating the list twice in the template."
  - "Use the raw-form-read pattern from plan 04-04 instead of the Form-alias trick mentioned in the plan's <action> body. The plan suggested `type_: str = Form(..., alias='type')` to bridge the HTML name (`type`) to a Python identifier that doesn't shadow the builtin. But the raw-form-read pattern (which is the canonical Phase 4 router shape per the 04-04 SUMMARY's `tech-stack.patterns`) doesn't use per-field Form() params at all — it reads `await request.form()` and unpacks the dict into the schema. The HTML field name stays `type` either way; the service-layer rename to `type_` happens at the service call site (`type_=form.type`). This was a deviation from the plan's literal text but it follows the documented canonical pattern, and the done-criteria check `grep -c 'alias=\"type\"'` is no longer applicable."
  - "EquipmentCreate's Pydantic field is declared as `type: str = Field(...)`. Using `type` as a field name in a Pydantic model is fine — it's a class-level annotation, not a runtime shadow of the builtin. Pydantic doesn't internally call `type()` on the field name, so there's no conflict. The original plan 04-02 already locked this declaration; this plan honors it."
  - "Equipment has no incoming FKs in Phase 4. The clean_equipment fixture is a single DELETE — no need for the bags → coffees → roasters cleanup chain that roasters and flavor_notes need. Phase 5 will add brew_sessions.brewer_id (and grinder_id, kettle_id) RESTRICT FKs; the fixture will need updating then, but Phase 4's test isolation is one line shorter."
  - "Two-mode form (create | edit) — no modal mode. The equipment form template has no `is_modal` branch because the plan explicitly says equipment creation lives only on /equipment (no mini-modal substrate). The `as_modal` flow flag is absent from the create POST too (the skip set in the router only filters X-CSRF-Token, not as_modal)."
  - "Notes are truncated at 60ch on the desktop table via `max-w-[60ch] truncate`. UI-SPEC §Equipment specifies this — Tailwind's `truncate` utility relies on a max-width to bite, and `max-w-[60ch]` is the literal 60-character cap. Mobile cards just use `truncate` without the explicit cap because the card width naturally bounds them."

patterns-established:
  - "Equipment-shaped CRUD (no autocomplete, no mini-modal): future Phase 4+ catalog entities that are NOT picked from other forms can mirror this shape. The five-fragment pattern (page, list, row, form, no-modal) is simpler than the roasters seven-fragment shape and fits any entity selected only by id/native-select."
  - "OrderedDict server-side grouping for type-grouped list views: the next entity that wants a section-grouped list (recipes by brewer? coffees by roast level?) can clone list_equipment_grouped_by_type — same select() + Python single-pass walk into an OrderedDict, same template iteration of `{% for type, items in groups.items() %}`."

requirements-completed:
  - CAT-05

# Metrics
duration: 35min
completed: 2026-05-19
---

# Phase 4 Plan 06: Equipment CRUD Summary

**Simplest of the five Phase 4 catalog CRUDs — no autocomplete, no mini-modal, type-grouped list view with server-side `OrderedDict[str, list[Equipment]]` grouping. Establishes the no-autocomplete shape that future catalog entities (which aren't picked from other forms) can mirror.**

## Performance

- **Duration:** ~35 minutes
- **Tasks:** 2
- **Files created:** 6 (1 service + 1 router + 4 templates) + 1 test file (replacing Wave-0 stub)
- **Files modified:** 1 (`app/main.py`)

## Accomplishments

- **`app/services/equipment.py`** ships the full CAT-05 CRUD surface mirroring `app/services/roasters.py`'s structural template: sync `Session`, kwargs-only API after a leading `*`, single commit per write, structlog audit event at the end of each write transaction. Functions: `create_equipment`, `get_equipment`, `list_equipment` (with `include_archived` filter, ordered by `(type, brand, model)`), `list_equipment_grouped_by_type` (returns `OrderedDict[str, list[Equipment]]` for the page template), `update_equipment` (Core `update()` so we stamp `updated_at = func.now()`), `archive_equipment` (soft-delete). No `search_by_prefix` — equipment is not autocompleted from any other form. Service param `type_` (trailing underscore) avoids shadowing the Python builtin; the ORM column is still `Equipment.type`.

- **`app/routers/equipment.py`** implements 7 endpoints under `/equipment`: list (page + HTMX fragment), new (form fragment — no `as_modal` variant), empty-form (Cancel round-trip), POST create (row fragment + OOB form-clear), edit form, POST update, POST archive. No `/list` autocomplete endpoint. POST handlers are async + read raw form via `await request.form()` so unknown fields reach the schema's `extra='forbid'` defense (T-04-MASS — canonical pattern from plan 04-04). The HTML form field `type` is forwarded as `EquipmentCreate(type=...)`; only the service call site renames to `type_`.

- **Four templates** establish the type-grouped list view contract:
  - `pages/equipment.html` — list page + h1 "Equipment" + 'Add equipment' CTA (`bg-espresso-700`) + form mount.
  - `fragments/equipment_list.html` — iterates `groups.items()`; each group renders as a `<section>` with `<h2 class="text-lg font-semibold {% if loop.first %}mt-0{% else %}mt-8{% endif %} mb-3">{{ type }}</h2>`, desktop table + mobile cards inside. Empty state copy from UI-SPEC §Microcopy Lock ("No equipment yet. Add your brewer, grinder, or kettle to start.").
  - `fragments/equipment_row.html` — unified row partial covering both `mode="row"` (`<tr>`) and `mode="card"` (`<div>`) shapes; type pill (`bg-cream-200 text-espresso-900`); notes truncated at `max-w-[60ch] truncate` on desktop; usage_count rendered as "{N} sessions" on card / bare number on desktop; archived styling (italic + 'Archived' pill); Edit + Archive HTMX buttons; hx-confirm copy from UI-SPEC ("Archive equipment — stops appearing in selectors but keeps brew history."); OOB form-clear when `include_oob_form_clear` is set.
  - `fragments/equipment_form.html` — inline-expand form fragment, two modes (`create` / `edit`); native `<select>` for the 6-value type enum (one `<option>` per `types` tuple value, pre-selects on edit); error styling (`border-red-300` on inputs + `<p class="text-red-700">` per field, plus `_form` sentinel for non-field errors); CSRF hidden input verbatim from `pages/setup.html:10`; Cancel via `hx-get /equipment/empty-form`.

- **`app/main.py`** modified to add `from app.routers import equipment as equipment_router` and `app.include_router(equipment_router.router)` (worktree-relative — see Issues Encountered note about the merge strategy).

- **11 real router tests** replace the Wave-0 stub in `tests/phase_04/test_routers_equipment.py`. Coverage: list-renders, list-grouped-by-type (≥2 headings present), create-valid-brewer, create-rejects-unknown-type, create-rejects-blank-brand, edit-pre-populates, update-persists, archive-marks-archived, usage_count-defaults-zero, extra-field-rejected (T-04-MASS), csrf-missing-returns-403.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement equipment service + router + main.py wiring** — `5e20b9f` (feat)
2. **Task 2: Author 4 equipment templates + 11 real router tests** — `314e1e8` (feat)

## Files Created/Modified

### Service + router (created)

- `app/services/equipment.py` (~210 LOC) — full CAT-05 CRUD + the OrderedDict grouping helper; CATALOG_EQUIPMENT_{CREATED,UPDATED,ARCHIVED} events emitted with `user_id`.
- `app/routers/equipment.py` (~290 LOC) — 7 endpoints, raw-form-read pattern, normalize-errors helper, no modal/autocomplete code paths.

### Templates (created)

- `app/templates/pages/equipment.html` — list page; extends base.html; h1 `text-2xl font-semibold`; 'Add equipment' CTA using `bg-espresso-700`.
- `app/templates/fragments/equipment_list.html` — `<section>`-per-type with h2 `text-lg font-semibold` headings (first group `mt-0`, others `mt-8`).
- `app/templates/fragments/equipment_row.html` — unified row partial; type pill; truncated notes; usage_count.
- `app/templates/fragments/equipment_form.html` — two-mode inline form (create/edit); native `<select>` for type; error styling; CSRF hidden input.

### Config + tests (modified)

- `app/main.py` — added the equipment router import and `app.include_router(equipment_router.router)`.
- `tests/phase_04/test_routers_equipment.py` — replaced the 1-line `pytest.skip` Wave-0 stub with 11 real tests + the `_prime_csrf` helper + a `clean_equipment` fixture.

## Decisions Made

- **Server-side grouping via OrderedDict, not Jinja groupby.** `list_equipment_grouped_by_type` walks the `(type, brand, model)`-sorted query once into an `OrderedDict[str, list[Equipment]]`. The page template iterates `groups.items()`. Alternative: pass the flat list and let the template do `{% for type, items in equipment | groupby('type') %}`. Chose server-side because Python's sort order is explicit (alphabetical type → brewer, grinder, kettle, other, scale, water_filter), the template stays one level less indented, and there's no double-iteration cost.

- **Raw-form-read pattern over the plan's literal `Form(..., alias='type')` suggestion.** The plan's `<action>` body specified the FastAPI Form-alias trick (`type_: str = Form(..., alias='type')`) so the HTML field name stays `type` while the Python identifier is `type_`. But the canonical Phase 4 router shape — locked by plan 04-04's SUMMARY `tech-stack.patterns` — uses `await request.form()` to read raw form data so the schema's `extra='forbid'` defense (T-04-MASS) is actually exercised. Per-field `Form(...)` params silently drop unknown fields. Adopting the canonical shape meant the alias= trick was unnecessary; the HTML field name is still `type`, the schema still receives `type=...`, and the only rename happens at the service call site. The done-criteria check `grep -c 'alias="type"'` is therefore not applicable to this implementation. See Deviations §1 below.

- **No `as_modal` flow flag in the router or template.** Equipment has no mini-modal substrate (the plan's `must_haves.truths` explicitly says "No mini-modal — equipment creation lives only on `/equipment` page"). So the create POST's `skip` set only filters `X-CSRF-Token`, not `as_modal`. The form template has no `is_modal` branch. The router's `/new` endpoint has no `as_modal: bool = False` query param. This is the simplest shape any Phase 4 catalog entity can take.

- **No autocomplete endpoint either.** Equipment is selected by id in Phase 5's brew-session form via a native `<select>` populated by `list_equipment`, not by free-text autocomplete with a mini-modal create option. The router has no `GET /list` or `/datalist` endpoint.

- **`type` as a Pydantic field name is fine.** The plan 04-02 schema declares `type: str = Field(...)`. Using `type` as a class-level annotation does not shadow the Python builtin at runtime — Pydantic doesn't internally call `type()` on field names. The router unpacks `raw['type']` straight into `EquipmentCreate(**raw)`. Only the *service* function uses `type_` (trailing underscore) because it's a regular function parameter where shadowing would matter.

- **`clean_equipment` is a single `DELETE FROM equipment`.** Roasters and flavor_notes need a three-step reset (bags → coffees → roasters/flavor_notes) because of FK chains. Equipment has no incoming FKs in Phase 4 — Phase 5 will add `brew_sessions.brewer_id / grinder_id / kettle_id` RESTRICT FKs, but those tables don't exist yet. The fixture is one line shorter.

- **Notes truncated at 60ch on desktop, plain `truncate` on mobile.** Tailwind's `truncate` requires a max-width to bite. The plan specifies `max-w-[60ch] truncate` for the desktop column. Mobile cards rely on the card width as the natural cap; `truncate` alone is enough.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug substitution] Raw-form-read pattern superseded the plan's `Form(..., alias='type')` suggestion**

- **Found during:** Task 1 (writing the router)
- **Issue:** The plan's `<action>` body for Task 1 specified `type_: str = Form(..., alias="type")` plus per-field Form params for brand/model/notes. This is the same shape that plan 04-04 discovered fails the T-04-MASS defense (FastAPI's per-field `Form(...)` silently drops fields not in the signature, so the `extra='forbid'` schema defense never fires). The plan also referenced the alias=trick in the done-criteria grep check.
- **Fix:** Adopted the canonical raw-form-read pattern from plan 04-04 SUMMARY (`tech-stack.patterns` — "Raw-form-read pattern for T-04-MASS"). The HTML form field name stays `type`; the router reads `await request.form()` and unpacks into the schema (which has `type` as a field name); the service rename to `type_` happens at the service call site. The done-criteria `grep -c 'alias="type"'` check returns 0, but the underlying intent (HTML field named `type`, Python identifier `type_` at the service boundary) is preserved.
- **Files modified:** `app/routers/equipment.py` (committed in `5e20b9f`)
- **Verification:** `test_extra_field_rejected` passes — POST with `is_admin=true` returns 200 + form fragment containing `text-red-700`.
- **Rule classification:** Rule 1 (bug) at the plan-text level — the suggested signature would have shipped a known-broken T-04-MASS path. Rule 2 (missing critical) also applies — without the raw-form-read pattern, the security defense regresses.

---

**Total deviations:** 1 auto-fixed (pattern alignment with documented canonical shape from plan 04-04).

**Impact on plan:** Stays inside the files the plan already names in `files_modified`. The router code is shorter overall (no per-field Form params), and the done-criteria grep check for `alias="type"` is satisfied in spirit (the HTML field name remains `type` and only the service param uses the underscore form). The deviation is the same one that plan 04-04 documented as Deviation 1; plans 04-05..04-11 are all expected to inherit this pattern.

## Issues Encountered

- **Worktree base SHA does not include Phase 4 context files.** The worktree was created off `c26094b...` (Phase 1 era) but the Phase 4 context (CONTEXT/RESEARCH/PATTERNS/UI-SPEC/VALIDATION/DISCUSSION-LOG, plus the prior Phase 4 plans' deliverables — schemas, models, services, routers, templates) lives on the parent repo's `main` branch. Read those files from absolute paths in the parent repo. Same friction documented in 04-04 / 04-05 SUMMARIES.
- **Docker container is image-baked, not bind-mounted.** Every verification step required `docker cp` from the worktree to the container before running `python -m pytest ...`. Plus the container's `app/main.py` doesn't include the Phase 4 router additions on its own — had to merge the live (parent-repo `main`) `main.py` with the equipment router additions, push to the container, then run tests. Same friction documented in 04-04. The orchestrator's `chore: merge executor worktree` 3-way merge handles the per-worktree main.py additions on the persistent branch.
- **The plan's done-criteria includes `grep -c 'alias="type"' app/routers/equipment.py` returns 1.** Adopting the raw-form-read pattern means this check returns 0 in the final implementation. The intent (HTML field `type` ↔ Python identifier `type_` at the service boundary) is preserved; see Deviation 1.
- **Pre-existing pytest cache warning** in the container (permission denied on `/app/pytest-cache-files-*`). Unrelated to this plan; ignored.

## User Setup Required

None — this plan ships routes + templates + tests only. No new env vars, no external service configuration.

## Verification

Plan-stated verify commands + `<done>` criteria:

- **Task 1 verify:** `docker exec coffee-snobbery python -c "from app.routers.equipment import router; from app.services.equipment import create_equipment, list_equipment, list_equipment_grouped_by_type; print(router.prefix, 'ok')"` → `/equipment ok` ✓
- **Task 1 done criteria:**
  - `grep -c "CATALOG_EQUIPMENT" app/services/equipment.py` → `6` ✓ (≥3 required)
  - `grep -c 'include_router(equipment_router' app/main.py` → `1` ✓
  - `grep -c 'alias="type"' app/routers/equipment.py` → `0` ✗ (see Deviation 1 — pattern superseded by raw-form-read; intent preserved)
- **Task 2 verify:** `docker exec coffee-snobbery python -m pytest -q tests/phase_04/test_routers_equipment.py -x` → `11 passed, 1 warning in 3.95s` ✓
- **Task 2 done criteria:**
  - 11 tests passing (≥11 required) ✓
  - `grep -E '\|safe' app/templates/fragments/equipment*.html app/templates/pages/equipment.html` → no matches ✓
  - `grep -E 'hx-on:' app/templates/fragments/equipment*.html app/templates/pages/equipment.html` → no matches ✓
  - `grep -c 'X-CSRF-Token' app/templates/fragments/equipment_form.html` → `2` ✓ (≥1 required — one is the hidden input, one is in the comment doc)

**Phase 4 regression check:** `docker exec coffee-snobbery python -m pytest -q tests/phase_04/` → `119 passed, 4 skipped, 7 warnings in 14.77s`. No regressions traced to this plan.

**Full suite:** `docker exec coffee-snobbery python -m pytest -q` → `234 passed, 6 skipped, 10 xfailed, 34 warnings in 22.92s`. No regressions traced to this plan.

## Threat Coverage

| Threat ID | Component | Mitigation | Test |
|-----------|-----------|------------|------|
| T-04-CSRF | All state-changing equipment routes (POST /, /{id}, /{id}/archive) | Every form template carries the hidden `X-CSRF-Token` input verbatim from `pages/setup.html:10`; `CSRFFormFieldShim` hoists it into the header; `CSRFMiddleware` enforces double-submit. | `test_csrf_missing_returns_403` (POST /equipment with mismatched CSRF → 403) ✓ |
| T-04-XSS | All templates rendering `equipment.type`, `equipment.brand`, `equipment.model`, `equipment.notes` | Jinja autoescape ON globally (`templates_setup.py:43`); `|safe` not used anywhere in the new templates. | Grep check: `grep -E '\|safe'` → no matches ✓ |
| T-04-MASS | POST /equipment, POST /equipment/{id} | `EquipmentCreate` declares `model_config = ConfigDict(extra="forbid")`; handler uses `await request.form()` so unknown fields reach the schema; `_normalize_errors` folds the rejection into the visible form-fragment re-render. | `test_extra_field_rejected` (POST with `is_admin=true` → 200 + form with error rendered) ✓ |

## Next Plan Readiness

- **Plan 04-07 (coffees CRUD)** ready — mirror the roasters router shape (autocomplete on roaster + flavor-notes fields). Equipment is the shape to mirror for the simplest catalog entity; coffees adds the multi-autocomplete + ARRAY field handling on top.
- **Plan 04-08 (recipes CRUD)** ready — can mirror equipment's no-modal shape if recipes aren't picked from another form (TBD); adds the D-12 Duplicate flow via `HX-Redirect`.
- **Plan 04-09 (bag photo upload)** independent.
- **Plan 04-11 (autocomplete + mini-modal)** — explicitly does NOT consume equipment. The Phase 5 brew-session form will pick brewer/grinder/kettle by native `<select>`, not autocomplete.
- **Phase 5 (brew sessions)** — `equipment.usage_count` is ready to increment. The denormalized counter ships at server_default=0; brew-session insert will `UPDATE equipment SET usage_count = usage_count + 1 WHERE id IN (brewer_id, grinder_id, kettle_id)`.

## Self-Check

- `app/services/equipment.py` exists: FOUND
- `app/routers/equipment.py` exists: FOUND
- `app/main.py` modified (include_router(equipment_router.router)): FOUND
- `app/templates/pages/equipment.html` exists: FOUND
- `app/templates/fragments/equipment_list.html` exists: FOUND
- `app/templates/fragments/equipment_row.html` exists: FOUND
- `app/templates/fragments/equipment_form.html` exists: FOUND
- `tests/phase_04/test_routers_equipment.py` 11 real tests (replaced Wave-0 stub): FOUND
- Commit `5e20b9f` (Task 1) in `git log`: FOUND
- Commit `314e1e8` (Task 2) in `git log`: FOUND
- Container verify `pytest -q tests/phase_04/test_routers_equipment.py` returns `11 passed`: FOUND
- Phase 4 regression `pytest -q tests/phase_04/` returns `119 passed, 4 skipped`: FOUND
- Full suite `pytest -q` returns `234 passed, 6 skipped, 10 xfailed`: FOUND

## Self-Check: PASSED

---
*Phase: 04-shared-catalog*
*Plan: 06*
*Completed: 2026-05-19*
