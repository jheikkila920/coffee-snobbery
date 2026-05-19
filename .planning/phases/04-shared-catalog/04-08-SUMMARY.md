---
phase: 04-shared-catalog
plan: 08
subsystem: recipes-crud
tags: [recipes, crud, htmx, alpine, csp-build, jsonb, hx-redirect, wave-6]

# Dependency graph
requires:
  - phase: 04-shared-catalog
    provides: app/schemas/recipe.py (RecipeCreate + StepSchema) + app/services/form_validation.py::errors_by_field (plan 04-02); app/models/recipe.py (Recipe — JSONB steps) (plan 04-03); app/events.py CATALOG_RECIPE_* constants (plan 04-01); the universal Phase 4 catalog router template (plan 04-04 — roasters)
  - phase: 02-auth
    provides: app/dependencies/auth::require_user + tests/conftest.py seeded_admin_user
  - phase: 01-middleware
    provides: app/templates_setup.py templates + base.html (CSP nonce + HTMX core + listener); app/static/js/alpine-components/__init.js (Alpine CSP-build convention scaffold); docs/decisions/0001-csp-strict-no-unsafe-eval.md
provides:
  - app/services/recipes.py — sync Session CRUD + audit-event emit (CAT-06) + duplicate_recipe deep-copy (D-12) + RecipeNotFound domain exception
  - app/routers/recipes.py — 8 HTMX endpoints under /recipes; first ship of the HX-Redirect (D-12) response-header pattern locked for Phase 5+
  - app/templates/pages/recipes.html — list page
  - app/templates/fragments/recipe_list.html, recipe_row.html, recipe_form.html, recipe_step_builder.html, pour_timeline.html — recipe-specific fragments
  - app/static/js/alpine-components/recipe-step-builder.js — FIRST live Alpine CSP-build component shipped (Alpine.data('recipeStepBuilder', ...))
  - HX-Redirect contract: 200 + header HX-Redirect: <url> + empty body — Phase 5+ cross-page navigation pattern
