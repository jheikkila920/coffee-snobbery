---
phase: 16-cafe-quick-rate
plan: "01"
subsystem: database
tags: [snobbery, postgres, sqlalchemy, alembic, gin-index, migration]

dependency_graph:
  requires:
    - Phase 15.1 migration head (p15_1_varietal_m2m)
  provides:
    - cafe_logs table with all 13 columns per D-01..D-05
    - CafeLog SQLAlchemy 2.0 model (importable as app.models.cafe_log.CafeLog)
    - _require_cafe_logs_table() skip-gate helper in tests/conftest.py
    - tests/migrations/test_cafe_logs_migration.py smoke test
  affects:
    - app/models/__init__.py (CafeLog added to exports for Alembic metadata discovery)

tech_stack:
  added:
    - "CafeLog SQLAlchemy 2.0 model (new file)"
    - "p16_cafe_logs Alembic migration (new file)"
    - "tests/migrations/ package (new directory)"
  patterns:
    - "Alembic-safe convention: inline sa.Column, no app.models imports in migration"
    - "GIN index via op.execute (autogenerate cannot emit USING GIN — Pitfall 1)"
    - "DESC B-tree via op.execute (sort direction not preserved by autogenerate)"
    - "_require_cafe_logs_table() skip-gate (project memory: tests-pass-by-skip-mask-green)"

key_files:
  created:
    - app/models/cafe_log.py
    - app/migrations/versions/p16_cafe_logs.py
    - tests/migrations/__init__.py
    - tests/migrations/test_cafe_logs_migration.py
  modified:
    - app/models/__init__.py

decisions:
  - "Plain Text (NOT CITEXT) for cafe_name and origin_country — per-user free-text, not shared-catalog identities (D-01/D-03)"
  - "GIN index hand-edited via op.execute per Pitfall 1 — autogenerate cannot emit USING GIN"
  - "down_revision=p15_1_varietal_m2m confirmed via alembic heads before finalizing"
  - "_require_cafe_logs_table placed in tests/conftest.py to mirror _require_analytics_tables pattern"

metrics:
  duration: "~25 minutes"
  completed: "2026-05-27"
  tasks_completed: 3
  tasks_total: 3
  files_created: 4
  files_modified: 1
---

# Phase 16 Plan 01: CafeLog Model + Migration Summary

