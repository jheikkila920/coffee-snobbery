---
phase: 04-shared-catalog
plan: 03
subsystem: database
tags: [models, sqlalchemy-2.0, alembic, postgres, citext, jsonb, array, gin-index, fk-restrict, check-constraint, wave-2-schema]

# Dependency graph
requires:
  - phase: 00-foundation
    provides: app/models/bag.py (Phase 0 shipped coffee_id as BigInteger NOT NULL with no FK — Plan 04-03 added the FK); app/migrations/versions/0001_initial.py (extensions citext/pg_trgm/unaccent installed, bags table created)
  - phase: 01-middleware
    provides: app/db.py SessionLocal sync session pattern (consumed by model tests)
  - phase: 03-encryption-settings
    provides: app/migrations/versions/p3_api_credentials.py (current head before plan 04-03; p4_shared_catalog sets down_revision="p3_api_credentials")
  - plan: 04-01
    provides: tests/phase_04/conftest.py + Wave-0 stubs (replaced test_models_catalog.py and test_migration.py with real tests); app/services/photos.py reads bags.photo_filename via lazy import (column finally lands here)
provides:
  - app/models/roaster.py — Roaster (CAT-01) Mapped[...] model with CITEXT unique name
  - app/models/flavor_note.py — FlavorNote (CAT-02) Mapped[...] model with CITEXT unique name + 9-value category CHECK
  - app/models/coffee.py — Coffee (CAT-03) Mapped[...] model with ARRAY(BigInteger) advertised_flavor_note_ids + IS NULL OR ... process/roast_level CHECKs
  - app/models/equipment.py — Equipment (CAT-05) Mapped[...] model with 6-value type CHECK + denormalized usage_count
  - app/models/recipe.py — Recipe (CAT-06) Mapped[...] model with JSONB steps + dose/water/temp/grind columns
  - app/models/bag.py MODIFIED — coffee_id now FK to coffees.id with ondelete=RESTRICT + new photo_filename Text NULL column (CAT-08)
  - app/models/__init__.py MODIFIED — re-exports all five new models for Alembic metadata discovery
  - app/migrations/versions/p4_shared_catalog.py — single migration creating 5 tables + GIN index (hand-edited raw SQL) + bag FK + photo_filename column
  - tests/phase_04/test_models_catalog.py — 12 real model integration tests (CITEXT unique, CHECK behavior, ARRAY/JSONB round-trip, FK RESTRICT, photo_filename optional+persists)
  - tests/phase_04/test_migration.py — 3 alembic upgrade/downgrade round-trip tests (idempotent, schema diff, GIN index presence)
  - tests/test_migrations.py UPDATED — replaced inverted Phase 0 guard with Phase 4 FK assertion
affects:
  - 04-04 (roasters CRUD router — imports Roaster model)
  - 04-05 (flavor_notes CRUD router — imports FlavorNote model)
  - 04-06 (coffees CRUD router — imports Coffee model + uses ARRAY GIN index)
  - 04-07 (equipment CRUD router — imports Equipment model)
  - 04-08 (recipes CRUD router — imports Recipe model)
  - 04-09 (bag photo upload — writes bags.photo_filename)
  - 04-10 (photos serving route — reads bags.photo_filename for safe filename resolution)
  - 04-11 (autocomplete + mini-modal — queries flavor_notes via CITEXT unique)
  - phase-05 (brew sessions — Equipment.usage_count increment, Recipe + Coffee FKs)
  - phase-07 (AI recommendations — reads Coffee.advertised_flavor_note_ids via GIN-served queries)
  - phase-08 (orphan sweep — bags.photo_filename is the canonical "referenced files" set)