affects:
  - 04-11 (autocomplete + mini-modal — ships two more Alpine CSP-build components: miniModal + autocomplete; reuses the recipe-step-builder.js loading convention in base.html)
  - 05 (brew sessions — references recipes.id via brew_sessions.recipe_id; D-12 duplicate-recipe substitutes for "recipe versioning" so brew sessions keep their recipe reference intact when a user edits a copy)
  - 07 (AI service — AI-06 suggests recipes from this user's own catalog; the JSONB steps shape is the source of truth)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HX-Redirect response header (D-12): handler returns Response(status_code=200, headers={'HX-Redirect': '/recipes/{new_id}/edit'}) with an empty body. HTMX 2.0 consumes the header and performs window.location navigation. Same-tab, fresh page load, edit form pre-populated. Locked for Phase 5+ cross-page nav flows triggered from HTMX swaps."
    - "Alpine CSP-build component loading: base.html loads each component's .js file BEFORE the @alpinejs/csp core script so Alpine.data registrations are present at boot. One <script defer> tag per component file under app/static/js/alpine-components/. Plan 04-11 adds miniModal + autocomplete via the same pattern."
    - "JSON-as-hidden-input form payload: Alpine step builder serialises its local `steps` array via JSON.stringify into a hidden <input name='steps' :value='stepsJson'> (CSP-build :value declarative bind). Router does json.loads BEFORE constructing RecipeCreate; JSONDecodeError folds into a '_steps' banner. The schema layer (StepSchema with extra='forbid') is the authoritative per-step validator."
    - "data-initial-steps seed pattern: form fragment stamps `data-initial-steps='{{ steps_json }}'` onto the x-data wrapper; the Alpine component's init() reads `this.$root.dataset.initialSteps` and JSON.parse'es it. Jinja's `|tojson` filter (planned use) was rendered moot because the router serialises with json.dumps() server-side; the attribute value is then HTML-autoescaped by Jinja's default autoescape (no |safe needed). This is the pattern for any future Alpine component that needs an initial-state seed."
    - "Per-step Pydantic ValidationError folding (Phase 4 ships banner-only): any nested loc starting with 'steps' is folded into a single '_steps' banner above the step builder. Per-step ring-1 ring-red-300 highlighting per UI-SPEC is a plan 04-11 follow-up — the schema layer is correctly enforcing the per-step ranges, the question is only the UI surface area for surfacing them."
    - "Recipe deep-copy via [dict(s) for s in src.steps]: a shallow list(src.steps) would share inner dict references — a subsequent update_recipe overwriting the source's steps would mutate the copy's steps too (psycopg returns the same Python objects from JSONB until the next fetch). The per-dict copy is the minimal defense; documented in test_duplicate_recipe_steps_independent."

key-files:
  created:
    - app/services/recipes.py
    - app/routers/recipes.py
    - app/templates/pages/recipes.html
    - app/templates/fragments/recipe_list.html
    - app/templates/fragments/recipe_row.html
    - app/templates/fragments/recipe_form.html
    - app/templates/fragments/recipe_step_builder.html
    - app/templates/fragments/pour_timeline.html
    - app/static/js/alpine-components/recipe-step-builder.js
    - tests/phase_04/test_services_recipes.py
  modified:
    - app/main.py
    - app/templates/base.html
    - app/static/js/alpine-components/__init.js
    - tests/phase_04/test_routers_recipes.py

key-decisions:
  - "Banner-only per-step error rendering for Phase 4 (defer per-step ring highlighting to plan 04-11). The shared errors_by_field helper picks the last non-int loc component, which would collide field keys for nested step errors (e.g., loc=('steps', 2, 'water_grams') → 'water_grams' collides with hypothetical top-level water_grams). The router's local _normalize_errors function detects loc[0] == 'steps' and folds into a single '_steps' banner above the step builder. Per-step inline highlighting is a UI polish task that doesn't gate the data-correctness contract."
  - "Stacked div segments (NOT SVG) for the pour-timeline preview. Each segment's flex-basis is the step's time-delta ratio with a min-basis to keep very-short segments visible. Alternating bg-espresso-700 / bg-espresso-500 distinguishes adjacent steps per UI-SPEC. SVG was rejected as overkill for household scale — the div approach is ~30 lines of template and integrates cleanly with Alpine reactivity."
  - "Recipe deep-copy uses per-dict copy: copy.steps = [dict(s) for s in src.steps]. A shallow list(src.steps) shares inner dict references; the next update_recipe on the source would silently mutate the copy. Test test_duplicate_recipe_steps_independent locks the behavior."
  - "RecipeNotFound domain exception (NOT HTTPException) raised from the service. Keeps the service module free of FastAPI types — the router catches and re-raises as HTTPException(404). Same pattern as Phase 3 credentials.OrphanCiphertextError."
  - "Single x-data wrapper around step builder + hidden steps input + pour-timeline preview. One Alpine scope means the hidden input's :value='stepsJson' binding stays reactive to the step builder's steps array AND the pour-timeline reads the same `timelineSegments` getter. Splitting into three scopes would have required cross-component state sharing via Alpine.store or events — overkill."
  - "Recipe form's `_coerce_numeric` helper converts the str-typed numeric form values to int BEFORE the Pydantic schema. Without it, Pydantic v2 will accept the string under default coercion rules but emits the field error against an unexpected type when the value is non-numeric. The helper makes the error-render path predictable: a non-numeric typed value (e.g., dose='abc') surfaces as a clean field-level error."
  - "Test fixture `clean_recipes` deletes brew_sessions in its OWN transaction. Phase 5 hasn't created the table yet; trying it inside the same transaction as the recipes DELETE would taint the connection (psycopg aborts on missing-table errors). Two separate `with engine.begin()` blocks keep the failure isolated. Documented Rule 1 deviation below."
  - "Empty form seeded with one Bloom step (water_grams=50, time_seconds=45, label='Bloom'). UI-SPEC §'Recipe Step Builder' calls for this as the starting state: zero-step recipes are valid, but a blank step builder is disorienting. The default ships in the router's `_DEFAULT_NEW_STEPS` constant, JSON-encoded into the form context as `steps_json`."
  - "alpine-components/__init.js stays as documentation-only (no live registrations). The recipe-step-builder.js file contains its own `alpine:init` listener and Alpine.data registration; __init.js is updated only to point future readers at the live component(s). Plan 04-11 adds two more components via the same pattern (one file per component, one <script defer> tag in base.html). Aggregating into one registration file was considered and rejected — keeps the load order self-evident."

patterns-established:
  - "HX-Redirect for cross-page navigation triggered from HTMX swaps: handler returns Response(status_code=200, headers={'HX-Redirect': '<url>'}). Used for D-12 duplicate-recipe; reusable in Phase 5+ for any 'create a thing and jump to its edit page' flow (e.g., 'duplicate brew session' or 'create new brew session from this recipe')."
  - "Alpine CSP-build component load order: per-component .js file in /static/js/alpine-components/<name>.js loaded by base.html via its own <script defer> tag BEFORE the @alpinejs/csp core script. The defer attribute serialises load order; the alpine:init listener registers the component before Alpine boots and walks the DOM."
  - "JSON-as-hidden-input form payload pattern: Alpine local state → JSON.stringify → hidden input → router json.loads → schema validate. Locks the contract for any future Alpine component that needs to submit structured data (e.g., plan 04-11's mini-modal pre-selected entity payload, Phase 5's brew session timer events array)."
  - "data-initial-steps seed pattern: server stamps initial-state JSON onto the x-data wrapping element's data-* attribute; Alpine component's init() reads this.$root.dataset.<key> and JSON.parses it. Server-side autoescape keeps the attribute safe; no |safe needed."

requirements-completed:
  - CAT-06

# Metrics
duration: 50min
completed: 2026-05-19
---

# Phase 4 Plan 08: Recipes CRUD Summary

**Ships CAT-06 — recipes CRUD with the Alpine-driven multi-step pour timeline + the D-12 duplicate-recipe HX-Redirect flow. The first live Alpine CSP-build component on the wire (plan 04-11 will ship miniModal + autocomplete via the same loading convention).**

## Performance

- **Duration:** ~50 minutes
- **Tasks:** 3
- **Files created:** 10 (1 service + 1 router + 6 templates + 1 Alpine component + 1 service test file + 1 router test file replacing the Wave-0 stub)
- **Files modified:** 3 (`app/main.py`, `app/templates/base.html`, `app/static/js/alpine-components/__init.js`)

## Accomplishments

- **`app/services/recipes.py`** ships full CAT-06 CRUD mirroring the roasters service shape: sync Session, kwargs-only API after a leading `*`, single commit per write, structlog audit event at the end of each write. Functions: `create_recipe`, `get_recipe`, `list_recipes` (with `include_archived` filter), `update_recipe` (Core `update()` so `updated_at = func.now()` is stamped in the same statement), `archive_recipe` (soft-delete), and **`duplicate_recipe`** — the D-12 deep-copy substitute for recipe versioning. Raises a `RecipeNotFound` domain exception (router catches and re-raises as `HTTPException(404)`) so the service stays FastAPI-agnostic. Audit events: `CATALOG_RECIPE_CREATED`, `CATALOG_RECIPE_UPDATED`, `CATALOG_RECIPE_ARCHIVED`, `CATALOG_RECIPE_DUPLICATED`.
- **`app/routers/recipes.py`** implements 8 endpoints under `/recipes`: list (page + HTMX fragment), new (form fragment seeded with one Bloom step), empty-form (Cancel round-trip), POST create (row fragment + OOB form-clear), edit form, POST update, **POST duplicate (HX-Redirect)**, POST archive. POST handlers are async + read raw form via `await request.form()` so unknown fields trip the schema's `extra='forbid'` (T-04-MASS). The `steps` field is JSON-parsed via `json.loads` BEFORE constructing `RecipeCreate`; JSON-decode failure folds into the `_steps` banner. The local `_normalize_errors` function detects nested `loc[0] == 'steps'` and folds into a `_steps` banner — per-step ring highlighting per UI-SPEC is deferred to plan 04-11.
- **`app/static/js/alpine-components/recipe-step-builder.js`** is the first live Alpine CSP-build component shipped in the project. `Alpine.data('recipeStepBuilder', ...)` exposes:
  - `init()` — reads `data-initial-steps`, JSON.parses, seeds with one Bloom step if empty.
  - `addStep()` — inserts a new step pre-filled with `(prev.water + 50, prev.time + 45, label='')`.
  - `removeStep(i)`, `moveUp(i)`, `moveDown(i)` — array mutations (Alpine reactivity wraps each step dict on push/splice).
  - `setLabel(i,v)`, `setWater(i,v)`, `setTime(i,v)` — handler-routed property writes (CSP-build forbids x-model; `:value` + `@input="setWater(idx, $event.target.value)"` is the substitute).
  - `deltaWater(i)`, `deltaTime(i)`, `formatTime(s)`, `formatDelta(i)` — read-only computed helpers used by step rows.
  - `totalWater`, `totalTime`, `totalLine`, `stepsJson`, `timelineSegments` — getters consumed by the form footer + hidden input + pour-timeline preview.
- **Six templates** ship the full recipes UI:
  - `pages/recipes.html` — list page + h1 + Add recipe button + `#recipe-form-mount` + `#recipe-list`.
  - `fragments/recipe_list.html` — desktop table (Name · Dose · Water · Ratio · Brewer · Actions) + mobile cards.
  - `fragments/recipe_row.html` — unified mode=row|card with Edit + Duplicate (`hx-post="/recipes/{{ id }}/duplicate"`) + Archive (with confirm); OOB form-clear when `include_oob_form_clear` is set.
  - `fragments/recipe_form.html` — single `x-data="recipeStepBuilder"` wrapper with `data-initial-steps="{{ steps_json }}"`; embeds the step builder + pour-timeline preview + hidden `name="steps" :value="stepsJson"` input.
  - `fragments/recipe_step_builder.html` — 44×44 up/down/remove tap targets, ARIA labels per UI-SPEC; per-step Δ readout.
  - `fragments/pour_timeline.html` — stacked div segments with alternating `bg-espresso-700` / `bg-espresso-500` (D-11); empty-state placeholder via `x-if="totalTime === 0"`.
- **`app/templates/base.html`** now loads `recipe-step-builder.js` BEFORE the `@alpinejs/csp` core script via its own `<script defer>` tag. Plan 04-11 will add two more `<script defer>` lines for `mini-modal.js` + `autocomplete.js`.
- **`app/main.py`** modified to include the recipes router after equipment.
- **21 real tests** (6 service + 15 router) replace the Wave-0 stub in `tests/phase_04/test_routers_recipes.py`. Service tests cover JSONB round-trip with order preserved, empty steps round-trip, duplicate clones all fields with "(copy)" suffix, deep-copy independence (mutating source steps does NOT mutate copy), unknown id raises `RecipeNotFound`, archive flips `archived=True`. Router tests cover page render, valid POST + row fragment, water_temp>100 rejected, dose=0 rejected, multi-step JSONB round-trip via POST, invalid steps JSON → `_steps` banner, per-step water>2000 rejected, T-04-MASS extra field, edit pre-populates `data-initial-steps`, update persists changes, **D-12 duplicate emits HX-Redirect**, duplicate 404 on unknown id, archive marks archived, CSRF missing → 403, UI-SPEC lock that the duplicate button renders on the list row.

## Task Commits

Each task was committed atomically:

1. **Task 1: Service + router + main.py wiring** — `f69a465` (feat)
2. **Task 2: Alpine step builder + templates + base.html wire-up** — `3bfc537` (feat)
3. **Task 3: Real router + service tests (21 passing)** — `26b4e10` (test)

## Decisions Made

- **Banner-only per-step error rendering for Phase 4** (defer per-step ring highlighting to plan 04-11). The shared `errors_by_field` helper picks the last non-int loc component, which would collide field keys for nested step errors. The router's local `_normalize_errors` detects `loc[0] == 'steps'` and folds into a single `_steps` banner above the step builder.
- **Stacked div segments (NOT SVG) for the pour-timeline preview.** Each segment's `flex-basis` is the step's time-delta ratio with a min-basis keeping very-short segments visible. Alternating `bg-espresso-700` / `bg-espresso-500` distinguishes adjacent steps per UI-SPEC §"Pour-Timeline Preview". SVG was overkill for household scale.
- **Recipe deep-copy uses per-dict copy:** `copy.steps = [dict(s) for s in src.steps]`. A shallow `list(src.steps)` would share inner dict references — the next `update_recipe` on the source would silently mutate the copy's steps. Test `test_duplicate_recipe_steps_independent` locks the behavior.
- **`RecipeNotFound` domain exception (NOT `HTTPException`) raised from the service.** Keeps the service module free of FastAPI types — the router catches and re-raises as `HTTPException(404)`. Same pattern as Phase 3 `credentials.OrphanCiphertextError`.
- **Single `x-data="recipeStepBuilder"` wrapper around step builder + hidden steps input + pour-timeline preview.** One Alpine scope means the hidden input's `:value="stepsJson"` binding stays reactive to the step array AND the pour-timeline reads the same `timelineSegments` getter. Splitting into three scopes would have required Alpine.store or cross-component events.
- **`_coerce_numeric` helper converts str-typed form values to int** BEFORE the Pydantic schema. Without it, a non-numeric value (e.g., `dose='abc'`) yields an opaque error against an unexpected type instead of a clean field-level error.
- **Test fixture `clean_recipes` deletes `brew_sessions` in its OWN transaction.** Phase 5 hasn't created the table yet; trying it inside the same transaction as the `recipes` DELETE taints the connection (psycopg aborts on missing-table errors). Two separate `with engine.begin()` blocks keep the failure isolated.
- **Empty form seeded with one Bloom step** (`water_grams=50, time_seconds=45, label='Bloom'`). UI-SPEC §"Recipe Step Builder" calls for this as the starting state.
- **`alpine-components/__init.js` stays documentation-only.** The `recipe-step-builder.js` file contains its own `alpine:init` listener and `Alpine.data` registration; `__init.js` is updated only to point future readers at the live component. Plan 04-11 adds two more components via the same one-file-one-`<script defer>`-tag pattern.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `brew_sessions` optional DELETE in `clean_recipes` fixture tainted the transaction when the table didn't exist**

- **Found during:** Task 3 (first run of recipes tests against the live DB).
- **Issue:** The fixture initially ran `DELETE FROM brew_sessions` followed by `DELETE FROM recipes` inside ONE `with engine.begin()` block, wrapping the optional delete in a `try/except`. psycopg aborts the entire transaction on a missing-table error (`InFailedSqlTransaction`) — even though the Python-level `except Exception` swallowed the SQLAlchemy exception, the connection was left in an aborted state and the subsequent `DELETE FROM recipes` failed with the same error.
- **Fix:** Moved the `brew_sessions` DELETE into its own `with engine.begin()` block. If the table is missing, the inner block raises, the outer try/except swallows it, and a fresh `with engine.begin()` opens a clean connection for the `recipes` DELETE.
- **Files modified:** `tests/phase_04/test_routers_recipes.py`, `tests/phase_04/test_services_recipes.py` (committed in `26b4e10`).
- **Verification:** All 21 recipes tests pass; the full Phase 4 suite still reports 140 passed / 3 skipped; full project suite reports 256 passed / 5 skipped / 10 xfailed.

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).