One-liner: `cafe_logs` table with 13 columns (D-01..D-05 + Claude's discretion), GIN + DESC B-tree indexes via `op.execute`, and a `_require_cafe_logs_table()` skip-gate for downstream test files.

## What Was Built

### Task 1 — CafeLog model + Alembic migration

**`app/models/cafe_log.py`** — SQLAlchemy 2.0 model with all 13 `Mapped[...]` columns:

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | BigInteger Identity | NOT NULL | PK |
| user_id | BigInteger FK(users.id) | NOT NULL | ondelete=RESTRICT |
| roaster_id | BigInteger FK(roasters.id) | NULL | ondelete=SET NULL (D-02) |
| cafe_name | Text | NOT NULL | plain Text, NOT CITEXT (D-01) |
| origin_country | Text | NULL | no FK, no countries table (D-03) |
| brew_method | Text | NULL | free-text, no enum (D-05) |
| rating | Numeric(3,2) | NULL | 0-5 in 0.25 steps |
| flavor_note_ids | BIGINT[] | NOT NULL | server_default='{}', GIN in migration (D-04) |
| notes | Text | NOT NULL | server_default='' |
| photo_filename | Text | NULL | |
| logged_at | TIMESTAMPTZ | NOT NULL | editable for backfilling |
| created_at | TIMESTAMPTZ | NOT NULL | server_default=now() |
| updated_at | TIMESTAMPTZ | NOT NULL | server_default=now() |

`__table_args__` declares the DESC B-tree index. GIN is NOT declared in the model — it lives in the migration via `op.execute` per the established Pitfall 1 pattern.

**`app/migrations/versions/p16_cafe_logs.py`** — Alembic migration:
- `revision = "p16_cafe_logs"`
- `down_revision = "p15_1_varietal_m2m"` (single head confirmed pre-write)
- `upgrade()`: `op.create_table(...)` + two `op.execute(...)` calls for B-tree and GIN indexes
- `downgrade()`: `DROP INDEX IF EXISTS` (both) then `op.drop_table("cafe_logs")`

**`app/models/__init__.py`** — `CafeLog` added to exports so Alembic metadata discovery is complete.

### Task 2 — Skip-gate helper + migration smoke test

**`tests/conftest.py`** — `_require_cafe_logs_table()` helper added:
- Calls `SELECT to_regclass('public.cafe_logs')` via `engine.connect()`
- `pytest.skip("cafe_logs table not present — migration p16_cafe_logs not applied")` when table absent
- Wraps import + connect in `try/except` mirroring `_require_analytics_tables()` pattern
- Skip message includes "p16_cafe_logs" for actionable `pytest -rs` output

**`tests/migrations/test_cafe_logs_migration.py`** — smoke test (1 test):
- `test_cafe_logs_migration_upgrade()` gates on `_require_postgres()` + `_require_cafe_logs_table()`
- Asserts: `to_regclass('public.cafe_logs')` non-NULL
- Asserts: both `ix_cafe_logs_user_logged_at` and `ix_cafe_logs_flavor_note_ids` in `pg_indexes`
- Asserts: GIN access method (`pg_am.amname == 'gin'`) via `pg_class + pg_am` join
- Gates: Postgres 16+ version check (skip if < 160000)
- Does NOT run `alembic downgrade -1` — no cross-test DB state mutation

### Task 3 — Lint clean

`ruff format --check` and `ruff check` both exit 0 on all four files. No `# noqa` suppressions added.

## Alembic State

```
alembic heads  →  p16_cafe_logs (head)
alembic current → p16_cafe_logs (head)
```

## psql `\d cafe_logs` output

```
Table "public.cafe_logs"
     Column      |           Type           | Nullable |          Default
-----------------+--------------------------+----------+---------------------------
 id              | bigint                   | not null | generated by default as identity
 user_id         | bigint                   | not null |
 roaster_id      | bigint                   |          |
 cafe_name       | text                     | not null |
 origin_country  | text                     |          |
 brew_method     | text                     |          |
 rating          | numeric(3,2)             |          |
 flavor_note_ids | bigint[]                 | not null | '{}'::bigint[]
 notes           | text                     | not null | ''::text
 photo_filename  | text                     |          |
 logged_at       | timestamp with time zone | not null | now()
 created_at      | timestamp with time zone | not null | now()
 updated_at      | timestamp with time zone | not null | now()
Indexes:
    "cafe_logs_pkey" PRIMARY KEY, btree (id)
    "ix_cafe_logs_flavor_note_ids" gin (flavor_note_ids)
    "ix_cafe_logs_user_logged_at" btree (user_id, logged_at DESC)
Foreign-key constraints:
    "cafe_logs_roaster_id_fkey" FOREIGN KEY (roaster_id) REFERENCES roasters(id) ON DELETE SET NULL
    "cafe_logs_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
```

## Test Results

```
pytest tests/migrations/test_cafe_logs_migration.py -x -v -rs
1 passed, 0 skipped in 2.25s
```

- `test_cafe_logs_migration_upgrade` PASSED
- GIN access method assertion exercised (gin confirmed)
- Both index names confirmed present
- Round-trip (downgrade + upgrade) verified manually during Task 1

## Deviations from Plan

None — plan executed exactly as written.

- Column types, nullability, and FK directionality match the plan's action spec verbatim
- GIN via `op.execute` per Pitfall 1 (confirmed via `pg_am.amname = 'gin'` assertion)
- `down_revision` pinned to `p15_1_varietal_m2m` (verified with `alembic heads` before writing)
- `_require_cafe_logs_table()` placed in `tests/conftest.py` to mirror `_require_analytics_tables()` exactly
- No `coffee_id` FK added (D-01 rejection respected)
- No CITEXT on `cafe_name` or `origin_country` (PATTERNS.md explicit)
- No `countries` lookup table (D-03 rejection respected)

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | ac2344a | feat(16-01): add CafeLog model + p16_cafe_logs migration |
| 2 | 57d531d | test(16-01): add _require_cafe_logs_table() skip-gate + migration smoke test |

## Known Stubs

None. This plan is schema-only — no UI rendering, no data service layer, no stubs.

## Threat Surface Scan

No new threat surface beyond what the plan's `<threat_model>` covers. The `cafe_logs` table introduces a new per-user data surface, but the schema-level mitigations (ondelete=RESTRICT for user_id, ondelete=SET NULL for roaster_id, GIN index for D-04) are all applied. Per-user IDOR scoping is deferred to Plan 16-02 (accepted disposition T-16-01-02).

## Self-Check

- [x] `app/models/cafe_log.py` — file exists, contains `class CafeLog(Base):`
- [x] `app/migrations/versions/p16_cafe_logs.py` — file exists, contains `revision = "p16_cafe_logs"` and `down_revision = "p15_1_varietal_m2m"`
- [x] `tests/conftest.py` — updated, contains `_require_cafe_logs_table`
- [x] `tests/migrations/test_cafe_logs_migration.py` — file exists, 1 test collected and passing
- [x] `alembic heads` returns `p16_cafe_logs (head)` (single head)
- [x] Both commits ac2344a and 57d531d exist in git log
- [x] `ruff format --check` + `ruff check` both exit 0 on all 4 plan files