# Tech tracking
tech-stack:
  added:
    - "Postgres ARRAY(BigInteger) via sqlalchemy.dialects.postgresql.ARRAY — first use in the project (coffees.advertised_flavor_note_ids)"
    - "JSONB column via sqlalchemy.dialects.postgresql.JSONB — first ORM-model use (Phase 0's ai_recommendations.response_json used JSONB but only via the migration; this is the first Mapped[list[dict]] declaration)"
    - "Postgres GIN index — first instance; hand-edited raw op.execute() in the Alembic migration because autogenerate cannot emit USING GIN"
  patterns:
    - "Catalog-model template: from __future__ + standard sqlalchemy imports + CITEXT/TIMESTAMP/ARRAY/JSONB from dialects.postgresql + Identity(always=False) BigInteger PK + created_at/updated_at TIMESTAMP(timezone=True) with server_default=func.now() + archived Boolean with server_default=text('false')"
    - "CHECK-constraint defense-in-depth: DB-side CHECK matches Pydantic schema regex (plan 04-02). Raw SQL INSERT bypassing the schema layer still fails at the DB boundary."
    - "IS NULL OR ... CHECK shape for nullable enum columns — coffees.process and coffees.roast_level use this shape so NULL is universally accepted as 'unknown' while non-null values must be from the locked vocabulary."
    - "Alembic-safe migration: no app.models imports inside the migration body — sa.Column + op.create_table + raw op.execute for GIN. A future model rename does not invalidate the migration."
    - "Per-test clean_catalog fixture: phase_04 model tests own their cleanup (DELETE in FK-respecting order) because the autouse fresh_db is Phase 2-scoped (users/sessions/setup_completed only)."
    - "Alembic round-trip test via alembic.command.upgrade/downgrade driven from a programmatically-built Config — no subprocess required, runs in the same Python process as the rest of pytest."

key-files:
  created:
    - app/models/coffee.py
    - app/models/roaster.py
    - app/models/flavor_note.py
    - app/models/equipment.py
    - app/models/recipe.py
    - app/migrations/versions/p4_shared_catalog.py
  modified:
    - app/models/bag.py — coffee_id FK constraint + photo_filename column
    - app/models/__init__.py — re-export 5 new models in alphabetical order
    - tests/phase_04/test_models_catalog.py — replaced Wave-0 skip stub with 12 real tests
    - tests/phase_04/test_migration.py — replaced Wave-0 skip stub with 3 real round-trip tests
    - tests/test_migrations.py — replaced inverted Phase 0 FK guard (test_bags_coffee_id_has_no_foreign_key) with Phase 4 FK assertion (test_bags_coffee_id_fk_to_coffees_restrict)

key-decisions:
  - "ondelete='SET NULL' on coffees.roaster_id (NOT RESTRICT). Asymmetry with bags.coffee_id is intentional: a coffee may survive a roaster being hard-deleted, but a coffee referenced by any bag must not be hard-deletable."
  - "ondelete='RESTRICT' on bags.coffee_id. DB-side backstop for the archive-only policy in plan 04-04 — if the policy ever slips, RESTRICT fails loudly with IntegrityError rather than silently cascade-deleting bag history."
  - "GIN index on coffees.advertised_flavor_note_ids landed via raw op.execute() — autogenerate cannot emit USING GIN. Documented in the migration body so a future autogenerate run that 'normalizes' the schema does not silently drop the index."
  - "IS NULL OR ... CHECK shape on coffees.process and coffees.roast_level. Both columns are nullable (household may not know the process for an old bag); a non-null value must be from the locked vocabulary, but NULL is the universal 'unknown' sentinel. This is documented in 04-RESEARCH.md and locked in both the model and the migration."
  - "coffees.name is CITEXT but NOT unique. Different roasters legitimately sell coffees with the same name ('Ethiopia Yirgacheffe' from N roasters). De-facto identity is (name, roaster_id); plan 04-04's schema-layer duplicate check enforces that pair at the application boundary."
  - "JSONB chosen over a normalized recipe_steps table for Recipe.steps. Read-mostly, write-rare, ordered list with per-step free-form fields. Plan 04-08's 'edit step 3' UX is dramatically simpler with JSONB; normalization buys nothing at household scale."
  - "Recipe steps JSON-Schema validation is NOT enforced at the DB column (no CHECK with jsonb_typeof()). Per-step shape is enforced by the Pydantic schema in plan 04-02. DB-side validation would duplicate Pydantic and lock the shape too early for Phase 5+ extensions."

