---
phase: 11-pwa-mobile-polish
plan: "02"
subsystem: schema
tags: [migration, schema, pydantic, brew-sessions, brew-time]
dependency_graph:
  requires: [p10_search_indexes]
  provides: [brew_time_seconds column, BrewSessionCreate.brew_time_seconds]
  affects: [app/models/brew_session.py, app/schemas/brew_session.py]
tech_stack:
  added: []
  patterns: [additive-nullable-column migration, Pydantic Field range validation]
key_files:
  created:
    - app/migrations/versions/p11_brew_time_seconds.py
  modified:
    - app/models/brew_session.py
    - app/schemas/brew_session.py
    - tests/test_migrations.py
decisions:
  - "brew_time_seconds uses Integer (not BigInteger) — seconds fit in 32-bit int"
  - "Field(ge=0, le=86400) rejects negatives and values >24h (T-11-06)"
metrics:
  duration_minutes: 8
  completed_date: "2026-05-23"
  tasks_completed: 2
  files_changed: 4
requirements: [BREW-12]
---

# Phase 11 Plan 02: brew_time_seconds Schema Migration Summary

Additive nullable `brew_time_seconds INTEGER` column on `brew_sessions` via Alembic migration chained off `p10_search_indexes`, with Pydantic `Field(ge=0, le=86400)` validation and a migration smoke test.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Model column + Alembic migration | 2d169f5 | app/models/brew_session.py, app/migrations/versions/p11_brew_time_seconds.py |
| 2 | Pydantic field + migration smoke test | 76accf3 | app/schemas/brew_session.py, tests/test_migrations.py |

## Verification Results

- `alembic upgrade head` applied cleanly; `alembic current` reports `p11_brew_time_seconds (head)`
- SQLAlchemy inspector confirms `brew_sessions.brew_time_seconds` exists and is nullable
- psql `\d brew_sessions` confirms `brew_time_seconds | integer | |` with no default
- `pytest tests/test_migrations.py -q -rs`: **16 passed, 0 warnings, 0 skips**

## Schema Contracts

**Migration:** `p11_brew_time_seconds`
- `down_revision = "p10_search_indexes"` (chain confirmed)
- `upgrade()`: `op.add_column("brew_sessions", sa.Column("brew_time_seconds", sa.Integer(), nullable=True))`
- `downgrade()`: `op.drop_column("brew_sessions", "brew_time_seconds")`
- No app.models import in migration body

**Model:** `BrewSession.brew_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)`

**Schema:** `BrewSessionCreate.brew_time_seconds: int | None = Field(None, ge=0, le=86400)` — inherits into `BrewSessionUpdate` automatically.

## Decisions Made

- `Integer` (not `BigInteger`) for `brew_time_seconds` — seconds fit comfortably in 32-bit int; consistent with other non-ID integer columns
- `ge=0, le=86400`: rejects negative durations and values exceeding 24h per T-11-06 tamper mitigation
- Added `Integer` to existing named SQLAlchemy imports in `brew_session.py` rather than introducing `import sqlalchemy as sa` — keeps the file's existing import pattern

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. This plan adds a column and validation only; no UI wiring (intentionally deferred to GBM plan per D-10 scope note).

## Threat Surface Scan

No new network endpoints or auth paths introduced. The `BrewSessionCreate` field is consumed by the existing `POST /brew` route (already behind `require_user` + CSRF). No new threat surface beyond what is already in the plan's threat model.

## Self-Check: PASSED

- `app/migrations/versions/p11_brew_time_seconds.py` — exists
- `app/models/brew_session.py` contains `brew_time_seconds` — confirmed
- `app/schemas/brew_session.py` contains `brew_time_seconds` — confirmed
- `tests/test_migrations.py` extended — confirmed
- Commits `2d169f5` and `76accf3` — both present in git log
