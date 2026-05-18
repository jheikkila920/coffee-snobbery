---
phase: 03-encryption-settings
plan: 01
subsystem: schema
tags: [schema, alembic, api_credentials, app_settings, encryption, sec-08, sec-09]
requires:
  - app/models/base.py
  - app/models/app_setting.py
  - app/migrations/versions/p1_sessions_table.py
  - app/migrations/versions/0001_initial.py
provides:
  - app/models/api_credential.py
  - app/migrations/versions/p3_api_credentials.py
  - "schema:api_credentials"
  - "schema:app_settings.encryption_key_primary_fingerprint"
affects:
  - app/models/__init__.py
tech-stack:
  added: []
  patterns:
    - "SQLAlchemy 2.0 Mapped[bytes | None] over LargeBinary (bytea) — Fernet bytes contract preserved end-to-end."
    - "Text + CHECK constraint over Postgres ENUM for the provider discriminator (agile to extend, type-honest at the DB layer)."
    - "Alembic-safe migration body: sa.table()+op.bulk_insert(), zero app.models imports."
key-files:
  created:
    - app/models/api_credential.py
    - app/migrations/versions/p3_api_credentials.py
  modified:
    - app/models/__init__.py
decisions:
  - "D-01: One row per provider, UPDATE on rotation (no key-history table)."
  - "D-02: model_name lives on api_credentials, not in app_settings."
  - "D-03: last_four denormalized on the row so admin masked-list rendering does not invoke the encryption service."
  - "D-04: Migration seeds both provider rows with is_enabled=false, ciphertext=NULL."
  - "D-discretion: provider is Text + CHECK constraint (api_credentials_provider_check) rather than Postgres ENUM."
  - "D-discretion: key_ciphertext is LargeBinary (bytea) + Mapped[bytes | None]."
metrics:
  duration_minutes: 14
  completed_date: 2026-05-18
  tasks_completed: 2
  files_created: 2
  files_modified: 1
---

# Phase 03 Plan 01: api_credentials Schema + Fingerprint app_setting — Summary

One-liner: Lands the `api_credentials` table, its SQLAlchemy 2.0 `Mapped[...]` model, and the new `encryption_key_primary_fingerprint` `app_settings` row — the at-rest substrate for SEC-08 (Fernet-encrypted provider keys) and SEC-09 (auto-rewrap on key rotation).

## What was built

### Files created

- **`app/models/api_credential.py`** — `ApiCredential(Base)` with 8 typed columns:
  - `provider: Mapped[str]` PK (Text)
  - `key_ciphertext: Mapped[bytes | None]` (LargeBinary / `bytea`, nullable)
  - `last_four: Mapped[str | None]` (Text, nullable)
  - `model_name: Mapped[str | None]` (Text, nullable)
  - `is_enabled: Mapped[bool]` (Boolean, NOT NULL, `server_default="false"`)
  - `created_at: Mapped[datetime]` (TIMESTAMPTZ, NOT NULL, `server_default=func.now()`)
  - `updated_at: Mapped[datetime]` (TIMESTAMPTZ, NOT NULL, `server_default=func.now()`, `onupdate=func.now()`)
  - `updated_by_user_id: Mapped[int | None]` (BigInteger FK `users.id` ON DELETE SET NULL)
  - `__table_args__` carries the `api_credentials_provider_check` CHECK constraint (`provider IN ('anthropic', 'openai')`).
- **`app/migrations/versions/p3_api_credentials.py`** — single Alembic migration that:
  1. `op.create_table("api_credentials", ...)` mirroring the model exactly (LargeBinary → `bytea`, `sa.false()` server default for `is_enabled`, `sa.func.now()` for the timestamps, FK to `users.id` ON DELETE SET NULL, named CHECK constraint).
  2. `op.bulk_insert` seeds two rows — `{provider:"anthropic",is_enabled:false}` and `{provider:"openai",is_enabled:false}` — every other column defaults to NULL or its server default.
  3. `op.bulk_insert` adds the `encryption_key_primary_fingerprint` row to `app_settings` (`value=None, value_type="null"`, descriptive text citing D-14).
  4. `downgrade()` runs `DELETE FROM app_settings WHERE key = 'encryption_key_primary_fingerprint'` then `op.drop_table("api_credentials")` — exact reverse order.

Revision header: `revision="p3_api_credentials"`, `down_revision="p1_sessions"`. Alembic chain after upgrade: `0001_initial → p1_sessions → p3_api_credentials` (head).

The migration body imports zero from `app.models` (Alembic-safe pattern from `0001_initial.py:222-228`).

### Files modified