patterns-established:
  - "Catalog-model template (Roaster/FlavorNote/Coffee/Equipment/Recipe): BigInteger Identity PK, CITEXT for case-insensitive name uniqueness where it applies, Text columns for free-form prose, archived Boolean for soft-delete (server_default false), created_at/updated_at TIMESTAMP(timezone=True) with server_default=func.now(). CHECK constraints carry deterministic names (table_column_check) so future migrations can target them."
  - "Hand-edit raw op.execute() in Alembic migrations for non-autogenerable DDL (GIN/GIST/BRIN indexes, partial unique indexes already established in 0001_initial via postgresql_where, future CREATE EXTENSION calls). Document the autogenerate gap in the migration body so the hand-edit survives the next normalization pass."
  - "Per-phase test cleanup fixture (clean_catalog) — Phase 4 model tests own their reset because the autouse fresh_db in tests/conftest.py is Phase 2-scoped. Future phases that add tables will add their own equivalent."
  - "Alembic-driven round-trip test: import alembic.command + alembic.config.Config, run upgrade/downgrade in-process. No subprocess overhead, integrates cleanly with pytest skip-on-no-DB pattern. Future phase migrations should reuse this shape for their own round-trip tests."

requirements-completed:
  - CAT-01
  - CAT-02
  - CAT-03
  - CAT-05
  - CAT-06
  - CAT-08

# Metrics
duration: 70min
completed: 2026-05-19
---

# Phase 4 Plan 03: Shared Catalog Models + Migration Summary

**Five new SQLAlchemy 2.0 Mapped[...] catalog models (Roaster/FlavorNote/Coffee/Equipment/Recipe) + bags FK to coffees with ON DELETE RESTRICT + bags.photo_filename column, landed via a single `p4_shared_catalog` Alembic migration that also creates the hand-edited GIN index on `coffees.advertised_flavor_note_ids`.**

## Performance

- **Duration:** ~70 minutes
- **Started:** 2026-05-19T00:04:00Z
- **Completed:** 2026-05-19T01:14:00Z
- **Tasks:** 2
- **Files created:** 8 (5 models + 1 migration + 2 test modules effectively rewritten)
- **Files modified:** 4 (bag.py, __init__.py, test_models_catalog.py + test_migration.py replaced, tests/test_migrations.py FK guard inverted)

## Accomplishments

- **Five new catalog models** ship with the locked schema shape from 04-PATTERNS.md: `Roaster` (CITEXT unique name), `FlavorNote` (CITEXT unique name + 9-value category CHECK), `Coffee` (CITEXT non-unique name, ARRAY(BigInteger) advertised_flavor_note_ids, IS NULL OR ... CHECKs on process and roast_level, FK to roasters with SET NULL), `Equipment` (6-value type CHECK + denormalized usage_count defaulting to 0), `Recipe` (JSONB steps + dose/water/temp/grind columns).
- **bags.coffee_id FK landed** with `ondelete='RESTRICT'` per CAT-04's deferred promise from Phase 0 — once a household member has a bag of a coffee, hard-deleting the coffee fails loudly. Combined with the archive-only policy in plan 04-04, coffees are never hard-deleted in practice; RESTRICT is the DB-side backstop.
- **bags.photo_filename column** added (CAT-08 storage). The photos pipeline shipped in plan 04-01 reads from this column via its lazy `from app.models.bag import Bag` inside `sweep_orphans` — no further service-layer change required.
- **Single Alembic migration** `p4_shared_catalog` (down_revision = `p3_api_credentials`) creates everything in FK-correct order and includes the hand-edited `CREATE INDEX ... USING GIN` raw SQL for `coffees.advertised_flavor_note_ids` (autogenerate cannot emit `USING GIN` — Pitfall 3 in 04-RESEARCH.md). Round-trip upgrade → downgrade → upgrade is clean.
- **15 real tests** replace the two Wave-0 skip stubs. 12 model integration tests cover CITEXT case-insensitive unique violations, CHECK constraint rejection of out-of-vocabulary values (and acceptance of NULL where the constraint is `IS NULL OR ...`), ARRAY and JSONB round-trip preserving order, FK RESTRICT raising IntegrityError on coffee delete, and the photo_filename optional + persists pair. 3 migration tests cover `alembic upgrade head` idempotency, downgrade -1 + upgrade head round-trip with `to_regclass('public.coffees')` introspection, and the `using gin` index-definition assertion.
- **Full test suite green:** `176 passed, 10 skipped, 10 xfailed` (was 163 passed before this plan). The +13 net is 12 new model tests + 3 new migration tests minus the 2 Wave-0 stubs that no longer run.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement 5 new Mapped models + modify bag.py + register in __init__.py** — `1b11477` (feat)
2. **Task 2: Author p4_shared_catalog migration + 12 model tests + 3 alembic round-trip tests + fix inverted Phase 0 FK guard** — `da970e0` (feat)

