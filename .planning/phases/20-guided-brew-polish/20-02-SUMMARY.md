---
phase: 20-guided-brew-polish
plan: 02
subsystem: data-layer
tags: [water-profiles, step-schema, brew-session, migration, alembic, pydantic, fastapi]

requires:
  - phase: 20-guided-brew-polish
    plan: 01
    provides: Wave 0 RED tests (contract lock for water profiles, StepSchema, brew timing)

provides:
  - WaterProfile shared-catalog model, schema, service, router (POST + GET /water-profiles)
  - Extended StepSchema with type/note/water_temp_c + optional water_grams
  - BrewSessionCreate extended with water_profile_id, first_drip_seconds, bloom_time_seconds
  - BrewSession model with water_profile_id FK + timing columns
  - p20_water_profiles Alembic migration (table + seed + FK link + timing columns)

affects:
  - 20-03 (brew form wiring — reads water_profiles, writes water_profile_id)
  - 20-04 (guided brew UI — reads first_drip_seconds/bloom_time_seconds from form)
  - 20-05 (guided brew Alpine component — finishBrewing() URL params)

tech-stack:
  added: []
  patterns:
    - "Shared-catalog model pattern: WaterProfile mirrors FlavorNote (BigInteger Identity PK, Text UNIQUE, timestamps)"
    - "Inline-create POST → HX-Trigger pattern (water-profile-created mirrors flavor-note-created)"
    - "Alembic inline-DDL data migration: INITCAP(TRIM) normalization + FK link via op.execute SQL"
    - "StepSchema backward-compat extension: all new fields Optional/defaulted so old JSONB dicts still validate"

key-files:
  created:
    - app/models/water_profile.py
    - app/schemas/water_profile.py
    - app/services/water_profiles.py
    - app/routers/water_profiles.py
    - app/migrations/versions/p20_water_profiles.py
  modified:
    - app/schemas/recipe.py
    - app/models/brew_session.py
    - app/schemas/brew_session.py
    - app/main.py
    - tests/conftest.py

key-decisions:
  - "WaterProfile uses plain Text (not CITEXT) for name — dedup handled by migration INITCAP(TRIM) normalization, not DB-level case insensitivity"
  - "POST /water-profiles returns JSON errors (not HTML fragment) — inline-create form is Alpine-managed, not an HTMX fragment swap"
  - "water_type column retained (not dropped) — deprecated but kept for backward compat; Plan 20-03 will stop writing to it"
  - "authed_client conftest fixture fixed to prime HMAC-signed CSRF token via GET / — raw placeholder string fails starlette-csrf URLSafeSerializer"

duration: 13min
completed: 2026-05-29
---

# Phase 20 Plan 02: Data Layer Summary

**Shared water_profiles catalog + extended StepSchema + brew_session timing FK + reversible seed/link migration turning GBREW-04/06/03 backend tests GREEN**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-05-29T16:15:51Z
- **Completed:** 2026-05-29T16:28:47Z
- **Tasks:** 3 (+1 style commit)
- **Files modified:** 10 (5 new, 5 modified)

## Accomplishments

- Created WaterProfile shared-catalog model (BigInteger Identity PK, Text UNIQUE name, optional notes, timestamps) — mirrors FlavorNote pattern exactly
- Created WaterProfileCreate schema (extra=forbid, min_length=1 name, optional notes) — T-20-04 mass-assignment guard
- Created water_profiles service (create/list/get with DuplicateNameError on UNIQUE violation)
- Created water_profiles router: POST /water-profiles fires HX-Trigger `water-profile-created` (D-02); GET /water-profiles returns JSON list; both Depends(require_user) + starlette-csrf covered
- Registered water_profiles_router in app/main.py adjacent to flavor_notes_router
- Extended StepSchema: type (Literal Bloom/Pour/Wait/Action, default Pour), water_grams → Optional (D-07), note (max 200), water_temp_c (50-100) — all backward-compatible (D-04, A3)
- Extended BrewSessionCreate: water_profile_id (ge=1 tamper guard, T-20-05), first_drip_seconds + bloom_time_seconds (ge=0, le=86400)
- Extended BrewSession model: water_profile_id FK (SET NULL), first_drip_seconds, bloom_time_seconds; water_type retained (deprecated, D-12)
- Created p20_water_profiles migration: creates table, seeds INITCAP(TRIM) normalized profiles, adds + links FK, adds timing columns; downgrade() reverses cleanly

## Task Commits

1. **Task 1: Water-profile model, schema, service, router, registration** — `84010de`
2. **Task 2: StepSchema extension + brew_session model/schema fields** — `0535896`
3. **Task 3: Alembic migration p20_water_profiles** — `a8a6104`
4. **Style: ruff check + format fixes** — `8ad6d7c`

## Test Results

All 14 in-scope tests GREEN:

- `tests/test_phase20_water_profiles.py`: 6 tests (3 endpoint + 3 migration normalization)
- `tests/test_phase20_step_schema.py`: 5 tests (backward compat, Wait step, temp range, coaching data, extra-field rejection)
- `tests/test_phase20_brew_session.py`: 3 tests (timing fields schema, water_profile_id schema, timing columns DB introspection)