- **`app/models/__init__.py`** — added `from app.models.api_credential import ApiCredential`; fully alphabetized `__all__` so downstream agents can rely on the ordering (per plan acceptance criterion).

## Decisions implemented

| ID | Decision | Where it lives |
|----|----------|----------------|
| D-01 | One row per provider, UPDATE on rotation | `provider` is the PK; no `id` column |
| D-02 | `model_name` is a column on `api_credentials`, not `app_settings` | model + migration both carry the column |
| D-03 | `last_four` denormalized | `last_four Text NULL` column |
| D-04 | Migration seeds both providers with `is_enabled=false`, `ciphertext=NULL` | `op.bulk_insert` block 1 |
| D-discretion: provider | Text + CHECK over Postgres ENUM | `sa.CheckConstraint("provider IN ('anthropic','openai')", name="api_credentials_provider_check")` |
| D-discretion: ciphertext | `bytea` (`LargeBinary`) + `Mapped[bytes | None]` | both `Mapped[bytes \| None]` in the model and `sa.LargeBinary` in the migration |

The CHECK constraint name **`api_credentials_provider_check`** is the canonical name downstream plans / tests reference.

## Verification (executed)

| Check | Result |
|-------|--------|
| `python -c "from app.models import ApiCredential"` succeeds | OK |
| `ApiCredential.__tablename__ == "api_credentials"` | OK |
| All 8 columns present on `ApiCredential.__table__` | OK |
| `api_credentials_provider_check` constraint on `__table_args__` | OK |
| `key_ciphertext` column resolves to `LargeBinary` type | OK |
| FK `updated_by_user_id → users.id ON DELETE SET NULL` | OK |
| `alembic upgrade head` on live DB | head now `p3_api_credentials` |
| `\d api_credentials` — 8 columns, types, NOT NULL flags, server defaults | matches the model byte-for-byte |
| 2 seeded rows: `anthropic|f|t`, `openai|f|t` (ciphertext IS NULL) | OK |
| `app_settings` now has 20 rows including `encryption_key_primary_fingerprint` row with `value_type='null'` | OK |
| `alembic downgrade -1` reverses cleanly: table dropped, `app_settings` back to 19 rows, head back to `p1_sessions` | OK |
| `alembic upgrade head` re-runs cleanly after downgrade | OK |
| `python -m pytest tests/test_migrations.py -q` (9 tests) — no regressions | 9 passed |
| Migration body contains no `from app.models` imports (Alembic-safe rule) | OK (Grep confirmed) |
| `ruff check` + `ruff format --check` on all touched files | All checks passed |

## Deviations from Plan

None — plan executed as written. The only non-trivial editorial call was fully alphabetizing `__all__` in `app/models/__init__.py` (the plan acceptance criterion explicitly requires alphabetized order, and the prior file was insertion-ordered; both the new entry and the rest were re-sorted to comply).

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | `f54062b` | `feat(03-01): add ApiCredential SQLAlchemy model + register in models package` |
| 2 | `4b07022` | `feat(03-01): add p3_api_credentials Alembic migration (table + 2 seed rows + fingerprint app_setting)` |

## Downstream handoff notes (for Plans 03-02, 03-03, 03-04)

- Plan 03-02 (encryption primitives) — no schema dependency on this plan; can start in parallel.
- Plan 03-03 (settings service) — `prewarm_cache(db)` will now find the `encryption_key_primary_fingerprint` row with `value_type='null'`; the `get_str` accessor must return `None` for `value_type='null'` (already in the locked D-05 contract).
- Plan 03-04 (credentials service) — UPDATE-only flow lands on the two seeded rows. Provider Literal must be exactly `Literal["anthropic", "openai"]` (matches the CHECK constraint).
- Plan 03-05 / Plan 03-06 (lifespan wiring + tests) — `rewrap_if_needed` will read the new fingerprint row via `settings.get_str("encryption_key_primary_fingerprint")`; first-deploy path (NULL stored fingerprint AND zero populated rows) must be no-op and must NOT write the fingerprint, per CONTEXT `<specifics>`.

## Self-Check: PASSED

- `app/models/api_credential.py` — FOUND
- `app/migrations/versions/p3_api_credentials.py` — FOUND
- `app/models/__init__.py` modified — FOUND (`ApiCredential` in imports and `__all__`)
- Commit `f54062b` — FOUND on branch `worktree-agent-ae1c074d4560ee657`
- Commit `4b07022` — FOUND on branch `worktree-agent-ae1c074d4560ee657`
- DB-level verification (table created, rows seeded, downgrade reverses) — PASSED on live container