## Files Created/Modified

### Models (created)
- `app/models/roaster.py` — `Roaster` class. CITEXT unique `name`, optional Text `location` / `website` / `notes`, `archived` Boolean (server_default false).
- `app/models/flavor_note.py` — `FlavorNote` class. CITEXT unique `name`, `category` Text with `flavor_notes_category_check` CHECK (9 values: fruit/floral/sweet/chocolate/nutty/spice/savory/fermented/other).
- `app/models/coffee.py` — `Coffee` class. CITEXT non-unique `name`, nullable FK `roaster_id` (SET NULL), nullable enum-like Text columns (country/origin/process/roast_level/varietal), `advertised_flavor_note_ids: list[int]` via ARRAY(BigInteger) with `'{}'::bigint[]` server_default, IS NULL OR ... CHECK constraints on `process` and `roast_level`. GIN index is migration-only (not in __table_args__).
- `app/models/equipment.py` — `Equipment` class. `type` Text + `equipment_type_check` CHECK (6 values), `brand` + `model` NOT NULL Text, `usage_count` Integer (server_default 0), `archived` Boolean. `ix_equipment_type` index in `__table_args__`.
- `app/models/recipe.py` — `Recipe` class. `name` + `dose_grams` + `water_grams` + `water_temp_c` NOT NULL, `grind_setting` Text (server_default ""), `steps` JSONB (server_default `'[]'::jsonb`). No CHECK on steps shape — Pydantic schema (plan 04-02) is the authority.

### Models (modified)
- `app/models/bag.py` — `coffee_id` is now `ForeignKey('coffees.id', ondelete='RESTRICT')`. New `photo_filename: Mapped[str | None] = mapped_column(Text, nullable=True)` column. Docstring updated to note Phase 4 landed the FK + CAT-08 column.
- `app/models/__init__.py` — Re-exports the 5 new models (alphabetical insertion between `Bag` and `Base`). `__all__` extended.

### Migration (created)
- `app/migrations/versions/p4_shared_catalog.py` — `revision = "p4_shared_catalog"`, `down_revision = "p3_api_credentials"`. Upgrade creates 5 tables in FK order, hand-edits the GIN index via raw `op.execute()`, adds `bags.photo_filename` column, creates `fk_bags_coffee_id` FK with ondelete='RESTRICT'. Downgrade reverses in strict reverse order; the GIN index drop uses `DROP INDEX IF EXISTS` for idempotency. Extensions (citext/pg_trgm/unaccent) are NOT dropped — they were installed in 0001_initial and are cluster-shared.