**Impact on plan:** Stayed inside files already named in the plan's `files_modified`. The two-transaction pattern is now the canonical shape for Phase 4 test fixtures that need to wipe a Phase 5+ optional table — plans 05-* will likely encounter the same friction.

## Issues Encountered

- **Docker container is image-baked, not bind-mounted.** Every iteration required `docker cp <file> coffee-snobbery:/app/...` before running the in-container verification. Same friction documented in 04-01..04-04 SUMMARIES.
- **Worktree base SHA does not include the Phase 4 context docs.** `04-UI-SPEC.md`, `04-CONTEXT.md`, etc. were read from absolute paths in the parent repo (`C:/Claude/Coffee-Snobbery/.planning/phases/04-shared-catalog/...`). Same friction as previous Phase 4 plans.
- **Worktree base drift on spawn.** The agent spawned at commit `56d309157d1c822772130038bf970f4f5276ed6e` instead of the expected `8620b24f`; the worktree-base assertion at startup corrected via `git fetch --all && git reset --hard 8620b24`. Documented in the response header for the orchestrator.
- **pytest cache permission warnings** in the container (`Permission denied: '/app/pytest-cache-files-*'`) — pre-existing, doesn't affect test results.

## User Setup Required

None — this plan ships routes + templates + tests + one new JS file. No new env vars, no external service configuration. The new `<script defer>` line in `base.html` loads from `/static/`, which is already mounted.

