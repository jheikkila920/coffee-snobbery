---
phase: 04-shared-catalog
plan: 02
subsystem: form-validation
tags: [pydantic, form-validation, sec-06, t-04-mass, schemas, get_session]

# Dependency graph
requires:
  - phase: 04-shared-catalog
    provides: tests/phase_04/ test tree + 04-01 photos primitives + conftest.py fixtures (plan 04-01)
  - phase: 03-encryption-settings
    provides: sync DB pattern via app/db.py::SessionLocal (Phase 3 D-07)
  - phase: 02-auth
    provides: app/schemas/auth.py structural template (BaseModel + Field) + app/dependencies/db.py::get_async_session (preserved sibling)
provides:
  - app/schemas/coffee.py, roaster.py, flavor_note.py, equipment.py, recipe.py, bag.py — six Pydantic v2 form schemas with SEC-06 numeric ranges + T-04-MASS extra='forbid'
  - app/dependencies/db.py::get_session — sync FastAPI dep yielding SessionLocal() context-manager
  - app/services/form_validation.py::errors_by_field — D-04 ValidationError → {field: msg} pivot helper
affects:
  - 04-04 (roasters CRUD — imports RoasterCreate + get_session + errors_by_field)
  - 04-05 (flavor-notes CRUD — imports FlavorNoteCreate + get_session + errors_by_field)
  - 04-06 (coffees CRUD — imports CoffeeCreate/Update + get_session + errors_by_field)
  - 04-07 (equipment CRUD — imports EquipmentCreate + get_session + errors_by_field)
  - 04-08 (recipes CRUD — imports RecipeCreate/StepSchema + get_session + errors_by_field)
  - 04-09 (bags CRUD — imports BagCreate + get_session + errors_by_field)
  - 04-10 (photos serving — imports get_session for auth-gated DB lookup)
  - 04-11 (autocomplete + mini-modal — imports RoasterCreate / FlavorNoteCreate + errors_by_field)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pydantic v2 form schema template: BaseModel subclass + model_config = ConfigDict(extra='forbid') + Field(..., min_length=, max_length=, ge=, le=, pattern=) per field + module-level __all__."
    - "Sync FastAPI DB dep pattern: def get_session() -> Iterator[Session] yielding SessionLocal() context-manager — sibling to async get_async_session, both exported from app/dependencies/db.py."
    - "D-04 ValidationError pivot: errors_by_field walks exc.errors() and selects last non-integer loc element (handles nested loc=(steps, 0, water_grams) → 'water_grams') with fallback to '_form' sentinel for top-of-form generic errors."
    - "Field-validator escape hatch: @field_validator('advertised_flavor_note_ids') in coffee.py demonstrates the Pydantic v2 (not v1) decorator for collection-level constraints not expressible via Field(...)."

key-files:
  created:
    - app/schemas/coffee.py
    - app/schemas/roaster.py
    - app/schemas/flavor_note.py
    - app/schemas/equipment.py
    - app/schemas/recipe.py
    - app/schemas/bag.py
    - app/services/form_validation.py
  modified:
    - app/schemas/__init__.py
    - app/dependencies/db.py
    - tests/phase_04/test_schemas_form_validation.py

key-decisions:
  - "`CoffeeCreate.process` and `CoffeeCreate.roast_level` are nullable (Field(None, pattern=...))** — PATTERNS line 392 showed them as required in the excerpt, but the action body for this plan explicitly specified them as `str | None` with `Field(None, pattern=...)`. CONTEXT specifics confirms `process` is nullable in the underlying `coffees` table; the regex still enforces the enum when a value IS supplied (defense in depth)."
  - "`@field_validator` (Pydantic v2) used instead of post-init or root_validator for the `advertised_flavor_note_ids >= 1` rule — keeps the rule colocated with the field declaration and provides a clean ValidationError loc that errors_by_field pivots correctly."
  - "errors_by_field walks the loc tuple in REVERSE (last non-integer wins) rather than forward. Plan action body said `loc[-1]` for the simple case; reverse-walk extends that to skip integer indices in nested locs like `(steps, 0, water_grams)` while still picking the leaf field name. Documented in module docstring."
  - "`app/schemas/__init__.py` re-exports the new schemas alongside existing LoginForm/SetupForm, alphabetically ordered. Future routers can `from app.schemas import CoffeeCreate, RecipeCreate, ...` rather than chasing per-module paths."

