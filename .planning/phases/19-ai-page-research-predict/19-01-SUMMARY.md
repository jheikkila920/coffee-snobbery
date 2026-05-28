---
phase: 19-ai-page-research-predict
plan: "01"
subsystem: ai-schemas-models-migration
tags: [ai, pydantic-schemas, sqlalchemy-models, alembic, sse, tdd]
dependency_graph:
  requires: [p16_cafe_logs migration, app/models/base.py, app/services/ai_schemas.py]
  provides: [AICoffeeResearchCache model, AIRatingPrediction model, p19_ai_research_predict migration, CoffeeResearchSchema, RatingPredictionSchema, BrewImproveSchema, PreferenceProfileProseSchema, RecipeSuggestionSchema D-11]
  affects: [app/services/ai_service.py, app/templates/fragments/home/ai_rec_hero.html, tests/test_migrations.py]
tech_stack:
  added: [sse-starlette>=3.4,<4]
  patterns: [Pydantic v2 extra=forbid prompt-injection defence (T-07-02 reused), Alembic hand-written DDL migration, typed Mapped[] SQLAlchemy 2.0 columns]
key_files:
  created:
    - app/services/ai_schemas.py (5 new schemas added)
    - app/models/ai_coffee_research_cache.py
    - app/models/ai_rating_prediction.py
    - app/migrations/versions/p19_ai_research_predict.py
    - tests/services/test_ai_research.py
    - tests/services/test_preference_prose.py
    - tests/services/test_brew_improve.py
  modified:
    - app/models/__init__.py (registered 2 new models)
    - app/services/ai_service.py (removed no_match from suggest_recipe)
    - app/templates/fragments/home/ai_rec_hero.html (replaced rs.no_match with recipe_id is none)
    - requirements.txt (sse-starlette pin)
    - tests/test_migrations.py (3 new Phase 19 introspection tests)
decisions:
  - "RecipeSuggestionSchema.no_match removed (D-11); ratio/temp_c/grind_hint now required; suggest_recipe given placeholder defaults pending plan 19-02 LLM wiring"
  - "ai_coffee_research_cache uses Text PK (not BigInt) because cache_key is the natural lookup key — avoids a secondary unique index"
  - "cited_sources JSONB column defaults to '[]'::jsonb server-side to avoid NOT NULL violation on cache writes before sources are extracted"
  - "Migration uses ON CONFLICT (key) DO NOTHING for app_settings INSERTs so re-running upgrade head is idempotent"
metrics:
  duration: "~35 minutes"
  completed: "2026-05-28"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 19 Plan 01: AI Schemas + Models + Migration Summary

Two new DB tables, five new/modified Pydantic schemas, one Alembic migration, and Wave 0 test scaffolding for the Phase 19 AI research/predict feature set — using `sse-starlette>=3.4,<4` as the new SSE library.

## What Was Built

### Task 1: New + modified AI schemas (D-02/D-11/AIX-01/AIX-09/AIX-12)

- **`RecipeSuggestionSchema`** (D-11): removed `no_match` field; added required `ratio: str`, `temp_c: int`, `grind_hint: str`. Constructing with `no_match=True` now raises `ValidationError` (extra=forbid).
- **`CoffeeResearchSchema`** (AIX-01): `coffee_name`, optional `roaster_name/origin/process/roast_level`, `tasting_notes: list[str]`, `buy_url`, `sources`, `summary_prose`. `extra=forbid` (T-19-01).
- **`RatingPredictionSchema`** (D-02): `predicted_low` + `predicted_high` (both ge=0, le=5), `confidence: Literal["Low","Medium","High"]`, `reasoning`. No single-number form.
- **`BrewParameterChangeSchema`** (AIX-12): `parameter: Literal["grind","ratio","temp_c","brewer","recipe"]`, `suggested_value`, `rationale`. `extra=forbid`.
- **`BrewImproveSchema`** (AIX-12): `summary_prose`, `unchanged_parameters: list[str]`, `next_try: list[BrewParameterChangeSchema]`. `extra=forbid`.
- **`PreferenceProfileProseSchema`** (AIX-09): `summary_prose` only. `extra=forbid`.
- Pinned `sse-starlette>=3.4,<4` in `requirements.txt`.

### Task 2: New models + migration (D-06/D-07/D-08)

