---
phase: 10
plan: "01"
subsystem: search
tags: [testing, migration, database, gin-index, tdd, idor, xss]
dependency_graph:
  requires: []
  provides:
    - tests/test_search.py (Wave-0 RED scaffold, 15 named tests)
    - app/migrations/versions/p10_search_indexes.py (6 GIN trigram indexes)
  affects:
    - Plan 02 (search service/router — RED→GREEN target)
    - Plan 03 (header injection — test_header_auth_gate RED until then)
tech_stack:
  added: []
  patterns:
    - Wave-0 RED scaffold: test file imports from not-yet-built service (ImportError = intentional)
    - GIN trigram via op.execute() — Alembic cannot autogenerate USING GIN
    - Expression index on (brand || ' ' || model) for equipment D-14 search
    - Two-user IDOR fixture: seeded_admin_user (User A) + seeded_regular_user (User B)
key_files:
  created:
    - tests/test_search.py
    - app/migrations/versions/p10_search_indexes.py
  modified: []
decisions:
  - "No CONCURRENTLY in migration: Alembic wraps in transaction; tables empty at first Phase 10 deploy"
  - "Wave-0 RED: ImportError on app.services.search surfaces as real test failure, not skip"
  - "IDOR fixture uses two distinct users from root conftest (seeded_admin_user + seeded_regular_user)"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-22"
  tasks: 2
  files: 2
---

# Phase 10 Plan 01: Wave-0 Test Scaffold + GIN Index Migration Summary

Wave-0 Nyquist test harness (15 tests, two-user IDOR fixtures) and six GIN trigram search indexes applied from alembic head p5_brew_sessions.

## What Was Built

### Task 1: Wave-0 Test Scaffold (`tests/test_search.py`)

15 named test functions covering the full 10-VALIDATION.md requirement map. All RED at this wave — failures on `hx-get="/search"` not found (Plan 03 not yet applied) and `ImportError` on `app.services.search` (Plan 02 not yet built).

**IDOR fixture (T-10-IDOR):** `test_brew_note_user_scoping` uses both root conftest users (User A = `seeded_admin_user`, User B = `seeded_regular_user`). Seeds User B's brew session with `notes="secret Ethiopia mango"`, asserts User A's `/search?q=mango` response does NOT contain that text, and User B's response DOES.

**XSS test (T-10-XSS):** `test_highlight_xss_safe` calls `search_service.highlight(text="<script>alert(1)</script> beans", query="beans")` and asserts `&lt;script&gt;` appears (escaped) and `<script>` does NOT (raw). Plan 02 must implement the `markupsafe.Markup` + `escape()` composition to pass this.

**No pass-by-skip:** The module-level try/except on `from app.services import search` sets `search_service = None` without skipping. Tests that call the service fail with `AssertionError: app.services.search not importable` — a real failure, not a silent skip. (memory: tests-pass-by-skip-mask-green)

### Task 2: Index Migration (`app/migrations/versions/p10_search_indexes.py`)

Six GIN trigram indexes via `op.execute()`, chained from `down_revision = "p5_brew_sessions"`.

| Index | Table | Column(s) |
|-------|-------|-----------|
| `ix_search_coffees_name` | `coffees` | `name gin_trgm_ops` |
| `ix_search_roasters_name` | `roasters` | `name gin_trgm_ops` |
| `ix_search_flavor_notes_name` | `flavor_notes` | `name gin_trgm_ops` |
| `ix_search_recipes_name` | `recipes` | `name gin_trgm_ops` |
| `ix_search_equipment_brand_model` | `equipment` | `(brand \|\| ' ' \|\| model) gin_trgm_ops` |
| `ix_search_brew_sessions_notes` | `brew_sessions` | `notes gin_trgm_ops` |

**Downgrade verified:** `alembic downgrade -1` removes all six; `alembic upgrade head` restores them cleanly.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 — Test scaffold | `aaeb653` | `test(10-01): add Wave-0 search test scaffold (15 tests, two-user IDOR fixtures)` |
| 2 — Index migration | `0e48f50` | `feat(10-01): add GIN trigram index migration for global search` |

## Verification Results

**Test file:** `python -c "import ast; ast.parse(...)"` → `SYNTAX OK`

**Test count:** `grep -c "def test_"` → `15` (all VALIDATION-map tests present)

**Wave-0 RED state confirmed:** `pytest tests/test_search.py -rs -q` fails on:
- `test_header_auth_gate`: `AssertionError: Search header not found on authenticated home page — Plan 03 not yet applied`
- (All subsequent tests would fail on 404 /search or ImportError on search_service)
- No collection errors, no skips

**Migration verification:**
- `alembic upgrade head` → `p10_search_indexes (head)`
- `SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_search_%'` → 6 rows
- `alembic downgrade -1` → 0 rows; `alembic upgrade head` → 6 rows (round-trip clean)

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries introduced by this plan. The migration is DDL-only (index creation); no data access surface changes.

## Known Stubs

None. This plan creates test infrastructure and a DDL migration only. No UI components or service functions with stub data.

## Self-Check: PASSED

- [x] `tests/test_search.py` exists (750 lines, 15 test functions)
- [x] `app/migrations/versions/p10_search_indexes.py` exists (119 lines)
- [x] Commit `aaeb653` exists in git log
- [x] Commit `0e48f50` exists in git log
- [x] All six `ix_search_*` indexes confirmed in `pg_indexes` table
- [x] Downgrade round-trip verified