### Tests (modified — Wave-0 stub replacement)
- `tests/phase_04/test_models_catalog.py` — Replaced the 1-line `pytest.skip` stub with 12 real integration tests. Adds a `clean_catalog` fixture that wipes Phase 4 catalog tables in FK-respecting order. Each test uses `_require_postgres` + `_require_p4_migration_applied` for clean skip behavior on unit-only runs.
- `tests/phase_04/test_migration.py` — Replaced the 1-line `pytest.skip` stub with 3 real alembic round-trip tests using `alembic.command.upgrade/downgrade` driven from a programmatically-built `alembic.config.Config` rooted at the repo's `alembic.ini`.

### Tests (modified — Phase 0 guard inversion)
- `tests/test_migrations.py` — Renamed `test_bags_coffee_id_has_no_foreign_key` → `test_bags_coffee_id_fk_to_coffees_restrict`. The previous test's own docstring acknowledged the inversion would land in Phase 4; this commit is that landing. New assertion checks the FK exists by name (`fk_bags_coffee_id`) and has `delete_rule = 'RESTRICT'` via `information_schema.referential_constraints`.

## Decisions Made

- **Asymmetric FK ondelete on the coffee ↔ roaster ↔ bag chain.** `coffees.roaster_id` is SET NULL (a coffee outlives a hard-deleted roaster); `bags.coffee_id` is RESTRICT (a coffee referenced by a bag cannot be hard-deleted). Both are documented in 04-PATTERNS.md and now in the model docstrings.
- **GIN index hand-edited via raw `op.execute()`** rather than declared in `__table_args__`. SQLAlchemy 2.0 + Alembic autogenerate cannot emit `USING GIN`. Documented in both the Coffee model docstring and the migration body so a future autogenerate-driven "normalization" pass doesn't silently drop the index.
- **IS NULL OR ... CHECK shape for nullable enum columns.** `coffees.process` and `coffees.roast_level` are nullable because the household may not always know the process; a non-null value must be from the locked 6-value vocabulary, but `NULL` is the universal "unknown" sentinel. This avoids the alternative of seeding an `'unknown'` literal that would compete with `NULL` for the same semantics.
- **`coffees.name` is CITEXT but NOT unique.** Different roasters legitimately sell coffees with the same name. Application-layer de-facto identity is `(name, roaster_id)` and plan 04-04's schema-layer duplicate check enforces that pair. Locking unique on `name` alone would force the application to invent decorator suffixes like "Ethiopia Yirgacheffe (Onyx)".
- **JSONB chosen over a normalized `recipe_steps` table.** Steps are an ordered list with per-step free-form fields (label, water_grams, time_seconds, optional notes). At household scale, normalization adds join cost and complicates the plan-04-08 "edit step 3" UX without any analytical benefit — recipes are read-mostly and write-rare.
- **Per-test `clean_catalog` fixture, not autouse-extended cleanup.** The autouse `fresh_db` in `tests/conftest.py` is Phase 2-scoped (users/sessions/setup_completed only); extending it to Phase 4 catalog tables would impose per-test cost on the entire suite. Phase 4 model tests opt in to cleanup via the fixture; non-model tests in `tests/phase_04/` (autocomplete, routers) don't pay the cost.
- **Alembic round-trip tests use `alembic.command` in-process** rather than `subprocess.run(['alembic', ...])`. Same effect, no subprocess overhead, no PATH/working-directory ambiguity, no flaky stderr-vs-stdout parsing. The `Config` object is built from the repo's `alembic.ini` path so the test honors the same env-var bootstrap as the rest of the suite.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Inverted Phase 0 FK guard in `tests/test_migrations.py`**