## Verification

Plan-stated verify commands + `<done>` criteria:

- **Task 1 verify:** `docker exec coffee-snobbery python -c "from app.routers.recipes import router; from app.services.recipes import create_recipe, duplicate_recipe, list_recipes; print(router.prefix, 'ok')"` → `/recipes ok` ✓
- **Task 1 done criteria:**
  - `grep -c 'CATALOG_RECIPE' app/services/recipes.py` → `8` ✓ (≥4 required)
  - `grep -c 'HX-Redirect' app/routers/recipes.py` → `6` ✓ (≥1 required)
  - `grep -c 'json.loads' app/routers/recipes.py` → `4` ✓ (≥1 required)
- **Task 2 verify:** `docker exec coffee-snobbery test -f app/static/js/alpine-components/recipe-step-builder.js && grep -c "Alpine.data('recipeStepBuilder'" app/static/js/alpine-components/recipe-step-builder.js` → `1` ✓
- **Task 2 done criteria:**
  - JS file exists, Alpine.data registration count = 1 ✓
  - All 8 template/static files present (6 recipe templates + 1 JS + base.html modification) ✓
  - `grep -c 'x-data="recipeStepBuilder"' app/templates/fragments/recipe_form.html` → `2` ✓ (form + step builder share the scope; the form template references it as the wrapper)
  - `grep -E '\|safe'` over recipe templates → no matches ✓
  - `grep -E 'hx-on:'` over recipe templates → no matches ✓
  - `grep -E 'x-data="\{'` over recipe templates → no matches (no inline-object literal) ✓