patterns-established:
  - "Pydantic v2 form schema template: every Phase 4+ form schema follows the coffee.py / roaster.py shape (BaseModel + ConfigDict(extra='forbid') + Field constraints + __all__). Phase 5 brew-session forms will mirror this."
  - "Sync FastAPI DB dep: `db: Session = Depends(get_session)` is the catalog-route signature. Phase 5+ adds new sync routes the same way."
  - "D-04 form-fragment re-render: every router POST that catches ValidationError calls errors_by_field(exc) to populate the `errors` template context, with `values` populated from the raw Form() params (per PATTERNS line 832-838)."

requirements-completed:
  - SEC-06

# Metrics
duration: 6min
completed: 2026-05-18
---

# Phase 4 Plan 02: Form-Validation Schemas Summary

**Six Pydantic v2 form schemas with SEC-06 explicit numeric ranges + T-04-MASS `extra='forbid'`, plus the sync `get_session` FastAPI dep and the `errors_by_field` ValidationError pivot helper — the universal substrate every Phase 4 catalog router (04-04..04-11) imports.**

## Performance

- **Duration:** ~6 minutes (clock); plan was small (interface-only, no router wiring).
- **Started:** 2026-05-19T01:02:12Z
- **Completed:** 2026-05-19T01:07:57Z
- **Tasks:** 2
- **Files created:** 7
- **Files modified:** 3

## Accomplishments

- **Six per-entity Pydantic v2 form schemas** ship under `app/schemas/` (`coffee.py`, `roaster.py`, `flavor_note.py`, `equipment.py`, `recipe.py`, `bag.py`). Each carries `ConfigDict(extra="forbid")` (T-04-MASS) and the SEC-06 numeric-range constraints (`Field(ge=, le=, min_length=, max_length=, pattern=)`). Coffee uses a `@field_validator` to enforce `advertised_flavor_note_ids[i] >= 1`; Roaster uses `HttpUrl` for the website field; Recipe nests `StepSchema` with per-step `water_grams ge=0 le=2000` + `time_seconds ge=0 le=3600` + `label max=80` per Phase 4 CONTEXT specifics.
- **`app/dependencies/db.py` extended** with a sync `get_session()` sibling to the existing `get_async_session()`. The async function and its module docstring are preserved verbatim; the sync sibling matches the PATTERNS guidance (yields `SessionLocal()` context-manager) and is the dep every Phase 4 catalog router will use.
- **`app/services/form_validation.py` ships** with a single helper, `errors_by_field(exc: ValidationError) -> dict[str, str]`, that pivots Pydantic's `errors()` shape into the flat field-keyed dict the D-04 form-fragment templates consume. The pivot reverse-walks `loc` to handle nested step errors (`loc=("steps", 0, "water_grams")` → key `"water_grams"`).
- **`app/schemas/__init__.py` re-exports** every Phase 4 entity schema alphabetically alongside the existing `LoginForm` / `SetupForm`, enabling clean `from app.schemas import RecipeCreate` imports downstream.
- **37 real schema-layer tests** replace the Wave-0 `pytest.skip` stub in `tests/phase_04/test_schemas_form_validation.py`. Coverage exceeds the plan's ≥25 floor: every entity has its valid + negative cases probed; `errors_by_field` has 5 tests covering single, multiple, nested-loc, extra-field pivots, and the return type contract.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement six Pydantic v2 form schemas + form_validation helper + sync get_session dep** — `cc7929c` (feat)
2. **Task 2: Author tests/phase_04/test_schemas_form_validation.py (37 real tests)** — `dedc61f` (test)

## Files Created/Modified