- **Found during:** Task 2 (running the full suite after wiring up Task 2's verification)
- **Issue:** `tests/test_migrations.py::test_bags_coffee_id_has_no_foreign_key` asserts that `bags.coffee_id` has zero FK constraints — correct at Phase 0, intentionally inverted by plan 04-03 which adds the FK as a primary deliverable. Test was failing as soon as `alembic upgrade head` brought the DB to `p4_shared_catalog`.
- **Fix:** Replaced the test with `test_bags_coffee_id_fk_to_coffees_restrict`. New assertion checks the FK exists by name (`fk_bags_coffee_id`) and has `delete_rule = 'RESTRICT'` via `information_schema.referential_constraints`. The previous test's own docstring acknowledged this inversion would land in Phase 4 ("If a future planner accidentally adds the FK here, this assertion guards against the regression") — plan 04-03 is the legitimate, non-accidental landing.
- **Files modified:** `tests/test_migrations.py` (committed in `da970e0` alongside Task 2)
- **Verification:** `docker exec coffee-snobbery python -m pytest -q tests/test_migrations.py` → `14 passed`. Full suite: `176 passed, 10 skipped, 10 xfailed` (was `163 passed, 10 skipped, 10 xfailed` before this plan, with the FK-guard test failing once Task 2 ran).

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug — stale Phase 0 regression guard that plan 04-03 was always going to retire).