- **Task 3 verify:** `docker exec coffee-snobbery pytest -q tests/phase_04/test_routers_recipes.py tests/phase_04/test_services_recipes.py -x` → `21 passed` ✓
- **Task 3 done criteria:**
  - 21 tests passing (≥21 required, 6 service + 15 router) ✓
  - `grep -c 'HX-Redirect' tests/phase_04/test_routers_recipes.py` → `5` ✓ (≥1 required)
  - `grep -c 'steps_jsonb_round_trip' tests/phase_04/test_services_recipes.py tests/phase_04/test_routers_recipes.py` → 1 per file ✓

**Wave-wide regression check:** `docker exec coffee-snobbery pytest -q tests/phase_04/` → `140 passed, 3 skipped, 7 warnings` (was 123 passed, 4 skipped before this plan — net +17 passed, -1 skipped from the Wave-0 stub now replaced, the remaining 3 skipped are Wave-0 stubs for 04-07/04-09/04-11 not yet filled).

**Full suite:** `docker exec coffee-snobbery pytest -q` → `256 passed, 5 skipped, 10 xfailed, 34 warnings` — no regressions traced to this plan.

## Threat Coverage

| Threat ID | Component | Mitigation | Test |
|-----------|-----------|------------|------|
| T-04-CSRF | All state-changing recipe routes (POST /, /{id}, /{id}/duplicate, /{id}/archive) | Every form template carries the hidden `X-CSRF-Token` input verbatim; `CSRFFormFieldShim` hoists it into the header; the duplicate POST originates from an HTMX request that carries `X-CSRF-Token` via the global `htmx:configRequest` listener (`htmx-listeners.js`). | `test_csrf_missing_returns_403` (POST /recipes with mismatched CSRF → 403) ✓ |
| T-04-XSS | Templates rendering `recipe.name`, step labels, `grind_setting` | Jinja autoescape ON globally; `|safe` not used anywhere in the new templates; `data-initial-steps` uses Jinja's standard attribute autoescape — JSON contains only ASCII (no `<`, `>`, `&` unless inside user-supplied step labels, which Jinja escapes correctly inside an attribute). | Grep check: `grep -E '\|safe'` → no matches ✓ |
| T-04-MASS | POST /recipes, POST /recipes/{id} (including nested step) | `RecipeCreate` + `StepSchema` declare `model_config = ConfigDict(extra="forbid")`; handler uses `await request.form()` so unknown fields reach the schema; `_normalize_errors` folds unknown-key rejections into the `_form` banner. | `test_create_recipe_extra_field_rejected` (POST with `is_admin=true` → 200 + form with `text-red-700`) ✓ |
| (steps DoS) | POST /recipes with absurdly large steps array | The JSON parse + Pydantic validation happens in-memory; the request body is bounded by Starlette's default 1MB form-size limit (no explicit `max_length=50` was added on the steps field per the planner's open question — see "Next Plan Readiness"). | Not exercised by a dedicated test; bounded by Starlette body limit. |
| (steps order tampering) | JSON payload reordering by adversary | Server doesn't trust client ordering for any semantic check — order is just persisted as-given. Pydantic validates per-step values; the deep-copy in `duplicate_recipe` preserves order via list iteration. | `test_create_recipe_steps_jsonb_round_trip` (service) + `test_create_recipe_steps_jsonb_round_trip_via_post` (router) ✓ |

