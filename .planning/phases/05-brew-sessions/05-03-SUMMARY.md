---
phase: 05-brew-sessions
plan: 03
subsystem: api
tags: [csv, import, export, citext, single-transaction, dedup, formula-injection, idor]

# Dependency graph
requires:
  - phase: 05-brew-sessions (plan 01)
    provides: BrewSession ORM (GENERATED extraction_yield_pct, flavor_note_ids_observed ARRAY), BrewCsvRow per-row schema, brew.csv.* event constants
  - phase: 05-brew-sessions (plan 02)
    provides: brew_sessions service (referenced for the same parameterized list-filter select reused by export)
  - phase: 04-shared-catalog
    provides: coffees (citext name, identity (name, roaster_id)), bags (coffee_id + roast_date), roasters/equipment/recipes, flavor_notes.create_flavor_note (D-09 citext link-or-create), DuplicateNameError sentinel
provides:
  - "app/services/csv_io.py — header-driven brew CSV import (D-12 coffee / D-13 bag resolve, D-14 dedup, single-transaction insert, D-09 observed-note auto-create) + name-based round-trip-safe export (D-15)"
  - "RowOutcome dataclass (status/row_number/reason) — the per-row import contract the Wave 3/4 result UI renders"
  - "EXPORT_FIELDNAMES — the authoritative Snobbery-native round-trip header set; importer alias table treats these as primary"
  - "Upload-guard constants MAX_CSV_BYTES (5 MiB) + ALLOWED_CSV_CONTENT_TYPES for the router (T-05-11)"