**Impact on plan:** Zero scope creep. The deviation is a single test rename + assertion inversion in a file plan 04-03 already touched implicitly (`alembic upgrade head` runs the whole migration chain, so any test asserting Phase 0 schema invariants is by construction this plan's responsibility to keep accurate). Documented in the new test's docstring so future plans don't re-add the inverted guard.

## Issues Encountered

- **Alembic 1.18 deprecation warning for `path_separator`** (pre-existing, not introduced by plan 04-03). `app/migrations/env.py` triggers a `DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path. Consider adding path_separator=os to Alembic config.` Fix is to add `path_separator = os` next to the existing `version_path_separator = os` line in `alembic.ini`. Out of scope for this plan; logged as a deferred item.
- **Docker container is image-baked, not bind-mounted.** Verification required `docker cp` of each modified file into the running `coffee-snobbery` container before running `alembic upgrade head` / `pytest`. Works fine for development; the production deploy path (`docker compose build && docker compose up -d`) bakes the new files into a fresh image. No code change required.

## User Setup Required

None — this plan ships schema + models only. No new env vars, no external service configuration.

## Verification

Plan-stated verify commands + `<done>` criteria:

- **Task 1** verify: `docker compose exec coffee-snobbery python -c "from app.models import Coffee, Roaster, FlavorNote, Equipment, Recipe, Bag; from app.models.bag import Bag as B; assert hasattr(B, 'photo_filename'); print('ok')"` → `ok` ✓
- **Task 1** done criteria grep counts:
  - `grep -c "ForeignKey..coffees.id...ondelete=.RESTRICT" app/models/bag.py` → `1` ✓
  - `grep -c "ARRAY(BigInteger)" app/models/coffee.py` → `1` ✓
  - `grep -c "JSONB" app/models/recipe.py` → `5` ✓ (≥1 required)
  - `grep -c "CheckConstraint" app/models/coffee.py` → `3` ✓ (≥2 required)
  - `grep -c "Coffee\|Roaster\|FlavorNote\|Equipment\|Recipe" app/models/__init__.py` → `10` ✓ (≥10 required: 5 imports + 5 in __all__)
- **Task 2** verify: `docker compose exec coffee-snobbery alembic upgrade head && docker compose exec coffee-snobbery pytest -q tests/phase_04/test_models_catalog.py tests/phase_04/test_migration.py -x` → `alembic` reaches `p4_shared_catalog (head)`; pytest exits 0 with `15 passed` ✓
- **Task 2** done criteria DB introspection:
  - `\dt` → all 5 tables present (`roasters`, `flavor_notes`, `coffees`, `equipment`, `recipes`) ✓
  - `SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_coffees_advertised_flavor_note_ids'` → `CREATE INDEX ... ON public.coffees USING gin (advertised_flavor_note_ids)` ✓
  - `\d bags` → `fk_bags_coffee_id FOREIGN KEY (coffee_id) REFERENCES coffees(id) ON DELETE RESTRICT` ✓
  - `\d bags` → `photo_filename | text | nullable` ✓

Full suite: `docker compose exec coffee-snobbery python -m pytest -q` → `176 passed, 10 skipped, 10 xfailed, 34 warnings in 9.69s`. No regressions traced to this plan; the single FK-guard inversion (Deviation 1) was the only test surface that needed updating.

## Threat Coverage

| Threat | Component | Mitigation | Test |
|--------|-----------|------------|------|
| Tampering (data integrity) | `coffees.process`, `coffees.roast_level`, `flavor_notes.category`, `equipment.type` | DB-side CHECK constraints (defense-in-depth alongside Pydantic regex in plan 04-02) | `test_flavor_note_category_check`, `test_coffee_process_check_allows_null`, `test_coffee_process_check_rejects_unknown`, `test_equipment_type_check` |
| Cascade destruction | `bags.coffee_id` | `ondelete='RESTRICT'` — hard-delete of a referenced coffee fails loudly with IntegrityError. DB-side backstop for the archive-only policy in plan 04-04. | `test_bag_coffee_fk_restrict`, `tests/test_migrations.py::test_bags_coffee_id_fk_to_coffees_restrict` |

## Next Plan Readiness

- **Plan 04-04 (roasters CRUD router)** ready — `from app.models import Roaster` works, CITEXT unique violation surfaces correctly for the duplicate-name error path.
- **Plan 04-05 (flavor_notes CRUD router)** ready — `from app.models import FlavorNote` works, category CHECK is in place for the form-validation defense layer.
- **Plan 04-06 (coffees CRUD router)** ready — `from app.models import Coffee` works, GIN index is live so the "coffees that mention these flavors" query in the autocomplete feature is sub-second from day one. The schema-layer `(name, roaster_id)` uniqueness check (plan 04-04 design note) is plan 04-06's responsibility.
- **Plan 04-07 (equipment CRUD router)** ready — `from app.models import Equipment` works, `usage_count` denormalization is in place for Phase 5's increment logic.
- **Plan 04-08 (recipes CRUD router)** ready — `from app.models import Recipe` works, JSONB `steps` is the read/write target for the "edit step N" UX.
- **Plan 04-09 (bag photo upload)** ready — `bags.photo_filename` exists; the upload route can `INSERT ... RETURNING photo_filename` or `UPDATE ... SET photo_filename = :basename`.
- **Plan 04-10 (photos serving route)** ready — `bags.photo_filename` exists for the safe-filename resolution step.
- **Phase 8 nightly orphan sweep** ready — `app/services/photos.py::sweep_orphans` already lazy-imports `Bag`; with `photo_filename` now landed, the wrapper's one-line `select(Bag.photo_filename)` query is live.

## Self-Check: PASSED

- `app/models/roaster.py` exists: FOUND
- `app/models/flavor_note.py` exists: FOUND
- `app/models/coffee.py` exists: FOUND
- `app/models/equipment.py` exists: FOUND
- `app/models/recipe.py` exists: FOUND
- `app/migrations/versions/p4_shared_catalog.py` exists: FOUND
- `app/models/bag.py` exists with `photo_filename` and FK: FOUND
- `app/models/__init__.py` re-exports 5 new models: FOUND
- `tests/phase_04/test_models_catalog.py` 12 real tests: FOUND (15 passed across both test files)
- `tests/phase_04/test_migration.py` 3 real tests: FOUND
- `tests/test_migrations.py` FK guard inverted: FOUND
- Commit `1b11477` (Task 1) in `git log`: FOUND
- Commit `da970e0` (Task 2) in `git log`: FOUND
- Container verify `alembic current` returns `p4_shared_catalog (head)`: FOUND
- Container verify `pytest -q tests/phase_04/test_models_catalog.py tests/phase_04/test_migration.py` returns `15 passed`: FOUND
- Full suite `pytest -q` returns `176 passed, 10 skipped, 10 xfailed`: FOUND

---
*Phase: 04-shared-catalog*
*Plan: 03*
*Completed: 2026-05-19*