`test_gbm_finish_url_has_brew_time` remains RED — this is Plan 20-04 scope (brew form first_drip/bloom_time param wiring), as documented in 20-01 SUMMARY.

`alembic downgrade -1` then `alembic upgrade head` round-trips without error.

## Files Created/Modified

- `app/models/water_profile.py` — WaterProfile shared-catalog model (D-01)
- `app/schemas/water_profile.py` — WaterProfileCreate with extra=forbid
- `app/services/water_profiles.py` — create/list/get with DuplicateNameError handling
- `app/routers/water_profiles.py` — POST + GET /water-profiles with HX-Trigger (D-02)
- `app/migrations/versions/p20_water_profiles.py` — table + seed + FK link + timing (D-03)
- `app/schemas/recipe.py` — StepSchema extended (D-04..D-07)
- `app/models/brew_session.py` — water_profile_id FK + timing columns added
- `app/schemas/brew_session.py` — BrewSessionCreate extended (D-12, D-14)
- `app/main.py` — water_profiles_router import + include_router
- `tests/conftest.py` — authed_client CSRF prime + water_profiles TRUNCATE (auto-fixes)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] authed_client fixture sends unsigned CSRF token**
- **Found during:** Task 3 (endpoint tests failed 403)
- **Issue:** The top-level conftest.py `authed_client` fixture pre-populated a raw literal string as `csrftoken` cookie + `X-CSRF-Token` header. starlette-csrf 3.x validates tokens via `URLSafeSerializer.loads()` (HMAC-signed), so any raw string returns `BadSignature → False`. The phase_04 conftest works because tests there call `_prime_csrf()` to fetch a real token from GET /. The top-level fixture didn't do this, making any POST endpoint unreachable from top-level test files.
- **Fix:** Updated `authed_client` to drop the placeholder, issue GET / to coax the middleware into minting a real HMAC-signed token, then wire that token as both cookie + header.
- **Files modified:** `tests/conftest.py`
- **Commit:** `a8a6104`

**2. [Rule 2 - Missing critical functionality] water_profiles not in _reset_catalog_tables TRUNCATE list**
- **Found during:** Task 3 (test_create_water_profile failed 422 duplicate on second run)
- **Issue:** The `_reset_catalog_tables` module-scoped autouse fixture TRUNCATEs all catalog tables after each test module, but `water_profiles` was missing from the list. Test data from `test_create_water_profile` ("Third Wave Water") persisted across pytest sessions, causing the next run to fail with 422 duplicate.
- **Fix:** Added `TRUNCATE TABLE water_profiles RESTART IDENTITY CASCADE` after `brew_sessions` (which is truncated first, satisfying the FK dependency since `brew_sessions.water_profile_id` is SET NULL).
- **Files modified:** `tests/conftest.py`
- **Commit:** `a8a6104`

## Known Stubs

None — all production code is fully wired. The water_profiles router, service, and model are live. The migration has been applied. No placeholder data or UI stubs.

## Threat Flags

No new threat surface beyond what the plan's threat model covers:

| Flag | File | Description |
|------|------|-------------|
| T-20-02 mitigated | app/routers/water_profiles.py | Depends(require_user) on all endpoints |
| T-20-03 mitigated | app/routers/water_profiles.py | starlette-csrf middleware covers /water-profiles POST |
| T-20-04 mitigated | app/schemas/water_profile.py | ConfigDict(extra="forbid") |
| T-20-05 mitigated | app/schemas/brew_session.py | water_profile_id Field(None, ge=1) |
| T-20-07 mitigated | app/schemas/recipe.py | note max_length=200, water_temp_c ge=50 le=100 |

## Self-Check

- [x] app/models/water_profile.py — exists, class WaterProfile, __tablename__ = "water_profiles"
- [x] app/schemas/water_profile.py — exists, WaterProfileCreate, extra=forbid
- [x] app/services/water_profiles.py — exists, create/list/get functions
- [x] app/routers/water_profiles.py — exists, POST + GET /water-profiles, HX-Trigger
- [x] app/migrations/versions/p20_water_profiles.py — exists, revision p20_water_profiles, down_revision p19_ai_research_predict
- [x] app/main.py — water_profiles_router import + include_router
- [x] Task 1 commit: 84010de
- [x] Task 2 commit: 0535896
- [x] Task 3 commit: a8a6104
- [x] Style commit: 8ad6d7c
- [x] alembic current shows p20_water_profiles (head)
- [x] 14 in-scope tests GREEN

## Self-Check: PASSED

## Next Phase Readiness

Plan 20-03 (brew form wiring) can proceed. The data layer is complete:
- POST /water-profiles is live and tested
- water_profiles table exists and is seeded
- brew_sessions.water_profile_id FK column exists
- BrewSessionCreate accepts water_profile_id
- StepSchema accepts type/note/water_temp_c with backward compat

---
*Phase: 20-guided-brew-polish*
*Completed: 2026-05-29*