## Threat Flags

(none — no new security-relevant surface beyond what the threat_model already covers)

## Next Plan Readiness

- **Plan 04-09 (bag photo upload)** ready — independent of this plan.
- **Plan 04-11 (autocomplete + mini-modal)** ready — adopts the same Alpine CSP-build component loading convention (`<script defer>` in `base.html` before the `@alpinejs/csp` core script). The `HX-Trigger` payload from `roaster-created` / `flavor-note-created` events feeds the mini-modal's pre-select flow; the autocomplete dropdown shares the `fragments/autocomplete_list.html` already established by plan 04-04.
- **Phase 5 (brew sessions)** ready — `brew_sessions.recipe_id` references this plan's `recipes.id`; the D-12 duplicate-recipe substitute keeps brew sessions' references stable when a user "versions" a recipe by duplicating + editing. The `HX-Redirect` contract is reusable for any "create + jump to edit" flow (e.g., "duplicate session", "create session from this recipe").
- **Phase 7 (AI service AI-06)** ready — recipe `steps` JSONB is the source-of-truth shape; the AI's "suggest a recipe" output should write through `recipes_service.create_recipe(...)` with the same `list[dict]` step shape.

## Open Questions (raised for future plans, not blockers here)

- **Should `RecipeCreate.steps` get a `max_length=N` constraint?** The planner left this open ("planner picks; recommendation: add it to defend against absurd payloads"). Phase 4 ships without an explicit per-array cap — Starlette's 1MB body limit is the de facto cap. Plan 04-11 or a future hardening pass can add `Field(default_factory=list, max_length=50)` if needed.
- **Per-step ring-1 ring-red-300 highlighting** (UI-SPEC §"Recipe Step Builder" validation errors) — deferred to plan 04-11. The data-correctness contract is already enforced server-side; this is a UI-polish task.