affects: [brew-router, brew-import-ui, brew-export-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Header-driven CSV parse: csv.DictReader + utf-8-sig decode (BOM/quoted-comma safe); case-insensitive alias map normalizes any header layout onto canonical fields, unknown columns ignored (resilient to Beanconqueror version drift)"
    - "Resolve-validate-then-batch: refused/skipped rows never enter the transaction; all accepted rows + their D-09 notes commit ONCE; a DB error rolls the whole batch back (no partial commit, Pitfall 4)"
    - "CSV formula-injection neutralization: free-text export cells with a leading = + - @ are prefixed with a single quote (T-05-13)"

key-files:
  created:
    - app/services/csv_io.py
    - tests/services/test_brew_csv.py
  modified: []

key-decisions:
  - "CSV formula injection mitigated by prefixing leading = + - @ with a single quote on free-text export columns only (numeric columns are not at risk) — the plan's chosen disposition for T-05-13"
  - "Beanconqueror header aliases shipped as a clearly-marked TODO-confirm block; the Snobbery-native EXPORT_FIELDNAMES is the authoritative round-trip format and works regardless of Beanconqueror confirmation"
  - "Equipment/recipe name resolution on import is best-effort link (null when unmatched), never a refusal cause — only coffee (D-12) and a named-but-unmatched bag (D-13) refuse a row"

patterns-established:
  - "Header-driven CSV importer with a case-insensitive alias map (canonical-field normalization decoupled from literal header text)"
  - "Single-transaction batch insert with a per-row outcome list (inserted/skipped/refused-with-reason)"
  - "Formula-injection-safe CSV export (leading-trigger single-quote prefix on free-text cells)"

requirements-completed: [BREW-10, BREW-11]

# Metrics
duration: ~5min
completed: 2026-05-20
---

# Phase 5 Plan 03: Brew CSV Import/Export Summary

**Header-driven, single-transaction brew CSV importer (D-12 coffee / D-13 bag resolve, D-14 dedup, D-09 observed-note auto-create, no partial commit) plus a name-based round-trip-safe export with computed brew-ratio + GENERATED extraction yield and CSV formula-injection neutralization — 7 new tests green, 33 Phase-5 service/schema tests green in-container.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-20T02:04:30Z
- **Completed:** 2026-05-20T02:08:53Z
- **Tasks:** 2 of 2 (both TDD)
- **Files modified:** 2 (2 created, 0 modified)

## Accomplishments

- `import_brews(db, *, raw_bytes, by_user_id) -> list[RowOutcome]`: header-driven (`csv.DictReader` + `utf-8-sig` decode — BOM/quoted-comma safe, never `split(",")`), with a case-insensitive alias map that normalizes any header layout onto canonical fields and ignores unknown columns. Per-row resolution in the locked order:
  - **Coffee (D-12):** citext `Coffee.name == name`, roaster-qualified via a `Roaster` join when a `roaster_name` column is present; missing → refused (`coffee "{name}" not in catalog`), ambiguous multi-match → refused (`coffee "{name}" ambiguous (matches multiple roasters)`).
  - **Bag (D-13):** named `roast_date` that resolves → link; named-but-unmatched/unparseable → refused (`bag (roast {date}) not found`); no bag named → `bag_id=None` (freestyle).
  - **Dedup (D-14):** `select` probe on `(user_id, coffee_id, brewed_at)` (no UNIQUE — Plan 01 deferred it) → skipped (`duplicate of an existing session`).
  - **Validate:** each accepted row through `BrewCsvRow` (numeric ranges + Decimal rating); a validation failure refuses the row with the field error.
- **Single transaction (BREW-11, Pitfall 4):** refused/skipped rows never enter the txn; all accepted rows + their D-09 observed notes are added and committed ONCE; any DB error during the batch rolls the whole thing back (verified by a forced-commit-failure test asserting zero rows committed).
- **D-09 observed-note auto-create:** delimited names are resolved by citext (existing reused, case-variant linked not duplicated) or created with `category="other"` inside the same transaction, reusing `flavor_notes.create_flavor_note` (which already handles the concurrent UNIQUE-citext collision → link-existing).
- **Mass-assignment defense (T-05-10):** `user_id` is taken from `by_user_id` only, never from the file; `extraction_yield_pct` (GENERATED) is never written.
- `export_brews(db, *, by_user_id, **filters) -> str`: name-resolved CSV via `csv.DictWriter` over the explicit `EXPORT_FIELDNAMES` header (the authoritative round-trip set the importer treats as primary). Resolves ids → human names (coffee + roaster, recipe, brewer/grinder/kettle, observed flavor notes joined by `;`), includes the read-only computed `brew_ratio` (water/dose, blank when dose is 0/null — never NaN/Inf) and the GENERATED `extraction_yield_pct`, scopes the query by `by_user_id` (T-05-14), reuses the same parameterized filter clauses as `list_brew_sessions`, and emits `BREW_CSV_EXPORTED`.
- **CSV formula injection (T-05-13):** free-text export cells beginning with `= + - @` are prefixed with a single `'` (numeric columns untouched), verified by a dedicated test.
- **Round-trip (D-15):** export → import for a fresh user with the same catalog inserts every row with no refusals (bag-linked and freestyle rows both round-trip); re-importing the same file for the same user is an all-skipped no-op.
- **Upload guard (T-05-11):** `MAX_CSV_BYTES` (5 MiB) + `ALLOWED_CSV_CONTENT_TYPES` exported for the Wave 3 router to reject non-CSV/oversized payloads before buffering the full body (net-new — no reusable byte-size service exists).

## Task Commits

Each task TDD: test (RED) → feat (GREEN). The export functions live in the same `csv_io.py` and were implemented in the Task 1 GREEN commit (shared module); Task 2's commit lands the verifying export tests.

1. **Task 1: CSV import — header-driven resolve + dedup + single transaction**
   - `7133746` (test) [TDD RED]
   - `a6f0f69` (feat) [TDD GREEN — also lands the `export_brews` helpers, which share `csv_io.py`]
2. **Task 2: CSV export — name-based, round-trip-safe** — `6643b3c` (test) [verifies the export functions committed in a6f0f69]

_TDD plan-level gate satisfied: a `test(...)` RED commit (7133746) precedes the `feat(...)` GREEN commit (a6f0f69)._

## Files Created/Modified

- `app/services/csv_io.py` — `import_brews` (resolve/dedup/validate + single-txn batch + D-09 notes), `export_brews` (name-resolved + ratio + EY + formula-prefix), `RowOutcome` dataclass, `_HEADER_ALIASES` map, `EXPORT_FIELDNAMES`, upload-guard constants, and the per-entity resolve/name-cache helpers
- `tests/services/test_brew_csv.py` — 7 tests: import outcomes (refused-not-in-catalog/ambiguous/bag-not-found, skipped-duplicate, inserted-freestyle/with-bag), single-transaction rollback, D-09 auto-create; export name-resolution, ratio+EY, round-trip (export→import + same-user no-op), formula-injection prefix

## Decisions Made

- **CSV formula-injection mitigation = leading-trigger single-quote prefix.** The plan offered two dispositions for T-05-13 (prefix vs document-as-reimport-only); chose the prefix on free-text columns only (`coffee_name`, `roaster_name`, `recipe_name`, `brewer/grinder/kettle`, `water_type`, `grind_setting`, `observed_flavor_notes`, `notes`). Numeric columns can't carry a formula payload, so they pass through. Recorded here per the plan's `<output>` instruction.
- **Beanconqueror aliases shipped TODO-confirm; Snobbery-native is authoritative.** Per the plan's `<unverified_assumption>`, the literal Beanconqueror export header strings, the rating scale (0-5 vs 0-10), and the `brew_quantity`-vs-`brew_beverage_quantity` water-in/yield-out distinction are unverified. The Beanconqueror rows in `_HEADER_ALIASES` are each commented `# TODO-confirm` and built from the verified internal field names; they require no algorithm change to confirm. The Snobbery-native `EXPORT_FIELDNAMES` round-trip is fully tested and independent of this. **No rating scale-conversion is applied** because the Snobbery-native export already emits 0-5 0.25-step ratings; a conversion step is only needed once a real Beanconqueror file confirms its scale (then add it to the alias-driven parse without touching the algorithm).
- **Equipment/recipe resolution is best-effort, never a refusal cause.** Only an unresolvable coffee (D-12) or a named-but-unmatched bag (D-13) refuses a row. Unmatched equipment/recipe names link to `None`, matching the plan's "refuse-or-skip policy planner picks" with the least-surprising behavior for a household importing a partial file.
- **`_parse_brewed_at` assumes UTC for naive timestamps.** Stored UTC (the router/template renders in `APP_TIMEZONE`), mirroring the `brew_sessions` service `brewed_at` convention.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Synced stale `form_validation.py` + `flavor_notes.py` into the running container**
- **Found during:** Task 1 GREEN (first in-container test run)
- **Issue:** The running `coffee-snobbery` image predated Phase 4's `DuplicateNameError` addition to `app/services/form_validation.py`; the container copy lacked the symbol, so `csv_io.py`'s `from app.services.form_validation import DuplicateNameError` (and the `flavor_notes.create_flavor_note` it reuses) failed to import in the container at test time.
- **Fix:** `docker compose cp` the current repo `app/services/form_validation.py` and `app/services/flavor_notes.py` into the running container so the test runtime matches the repo source. No source change — purely a container test-iteration sync (the documented baked-image gap from CLAUDE.md; a `docker compose build` on deploy picks up the same files).
- **Files modified:** none (container filesystem only)
- **Verification:** `from app.services.form_validation import DuplicateNameError` resolves; all 7 new tests + the 33-test Phase-5 service/schema suite pass.

**Total deviations:** 1 (Rule 3 blocking — container sync only, no source change)
**Impact on plan:** None on scope or production code. The deviation is a test-environment artifact of the baked image (no source bind-mount); the repo files were already correct.

## Issues Encountered

- **Stale baked image (above):** the running container is older than the current repo `app/services/`. Resolved by `docker compose cp` of the two dependency modules for the test run; a normal deploy (`docker compose build`) is the permanent fix.
- **pytest cache permission warnings:** `/app/.pytest_cache` is not writable by the app user — benign `PytestCacheWarning` noise on every run (same as Plans 01/02). Tests pass; no action.
- **Context7 / ctx7 not invoked:** the implementation uses only standard, already-in-use SQLAlchemy 2.0 Core idioms (`select()`, joins, `in_()`), stdlib `csv`/`decimal`, and Pydantic v2 patterns already established in the codebase — no version-specific API lookup was load-bearing. Behavior was validated directly against the live Postgres via the 7 in-container tests.

## Known Stubs

None — `import_brews` and `export_brews` are fully implemented and exercised end-to-end against the live DB (resolve, dedup, single-transaction rollback, D-09 auto-create, name resolution, computed ratio+EY, round-trip, formula prefix). The Beanconqueror alias rows are intentionally marked TODO-confirm (the algorithm is complete; only the literal header strings await a real export file) — this is a documented data-table confirmation, not a code stub, and does not block the Snobbery-native round-trip the plan requires. The Wave 3/4 router + import/export UI that consume this service are out of scope for this plan.

## Threat Flags

None — every threat-register mitigation for this plan was implemented (T-05-09 parameterized citext resolve; T-05-10 user_id-from-arg + EY-never-written; T-05-11 upload-guard constants; T-05-12 single-transaction no-partial-commit; T-05-13 formula-prefix; T-05-14 user-scoped export). No new security surface beyond the plan's threat model.

## User Setup Required

None — no external service configuration. (One operational note for deploy: the running container image is older than the repo `app/services/`; a `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery` on the next deploy bakes the current source, including this plan's `csv_io.py`.)

## Next Phase Readiness

- The CSV import/export service contract is defined and tested, so the Wave 3 `/brew/import` and `/brew/export` routes can build a thin request/response layer on top of `import_brews` (render `RowOutcome` list via the import-result fragment) and `export_brews` (wrap in `Content-Disposition: attachment`, reuse the list filter query params), using `MAX_CSV_BYTES` + `ALLOWED_CSV_CONTENT_TYPES` for the upload guard.
- The Beanconqueror header aliases await one real "Export → Excel" file from John to confirm the literal header strings, rating scale, and water-in/yield-out column mapping — adding/adjusting alias rows requires no algorithm change.

## Self-Check: PASSED

Both created files (`app/services/csv_io.py`, `tests/services/test_brew_csv.py`) exist on disk; all 3 task commits (7133746, a6f0f69, 6643b3c) present in git history; all 7 CSV tests + the 33-test Phase-5 service/schema suite pass in-container.

---
*Phase: 05-brew-sessions*
*Completed: 2026-05-20*