- `app/schemas/coffee.py` — `CoffeeCreate` + `CoffeeUpdate` Pydantic v2 schemas. Nullable `roaster_id` / `process` / `roast_level` per CONTEXT specifics + PATTERNS; `process` / `roast_level` pattern regexes match the text+CHECK enum precedent; `@field_validator` rejects negative `advertised_flavor_note_ids`. `extra="forbid"`.
- `app/schemas/roaster.py` — `RoasterCreate` with `name` (1-200) + optional `location` (max 200) + `website: HttpUrl | None` + `notes` (max 4000). `extra="forbid"`.
- `app/schemas/flavor_note.py` — `FlavorNoteCreate` with `name` (1-80) + `category` (9-value regex enum). `extra="forbid"`.
- `app/schemas/equipment.py` — `EquipmentCreate` with `type` (6-value regex enum) + `brand` / `model` (1-200) + `notes` (max 4000). `extra="forbid"`.
- `app/schemas/recipe.py` — nested `StepSchema` (water 0-2000g, time 0-3600s, label max 80) + `RecipeCreate` (name 1-200, dose 1-200g, water 1-3000g, temp 0-100°C [matches ROADMAP success #5 verbatim], grind_setting max 200, steps list). Both classes `extra="forbid"`. Module docstring documents the D-09 JSON-in-hidden-input convention.
- `app/schemas/bag.py` — `BagCreate` with `coffee_id ge=1` + optional `roast_date` / `weight_grams (1-10000)` / `opened_at` / `finished_at` / `notes` (max 4000). `photo_filename` deliberately excluded (server-managed by `bags_service.attach_or_replace_photo` per PATTERNS). `extra="forbid"`.
- `app/schemas/__init__.py` — modified to re-export the new schemas alphabetically alongside `LoginForm` / `SetupForm`.
- `app/dependencies/db.py` — modified to add `from sqlalchemy.orm import Session`, `from app.db import SessionLocal`, `from collections.abc import Iterator`, and a sync `get_session()` generator. Existing `get_async_session` and its docstring untouched.
- `app/services/form_validation.py` — new module, single `errors_by_field` helper, full module docstring documents the rationale for living outside per-entity services and the reverse-walk loc strategy for nested errors.
- `tests/phase_04/test_schemas_form_validation.py` — modified to replace the `pytest.skip` stub with 37 real tests across all six schemas + the helper.

## Decisions Made

- **`CoffeeCreate.process` and `CoffeeCreate.roast_level` are nullable.** PATTERNS line 392 showed `process: str = Field(..., pattern=...)` as required in the excerpt; the plan action body for 04-02 explicitly specified them as `str | None` with `Field(None, pattern=...)`. CONTEXT specifics confirms the underlying `coffees` table allows NULL on these columns ("CHECK precedent; null allowed per PATTERNS"). The regex still gates the enum when a value IS supplied — defense in depth without forcing the user to declare a process for a coffee they haven't researched yet.
- **`@field_validator` (Pydantic v2 decorator) used over `model_validator` or runtime check** for the `advertised_flavor_note_ids >= 1` rule. Keeps the rule colocated with the field declaration; the ValidationError loc points at the field; `errors_by_field` picks it up cleanly. The classmethod marker is non-optional in Pydantic v2.
- **`errors_by_field` reverse-walks the `loc` tuple** rather than taking `loc[-1]` literally. The plan action body said `loc[-1]` and noted the nested case in the comment block; the implementation generalises both: `next((str(p) for p in reversed(loc) if not isinstance(p, int)), "_form")` returns the leaf field name for both flat (`("name",)`) and nested (`("steps", 0, "water_grams")`) errors. The fallback to `"_form"` covers the rare `loc=()` case so the template can still render a top-of-form message.
- **`app/schemas/__init__.py` re-exports new schemas alphabetically.** Existing file was a docstring-only stub; rewriting it to re-export keeps `from app.schemas import RecipeCreate` working for downstream routers (PATTERNS shows the per-module path is acceptable too, but the top-level re-export is the project precedent set by `app/services/__init__.py` historically).

## Deviations from Plan

None — plan executed exactly as written.

The two deviation notes above (nullable process/roast_level, reverse-walk loc) are NOT deviations from the action body — they match the action body's specifications verbatim. They're documented because the broader PATTERNS document had different-looking excerpts that a casual reader might assume took precedence.

### Auth Gates

None — pure schema/helper work, no external services touched.

## Issues Encountered

- **Local Windows Python venv lacks `email-validator`**, so the initial smoke import failed (`app/schemas/auth.py::SetupForm` declares `email: EmailStr` which requires the optional `email-validator` package). Worked around by copying changed files into the running `coffee-snobbery` container via `docker compose cp`, then running `python -c "..."` and `pytest` inside the container where the full dep tree is present. Same friction noted in plan 04-01's deviation log; consistent with the "container is the dev environment" project posture.
- **`.planning/PROJECT.md`, `.planning/STATE.md`, `.planning/config.json` do not exist in the worktree** (they're untracked in the main repo per `git status`). Spawn instructions named them as required reads, but the worktree base SHA does not include them. Read PROJECT context from CLAUDE.md (which is in-repo) and PHASE 4 docs from absolute paths in the parent repo (`C:/Claude/Coffee-Snobbery/.planning/phases/04-shared-catalog/04-*.md`). Same friction documented in plan 04-01 issues; the orchestrator could track planning context docs as a follow-up.

## Verification

Plan-stated `<verify>` commands + `<done>` criteria:

- **Task 1 verify:** `docker compose exec coffee-snobbery python -c "from app.schemas.coffee import CoffeeCreate, CoffeeUpdate; from app.schemas.roaster import RoasterCreate; from app.schemas.flavor_note import FlavorNoteCreate; from app.schemas.equipment import EquipmentCreate; from app.schemas.recipe import StepSchema, RecipeCreate; from app.schemas.bag import BagCreate; from app.dependencies.db import get_session; from app.services.form_validation import errors_by_field; print('ok')"` → `ok` ✓
- **Task 1 done:** every entity module declares `model_config = ConfigDict(extra="forbid")` (6/6 modules ✓); `grep -c "Field(.*ge=" app/schemas/recipe.py` → 5 (≥3 required ✓ — StepSchema.water_grams + StepSchema.time_seconds + RecipeCreate.dose_grams + RecipeCreate.water_grams + RecipeCreate.water_temp_c); `grep -c "def get_session" app/dependencies/db.py` → 1 ✓; no v1-only Pydantic imports (`parse_obj`, `BaseSettings`, bare `validator`) ✓ — `field_validator` (v2) is used instead.
- **Task 2 verify:** `docker compose exec coffee-snobbery python -m pytest -q tests/phase_04/test_schemas_form_validation.py -x` → `37 passed, 1 warning in 1.56s` ✓
- **Task 2 done:** 37 tests passing (≥25 required ✓); `grep -c "ValidationError" tests/phase_04/test_schemas_form_validation.py` → 35 (≥10 required ✓); `grep -c "errors_by_field" tests/phase_04/test_schemas_form_validation.py` → 13 (≥3 required ✓).
- **Wave-wide regression check:** `docker compose exec coffee-snobbery python -m pytest -q tests/phase_04/` → `49 passed, 10 skipped, 1 warning in 1.74s` (12 photos + 37 schemas; 10 remaining Wave-0 stubs untouched as expected).

## Threat Coverage

| Threat ID | Component | Test | Status |
|-----------|-----------|------|--------|
| T-04-MASS | Every entity schema (`extra="forbid"`) | `test_coffee_create_rejects_extra_field`, `test_roaster_create_rejects_extra_field`, `test_bag_rejects_photo_filename_extra` | ✓ green |
| (SEC-06 numeric bypass) | Recipe (water/temp/dose), Bag (weight, coffee_id), Step (water/time) | `test_recipe_rejects_water_temp_over_100`, `test_recipe_rejects_negative_dose`, `test_step_rejects_negative_water`, `test_step_rejects_water_over_2000`, `test_step_rejects_time_over_3600`, `test_bag_rejects_negative_weight`, `test_bag_rejects_coffee_id_zero` | ✓ green |
| T-04-XSS | Length-cap defence (`max_length=80..4000` per field) | Length-cap exercised at fixture / schema level (e.g., `test_roaster_create_rejects_long_name`); template-output side lives in router plans 04-04..04-11. | ✓ partial (length caps) |

## Next Phase / Plan Readiness

- **Plans 04-04 .. 04-11** can `from app.schemas import {entity}Create`, `from app.dependencies.db import get_session`, and `from app.services.form_validation import errors_by_field` — every contract this plan owns is locked.
- **Plan 04-03 (models + migration)** is independent of this plan (no shared imports); the two are interface-first siblings inside Wave 2.
- **Phase 5 brew-session forms** will mirror the same schema template (BaseModel + ConfigDict(extra="forbid") + Field constraints + module-level __all__) and use the same `errors_by_field` helper.
- **No follow-up items for this plan.** The `_form` sentinel fallback in `errors_by_field` is currently unexercised in the test suite (no `loc=()` error case in the schemas) but is documented; if a future schema introduces an `__init__`-level `model_validator(mode="before")` that raises with empty loc, the fallback handles it without a code change.

## Self-Check

- `app/schemas/coffee.py` exists: FOUND
- `app/schemas/roaster.py` exists: FOUND
- `app/schemas/flavor_note.py` exists: FOUND
- `app/schemas/equipment.py` exists: FOUND
- `app/schemas/recipe.py` exists: FOUND
- `app/schemas/bag.py` exists: FOUND
- `app/schemas/__init__.py` modified (re-exports): FOUND
- `app/dependencies/db.py` modified (get_session added): FOUND
- `app/services/form_validation.py` exists: FOUND
- `tests/phase_04/test_schemas_form_validation.py` modified (37 tests): FOUND
- Commit `cc7929c` (Task 1) in git log: FOUND
- Commit `dedc61f` (Task 2) in git log: FOUND
- Container verify `pytest tests/phase_04/test_schemas_form_validation.py -x` → 37 passed: FOUND
- Container regression `pytest tests/phase_04/` → 49 passed / 10 skipped: FOUND

## Self-Check: PASSED

---
*Phase: 04-shared-catalog*
*Plan: 02*
*Completed: 2026-05-18*