- **`AICoffeeResearchCache`**: Text PK `cache_key`, JSONB `response_json` + `cited_sources`, TIMESTAMPTZ `expires_at`, B-tree index on `expires_at`.
- **`AIRatingPrediction`**: BigInt Identity PK, `user_id` FK (CASCADE), `research_cache_key` FK (CASCADE), `Numeric(3,2)` `predicted_low`/`predicted_high`, Text `confidence`/`reasoning`/`input_signature`, TIMESTAMPTZ `expires_at`, UNIQUE(`user_id`, `research_cache_key`).
- Migration `p19_ai_research_predict` (down_revision=`p16_cafe_logs`): creates both tables + index + two `app_settings` quota rows (`ai.research_daily_quota=20`, `ai.improve_brew_daily_quota=20`).

### Task 3: Wave 0 test scaffolds

- `tests/services/test_ai_research.py`: schema validation tests + 7 skipped placeholders (19-03).
- `tests/services/test_preference_prose.py`: schema validation test.
- `tests/services/test_brew_improve.py`: schema validation test + 1 skipped placeholder (19-04).
- `tests/test_migrations.py`: extended with 3 Phase 19 introspection tests (table columns, UNIQUE constraint, quota seed rows).

**Final test result:** 23 passed, 8 skipped (all skips reference owning downstream plan).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `suggest_recipe` in `ai_service.py` to remove `no_match` usage**
- **Found during:** Task 1 (removing `no_match` from schema breaks the function that constructs it)
- **Issue:** `ai_service.py:suggest_recipe()` passed `no_match=True/False` to `RecipeSuggestionSchema` — immediate `ValidationError` at runtime after the schema change.
- **Fix:** Replaced `no_match` with placeholder `ratio="1:15"`, `temp_c=94`, `grind_hint="medium-fine"`. Plan 19-02 will wire these from the LLM structured output.
- **Files modified:** `app/services/ai_service.py`
- **Commit:** ef65c0c

**2. [Rule 1 - Bug] Fixed `ai_rec_hero.html` template to remove `rs.no_match` check**
- **Found during:** Task 1 (template access on non-existent field)
- **Issue:** Jinja template used `{% if rs.no_match %}` which would silently be falsy (attribute absent), rendering the `{% else %}` branch even when `recipe_id is None`, printing `None` as the recipe name.
- **Fix:** Changed to `{% if rs.recipe_id is none %}` which correctly detects the no-match case.
- **Files modified:** `app/templates/fragments/home/ai_rec_hero.html`
- **Commit:** ef65c0c

**3. [Rule 3 - Blocking] Created `docker-compose.override.yml` for local build**
- **Found during:** Task 1 verification
- **Issue:** `docker-compose.yml` uses a GHCR image tag; `docker compose build` was a no-op without the dev override.
- **Fix:** Copied `docker-compose.override.yml.example` to `docker-compose.override.yml` (gitignored) to enable local builds.
- **Files modified:** `docker-compose.override.yml` (not committed — gitignored)

Note: `test_suggest_recipe_picks_highest_rated` and `test_suggest_recipe_no_match` in `tests/services/test_ai_service.py` now fail (they assert `result.no_match is False/True`). Per the plan, `test_ai_service.py` is explicitly NOT modified in plan 19-01; plan 19-02 owns those fixes.

## Known Stubs

- `suggest_recipe()` returns placeholder `ratio="1:15"`, `temp_c=94`, `grind_hint="medium-fine"` for both the match and no-match cases. Plan 19-02 will wire the LLM to populate these from the `structure_output` tool response.

## Threat Flags

No new network endpoints or auth paths introduced in this plan. The two new tables are created but not yet accessible via any route (routes added in plan 19-03). The `extra=forbid` prompt-injection defence (T-19-01) is applied to all 5 new schemas as required by the threat model.

## Self-Check: PASSED

Files exist:
- `app/services/ai_schemas.py` — FOUND
- `app/models/ai_coffee_research_cache.py` — FOUND
- `app/models/ai_rating_prediction.py` — FOUND
- `app/migrations/versions/p19_ai_research_predict.py` — FOUND
- `tests/services/test_ai_research.py` — FOUND
- `tests/services/test_preference_prose.py` — FOUND
- `tests/services/test_brew_improve.py` — FOUND

Commits exist:
- ef65c0c: feat(19-01): add 5 new AI schemas; remove no_match from RecipeSuggestionSchema
- a991834: feat(19-01): add AICoffeeResearchCache + AIRatingPrediction models and migration
- e394f07: test(19-01): extend test_migrations.py with Phase 19 table + quota assertions
