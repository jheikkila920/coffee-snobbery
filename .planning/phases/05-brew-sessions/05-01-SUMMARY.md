---
phase: 05-brew-sessions
plan: 01
subsystem: database
tags: [sqlalchemy, alembic, postgres, pydantic, generated-column, array, jsonb]

# Dependency graph
requires:
  - phase: 04-shared-catalog
    provides: coffees / bags / recipes / equipment tables + GIN/raw-op.execute migration precedent
  - phase: 02-auth
    provides: users table (FK target for brew_sessions.user_id and brew_drafts.user_id)
provides:
  - "BrewSession ORM model (first per-user table) with GENERATED extraction_yield_pct, ARRAY observed notes, FK ondelete asymmetry"
  - "BrewDraft ORM model (one row per user, JSONB payload) — localStorage server backstop"
  - "BrewSessionCreate/Update + BrewCsvRow Pydantic schemas (Decimal rating, extra=forbid, SEC-06 ranges)"
  - "p5_brew_sessions Alembic migration (brew_sessions + brew_drafts, GENERATED EY, GIN + B-tree indexes)"
  - "seven brew.* audit-event constants in app/events.py"
  - "Wave 0 schema test scaffolding (tests/services/test_brew_schema.py)"
affects: [brew-services, brew-router, brew-csv-import, brew-prefill, brew-drafts, analytics, ai-recommendations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Postgres GENERATED column via SQLAlchemy Computed(expr, persisted=True) on the model + raw ALTER TABLE in the migration (mirrors the p4 GIN raw-op.execute precedent for DDL autogenerate cannot emit)"
    - "Decimal (not float) Pydantic field with multiple_of=Decimal('0.25') for exact quarter-step rating validation"
    - "FK ondelete asymmetry: RESTRICT for ownership/history (user_id, coffee_id), SET NULL for optional refs, CASCADE only for the per-user draft row"

key-files:
  created:
    - app/models/brew_session.py
    - app/models/brew_draft.py
    - app/schemas/brew_session.py
    - app/schemas/brew_csv.py
    - app/migrations/versions/p5_brew_sessions.py
    - tests/services/test_brew_schema.py
  modified:
    - app/models/__init__.py
    - app/schemas/__init__.py
    - app/events.py
    - tests/phase_04/test_migration.py

key-decisions:
  - "tds_pct stored as WHOLE PERCENT (1.35 = 1.35%); GENERATED EY expression divides tds by 100 and re-multiplies the ratio by 100: (yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100 → whole-percent EY"
  - "user_id FK uses ondelete=RESTRICT (not CASCADE) — brew history never silently vanishes on a user delete; Phase 9 admin user-delete must handle logs explicitly"

patterns-established:
  - "GENERATED column: declare Computed(persisted=True) on the model for ORM/autogenerate visibility; hand-write GENERATED ALWAYS AS (...) STORED in the migration so the clause survives (Pitfall 1)"
  - "extraction_yield_pct (and user_id) deliberately absent from every writable schema — mass-assignment + render-only defense (T-05-01)"
  - "DESC composite B-tree indexes emitted via raw op.execute to carry the sort direction; GIN via raw op.execute (autogenerate cannot emit USING GIN)"

requirements-completed: [BREW-01, BREW-04, MOB-05]

# Metrics
duration: ~12min
completed: 2026-05-20
---

# Phase 5 Plan 01: Brew Sessions Data Foundation Summary

**brew_sessions (first per-user table) with a Postgres GENERATED whole-percent extraction_yield_pct, ARRAY observed flavor notes, and FK ondelete asymmetry; brew_drafts server backstop; Decimal-rating Pydantic schemas; the additive p5 migration; and Wave 0 schema tests — all green in-container.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-20T01:36Z
- **Completed:** 2026-05-20T01:48Z
- **Tasks:** 4 of 4 (Task 0 was a pre-resolved decision gate)
- **Files modified:** 10 (6 created, 4 modified)

## Accomplishments

- `BrewSession` model: the app's first per-user table, with a GENERATED `extraction_yield_pct` (whole-percent EY, NULL-propagating), `flavor_note_ids_observed` BIGINT[], FK ondelete asymmetry (user_id/coffee_id RESTRICT; bag/recipe/equipment SET NULL), and two DESC composite B-tree indexes.
- `BrewDraft` model: one row per user (unique user_id, CASCADE), JSONB payload — the iOS-ITP server backstop for the brew form.
- `BrewSessionCreate`/`BrewSessionUpdate` + `BrewCsvRow` schemas: Decimal rating with `multiple_of=0.25`, full SEC-06 numeric ranges, `extra="forbid"`; EY and user_id deliberately omitted (mass-assignment defense).
- `p5_brew_sessions` migration: creates both tables, hand-writes the `GENERATED ALWAYS AS (...) STORED` clause, adds GIN + two B-tree indexes via raw SQL, no UNIQUE on the dedup key; complete idempotent downgrade. Applies cleanly from the p4 head.
- Seven `brew.*` audit-event constants; both models re-exported for Alembic autogenerate.
- All five Wave 0 schema tests pass in-container (EY generated = 22.50, NULL propagation, EY-not-writable, ARRAY round-trip, Decimal steps).

## Task Commits

1. **Task 1: Wave 0 test scaffolding + pytest in container** — `8b6cfd8` (test) [TDD RED]
2. **Task 2: BrewSession + BrewDraft models, __init__ re-export, brew events** — `a13c4b2` (feat) [TDD GREEN]
3. **Task 3: Pydantic schemas (brew_session + brew_csv)** — `ac1d21c` (feat) [TDD GREEN]
4. **Task 4: Alembic migration + GENERATED EY hand-edit + indexes** — `c396a75` (feat, includes Rule 1 test fix)

_TDD plan-level gate satisfied: a `test(...)` commit (8b6cfd8, RED) precedes the `feat(...)` commits (GREEN)._

## Files Created/Modified

- `app/models/brew_session.py` — BrewSession ORM model; Computed EY, ARRAY observed notes, FK ondelete asymmetry, B-tree indexes
- `app/models/brew_draft.py` — BrewDraft ORM model; unique user_id CASCADE, JSONB payload
- `app/schemas/brew_session.py` — BrewSessionCreate/Update; Decimal rating, extra=forbid, SEC-06 ranges
- `app/schemas/brew_csv.py` — BrewCsvRow per-row import schema mirroring StepSchema
- `app/migrations/versions/p5_brew_sessions.py` — additive migration; GENERATED EY, GIN + B-tree, both tables
- `tests/services/test_brew_schema.py` — Wave 0 schema tests (BREW-01, BREW-04)
- `app/models/__init__.py` — re-export BrewSession, BrewDraft (Alembic autogenerate visibility)
- `app/schemas/__init__.py` — re-export the three new schemas (codebase convention)
- `app/events.py` — seven brew.* constants + __all__
- `tests/phase_04/test_migration.py` — stabilized p4 downgrade round-trip test (Rule 1 fix)

## Decisions Made

- **tds_pct unit (Task 0, pre-resolved):** stored as a WHOLE PERCENT (1.35 = 1.35%). The GENERATED expression is `(yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100`, producing a whole-percent EY. Verified in the live DB: `generated always as ((yield_grams_actual * tds_pct / 100.0 / dose_grams_actual * 100::numeric)) stored`; test asserts dose=15/yield=250/tds=1.35 → EY = 22.50.
- **user_id ondelete (Task 0, pre-resolved):** RESTRICT, not CASCADE. Brew history must never silently vanish on a user delete; Phase 9 admin user-delete must explicitly handle a user's logs first.
- **Re-export new schemas in `app/schemas/__init__.py`:** not listed in the plan's `files_modified` but matches the established re-export convention (Rule 2 consistency); lets downstream Phase 5 plans `from app.schemas import BrewSessionCreate`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stabilized the p4 downgrade round-trip test against a moving head**
- **Found during:** Task 4 (migration apply + full-suite verification)
- **Issue:** `tests/phase_04/test_migration.py::test_alembic_downgrade_p4_then_upgrade` did `alembic downgrade -1` and asserted the `coffees` table was dropped. That assumed p4 was the head. Adding p5 on top of p4 made `-1` revert only p5, leaving `coffees` present → the assertion failed.
- **Fix:** Changed the downgrade target from the moving `-1` to the explicit revision below p4 (`p3_api_credentials`), preserving the test's intent (downgrade past p4 drops coffees, re-upgrade restores them) and making it stable against future migrations stacked on p4.
- **Files modified:** tests/phase_04/test_migration.py
- **Verification:** That test (and the other two in the file) pass; full suite green (321 passed, 0 failed). The fix also proves p5's own downgrade is clean (it ran p5.downgrade → p4.downgrade → upgrade head).
- **Committed in:** c396a75 (Task 4 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix was necessary for a green suite and is strictly a test-stability improvement; no production-code or scope change. Adding the schema re-export is a convention-consistency choice, not a deviation requiring a rule.

## Issues Encountered

- **Container test-tree cruft:** the documented `docker compose cp tests/ coffee-snobbery:/app/tests/` nests into `/app/tests/tests/`, leaving a stale duplicated copy of the Phase 4 suite (predating commit e37cdf3). It surfaced one spurious failure during the full-suite run. Removed `/app/tests/tests` (as root) to restore a clean baseline. Not a code issue; a test-iteration artifact of the cp idiom. For single-file iteration, `docker compose cp <file> coffee-snobbery:/app/<file>` is the safe form.
- **`alembic check` reports benign drift:** it wants to "remove" the raw GIN index `ix_brew_sessions_flavor_note_ids_observed` — identical to the pre-existing benign signal for `ix_coffees_advertised_flavor_note_ids` (p4) and `ix_roasters_archived`. These are raw-SQL/undeclared indexes the codebase manages by hand, exactly per the p4 precedent. Zero column/FK/table drift. Not actionable.
- **Context7 unavailable:** the project's mandated ctx7 lookup for the SQLAlchemy `Computed`/GENERATED API returned "monthly quota exceeded." Relied on the planner-verified pattern in 05-RESEARCH.md / 05-PATTERNS.md and confirmed the rendered DDL directly against the live Postgres catalog (`\d brew_sessions`) instead — the GENERATED clause, indexes, and FK ondelete all match the spec.

## Known Stubs

None — every column, schema field, and index in this plan is fully wired and exercised by the Wave 0 tests against the live DB. (Services, router, templates, and the Alpine components that consume these contracts are intentionally out of scope for this plan and land in Waves 2-4.)

## User Setup Required

None — no external service configuration required. (`pip install --user pytest pytest-asyncio respx` into the running container is the documented Wave 0 test step, not user setup; pytest was already present.)

## Next Phase Readiness

- Stable model + schema + event contracts are in place for the Wave 2-4 brew service, router, CSV import/export, prefill, and draft plans to build against.
- The GENERATED EY and ARRAY/JSONB columns are live and verified; analytics (Phase 6) can rely on the GIN index for containment queries.
- DB is at head `p5_brew_sessions`; full suite green.

## Self-Check: PASSED

All 6 created files and the SUMMARY exist on disk; all 5 plan commits (8b6cfd8, a13c4b2, ac1d21c, c396a75, 6ad2096) present in git history.

---
*Phase: 05-brew-sessions*
*Completed: 2026-05-20*