## Self-Check

- `app/services/recipes.py` exists: FOUND
- `app/routers/recipes.py` exists: FOUND
- `app/main.py` modified (`include_router(recipes_router.router)`): FOUND
- `app/templates/pages/recipes.html` exists: FOUND
- `app/templates/fragments/recipe_list.html` exists: FOUND
- `app/templates/fragments/recipe_row.html` exists: FOUND
- `app/templates/fragments/recipe_form.html` exists: FOUND
- `app/templates/fragments/recipe_step_builder.html` exists: FOUND
- `app/templates/fragments/pour_timeline.html` exists: FOUND
- `app/static/js/alpine-components/recipe-step-builder.js` exists: FOUND
- `app/templates/base.html` modified (script tag): FOUND
- `app/static/js/alpine-components/__init.js` modified (doc reference): FOUND
- `tests/phase_04/test_services_recipes.py` (6 tests, new file): FOUND
- `tests/phase_04/test_routers_recipes.py` (15 tests, replaces Wave-0 stub): FOUND
- Commit `f69a465` (Task 1) in `git log`: FOUND
- Commit `3bfc537` (Task 2) in `git log`: FOUND
- Commit `26b4e10` (Task 3) in `git log`: FOUND
- Container verify `pytest -q tests/phase_04/test_routers_recipes.py tests/phase_04/test_services_recipes.py` returns `21 passed`: FOUND
- Wave-wide regression `pytest -q tests/phase_04/` returns `140 passed, 3 skipped`: FOUND
- Full suite `pytest -q` returns `256 passed, 5 skipped, 10 xfailed`: FOUND

## Self-Check: PASSED

---
*Phase: 04-shared-catalog*
*Plan: 08*
*Completed: 2026-05-19*
