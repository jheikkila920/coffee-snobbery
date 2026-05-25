# Phase 3: Encryption + Settings - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Infrastructure substrate for Phase 7 (AI services) and Phase 9 (Admin). No user-facing UI in this phase. Three deliverables:

1. `app/services/encryption.py` — pure crypto primitives over `cryptography.fernet.MultiFernet`. `encrypt(plaintext: bytes) -> bytes` / `decrypt(ciphertext: bytes) -> bytes`. Constructed from the comma-separated `APP_ENCRYPTION_KEY` env var that Phase 0 already parses (first key = primary for encryption; all keys attempted for decryption). Sentinel encrypt+decrypt round-trip at lifespan startup verifies the constructed `MultiFernet` actually works.
2. `app/services/settings.py` — typed reader over the existing `app_settings` table (Phase 0 already shipped 19 seed rows). Pre-warmed in-memory cache populated at lifespan startup, write-through invalidation, sync DB session via `app/db.py`. Public API is the four typed accessors `get_str / get_int / get_bool / get_json` plus `set_setting(db, key, value, *, by_user_id)`. The Phase 2 raw-SQL call to read `setup_completed` is replaced by `settings.get_bool("setup_completed")` where convenient.
3. `app/services/credentials.py` (new) — CRUD over a new `api_credentials` table that this phase creates (one row per provider, UPDATE on rotation). Defines the `ProviderCredential` frozen+slots dataclass that Phase 7 consumes. `get_provider_credential(db, provider) -> ProviderCredential | None` calls `services.encryption.decrypt()`, never reimplements crypto. `set_provider_credential(db, provider, *, key, model_name, by_user_id)` encrypts via `services.encryption.encrypt()`, writes `last_four` denormalized, emits the `admin.api_credential_set` audit event.

Schema delta this phase ships:
- New `api_credentials` table — columns: `provider` (text PK or unique; values `'anthropic'` and `'openai'`), `key_ciphertext` (bytea, nullable for the seeded empty rows), `last_four` (text, nullable, 4 chars), `model_name` (text, nullable), `is_enabled` (bool NOT NULL DEFAULT false), `created_at` / `updated_at` (timestamptz NOT NULL DEFAULT now()), `updated_by_user_id` (BigInt FK users.id ON DELETE SET NULL). Migration seeds two rows: `('anthropic', NULL, NULL, NULL, false, …)` and `('openai', NULL, NULL, NULL, false, …)`.
- New `app_settings` row: `encryption_key_primary_fingerprint` (value_type='string', initial value NULL via value_type='null'). Used by the auto-rewrap logic at startup.

Lifespan additions in `app/main.py`:
- `encryption.startup_check()` — sentinel round-trip; raises EncryptionStartupError on failure → uvicorn exits non-zero → docker-compose healthcheck flags the container.
- `credentials.rewrap_if_needed(db)` — compares SHA-256 of the current primary key against `app_settings.encryption_key_primary_fingerprint`; on mismatch, re-encrypts every populated `api_credentials.key_ciphertext` under the new primary in one transaction and writes the new fingerprint.
- `settings.prewarm_cache(db)` — single `SELECT * FROM app_settings`; populates the in-process dict.

In scope:
- `services/encryption.py` (pure primitives + startup_check + key-fingerprint helper)
- `services/credentials.py` (api_credentials CRUD + ProviderCredential dataclass + rewrap_if_needed + audit emit)
- `services/settings.py` (typed accessors + cache + set_setting + audit emit + prewarm_cache)
- New `api_credentials` migration + seed rows
- New `app_settings` row (`encryption_key_primary_fingerprint`) migration
- `app/models/api_credential.py` (SQLAlchemy `Mapped[...]` model). **Pydantic models for this table never include the decrypted `api_key` field** (PITFALL SEC-6).
- New event constants in `app/events.py`: `ADMIN_APP_SETTING_CHANGED`, `ADMIN_API_CREDENTIAL_SET`, `ENCRYPTION_DECRYPT_FAILED`, `ENCRYPTION_STARTUP_OK`, `ENCRYPTION_REWRAP_COMPLETED`
- Lifespan wiring in `app/main.py` (3 new calls — startup_check, rewrap_if_needed, prewarm_cache)
- Unit tests: encryption round-trip, key-rotation under MultiFernet, settings cache pre-warm + invalidation, credentials CRUD set/rotate/disabled-provider-returns-None, decrypt-failure event emission, rewrap-when-fingerprint-changes
- The Phase 2 `setup_completed` read site optionally migrates to `settings.get_bool("setup_completed")` (planner judges if it's a clean swap — the `SELECT … FOR UPDATE` lock has to stay; the typed reader is for read-only call sites only)

Out of scope (belongs in later phases):
- Admin UI to set / rotate / enable / disable API credentials — Phase 9 (ADMIN-02)
- Admin UI to edit `app_settings` rows via the `value_type`-driven editor — Phase 9 (ADMIN-03)
- AI service consuming `ProviderCredential` — Phase 7
- Scheduler reading settings (e.g., `last_ai_run_status` write-back) — Phase 8
- Catalog / brew session services consuming settings — Phases 4, 5
- CI grep test for `model_dump()` on `ApiCredential` — Phase 12 per ROADMAP Phase 3 Notes
- API health-panel UI surfacing `last_ai_run_status` — Phase 9

2 requirements mapped: SEC-08, SEC-09.

</domain>

<decisions>
## Implementation Decisions

### api_credentials schema + model_name location

- **D-01: One row per provider, UPDATE on rotation.** PK or `UNIQUE(provider)` constraint on `provider` text column with values `'anthropic'` and `'openai'`. Rotating overwrites `key_ciphertext`, `last_four`, `model_name`, and `updated_at`. No key-history table; household scale doesn't need an audit trail of every old key. Aligns with PROJECT.md row 11 wording ("api_credentials table (admin-managed, Fernet-encrypted keys)").
- **D-02: `model_name` is a column on `api_credentials`, not in `app_settings`.** The Phase 9 admin API-credentials page edits provider+key+model atomically, matching ROADMAP §9 success #2 ("pick a model per provider"). Keeping it on the row avoids a split-brain state where key and chosen model can disagree during rotation. The existing `app_settings` rows `ai_tool_version_anthropic` / `ai_tool_version_openai` continue to hold the **web-search tool version** (a separate concern — tool versions evolve independently of model names).
- **D-03: `last_four` is denormalized on the row, written at set/rotate time.** Phase 9 list page renders the masked key without invoking the encryption service; audit logs and error messages can safely include the masked tail. Tiny consistency cost — `set_provider_credential()` writes `last_four = key[-4:]` in the same UPDATE that writes `key_ciphertext`.
- **D-04: Migration seeds both provider rows with `is_enabled=false, ciphertext=NULL`.** Phase 9 admin form is always an UPDATE; "which providers exist" is locked at the schema layer. Phase 7's provider abstraction reads a known set of rows and decides which are usable based on `is_enabled` AND `key_ciphertext IS NOT NULL`. The NULL-ciphertext branch in `credentials.get_provider_credential()` returns None (same path as `is_enabled=false`).

### Settings reader: cache + coercion + sync/async

- **D-05: Typed accessors public API.** `services/settings.py` exposes `get_str(key) -> str`, `get_int(key) -> int`, `get_bool(key) -> bool`, `get_json(key) -> Any`. Each raises `SettingTypeError` if the row's `value_type` doesn't match the accessor (a typo defense). Also exposes `get_raw(key) -> (value: str | None, value_type: str)` for the Phase 9 admin editor that needs to render arbitrary types. `'null'` rows return `None` from every accessor.
- **D-06: Pre-warm at lifespan startup.** Single `SELECT * FROM app_settings` inside the lifespan block populates a module-level `_cache: dict[str, _CachedSetting]` where `_CachedSetting` is a frozen tuple of `(value: str | None, value_type: str, coerced: Any)`. After warm-up, every accessor is a pure dict lookup — sub-microsecond, no I/O. Single-worker invariant (Phase 0 / Phase 1 D-17) means the cache is consistent across every request.
- **D-07: Sync DB session via `app/db.py`.** Matches the established Phase-4-onward catalog pattern, the future scheduler module, and the Phase 0 D-13 lifespan idiom. Phase 7's async AI service calls `settings.get_int(...)` directly — no `await`, no `run_in_threadpool` — because cache reads are pure CPU. The write path uses the sync `Session` from `app.db.SessionLocal()`; Phase 9 admin (likely sync) writes through directly.
- **D-08: Write-through invalidate + emit `admin.app_setting_changed` event.** `set_setting(db, key, value, *, by_user_id)` validates against the row's stored `value_type`, UPDATEs the row inside a transaction, pops the key from `_cache` (re-loaded on next access), and emits a structured log event `event="admin.app_setting_changed", request_id, user_id, setting_key, old_value_redacted, new_value_redacted, value_type` per Phase 1 D-14 taxonomy. The redaction policy: numeric / boolean / string values are logged verbatim (no secrets in `app_settings`); `json` values are logged with their top-level keys only. Adds `ADMIN_APP_SETTING_CHANGED` constant to `app/events.py`.

### Decrypted-key handoff contract to AI service

- **D-09: Transport object is a frozen+slots `ProviderCredential` dataclass.** Definition in `app/services/credentials.py`:
  ```python
  @dataclass(frozen=True, slots=True)
  class ProviderCredential:
      provider: Literal["anthropic", "openai"]
      key: str  # decrypted; lives only inside the caller's local scope
      model_name: str
      last_four: str
  ```
  Never goes through Pydantic; satisfies PITFALL SEC-6 (`model_dump()` cannot leak `key`). The `key` field type (`str` vs `bytes`) is `str` because both the Anthropic and OpenAI SDKs accept `api_key` as a string. Planner double-checks via Context7 on `anthropic` and `openai` SDK signatures, but this is the expected resolution.
- **D-10: Disabled or missing provider returns `None`.** `get_provider_credential(db, provider) -> ProviderCredential | None`. Returns None when (a) row doesn't exist (shouldn't happen given D-04 seed), (b) `is_enabled=false`, (c) `key_ciphertext IS NULL`, (d) decrypt failed (D-15). Phase 7's provider-fallback logic + cold-start gate already handle None for "render AI not configured" — same path. Avoids forcing Phase 7 into try/except branching.
- **D-11: Sync accessor.** `get_provider_credential(db, provider)` is sync. The work is one cached-table lookup (or one indexed SELECT on a 2-row table) plus one Fernet decrypt — pure CPU, microseconds. The async AI service can call inline without `run_in_threadpool`; threadpool overhead would dominate the operation cost.
- **D-12: Two-module split: `services/encryption.py` (pure crypto) + `services/credentials.py` (CRUD + dataclass + audit).** `encryption.py` exports `encrypt(plaintext: bytes) -> bytes`, `decrypt(ciphertext: bytes) -> bytes`, `primary_key_fingerprint() -> str` (SHA-256 hex of first key in `APP_ENCRYPTION_KEY`), `startup_check()` (sentinel round-trip). `credentials.py` imports `encryption` and is the **only** module that touches `api_credentials` rows. CLAUDE.md's invariant "never bypass `services/encryption.py`" is preserved — `credentials.py` calls into `encryption.py` and never reimplements crypto. Mirrors the Phase 2 `services/auth.py` + `services/setup.py` split (primitives + domain logic).

### Startup validation + rotation mechanics

- **D-13: Sentinel encrypt+decrypt round-trip at lifespan startup.** `encryption.startup_check()` runs `decrypt(encrypt(b"snobbery-startup-check"))`; on success, emits `event="encryption.startup_ok"`; on any exception, raises `EncryptionStartupError` with the underlying cryptography error chained, which propagates out of `lifespan` and exits the process non-zero. Docker-compose healthcheck flips unhealthy. Implements Roadmap success #2 ("absent or malformed `APP_ENCRYPTION_KEY` causes startup to fail loudly"). Catches both the obvious case (malformed base64 → Fernet constructor raises) and subtle runtime mismatches.
- **D-14: Auto-rewrap at lifespan startup when key-fingerprint changes.** Stored in `app_settings.encryption_key_primary_fingerprint` (string row, NULL initially). `credentials.rewrap_if_needed(db)` flow:
  1. Compute SHA-256 of the current primary key.
  2. Read the stored fingerprint via `settings.get_str("encryption_key_primary_fingerprint")` (returns None on first run).
  3. If they match: no-op. If they differ (or stored is None and at least one row has `key_ciphertext IS NOT NULL`): start one transaction, `SELECT key_ciphertext FROM api_credentials WHERE key_ciphertext IS NOT NULL FOR UPDATE`, decrypt each (MultiFernet attempts all keys), re-encrypt under the new primary, UPDATE the row, then `set_setting(db, "encryption_key_primary_fingerprint", new_fp, by_user_id=None)`. Commit. Emit `event="encryption.rewrap_completed", row_count`.
  4. Bounded to ≤2 rows; cost is trivial.
  Operator workflow: prepend new key → restart container → rewrap runs → next deploy can remove the old key from `APP_ENCRYPTION_KEY`. README documents this sequence.
- **D-15: Orphaned ciphertext (no key decrypts) returns `None` + emits `encryption.decrypt_failed`.** Inside `credentials.get_provider_credential()`, a `cryptography.fernet.InvalidToken` exception during `encryption.decrypt()` is caught and translated to: log `event="encryption.decrypt_failed", provider, request_id` and return None. The app stays up; Phase 7 sees "no credential" and renders the graceful AI-not-configured card; admin sees the event in the log stream (and later, in Phase 9, in the API health panel). Manual recovery is to re-set the key via the Phase 9 admin form. Refusing to start the app on this condition is the wrong failure mode — it would lock the admin out of fixing the problem.
- **D-16: Lifespan hook order in `app/main.py`.** Add these three calls inside the existing lifespan startup block (after Phase 0's engine open + Phase 1's middleware stack assembly, before yielding to uvicorn):
  ```python
  # Phase 3 hooks
  encryption.startup_check()                  # raises on bad APP_ENCRYPTION_KEY
  with SessionLocal() as db:
      credentials.rewrap_if_needed(db)        # rotates ciphertexts under new primary
      settings.prewarm_cache(db)              # populates in-process dict
  ```
  All three are synchronous; lifespan is async but `await`-free here is fine. `startup_check` runs first so a bad key fails fast before any DB I/O. `rewrap_if_needed` runs before `prewarm_cache` so the fingerprint write made by rewrap lands in the cache.

### Claude's Discretion

- **`provider` column type** — text with a CHECK constraint (`provider IN ('anthropic', 'openai')`), or Postgres ENUM. Planner picks; text + CHECK is more agile if a third provider lands later. The seed migration inserts exactly the two rows; the CHECK guards typos.
- **`key_ciphertext` column type** — `bytea` (preferred) or `text`. Fernet output is base64-url; storing as `bytea` is type-honest and avoids encoding round-trips. Planner picks.
- **Exact Pydantic schema shapes** for the Phase 9 admin form payload (which Phase 9 will define) — Phase 3 lands the service layer with kwargs (`set_provider_credential(db, provider, *, key, model_name, by_user_id)`); Phase 9 wraps in its own form schema with no `api_key` round-trip field, per SEC-6.
- **Whether to wrap the rewrap transaction in `SELECT … FOR UPDATE`** on each row, or rely on single-worker invariant — planner's call. Belt-and-suspenders FOR UPDATE is cheap and forward-defends a future multi-worker world.
- **Cache datatype** — a plain `dict[str, _CachedSetting]` is fine; `_CachedSetting` shape (NamedTuple vs frozen dataclass) is planner's choice. Thread-safety is not a concern under single-worker + the GIL for atomic dict reads.
- **Audit event payload field naming for `admin.app_setting_changed`** — fields `setting_key`, `old_value`, `new_value`, `value_type`. Planner picks whether to truncate string values to N chars or log full; values are non-sensitive at the `app_settings` level, but a future row with sensitive content would need a redaction list (deferred).
- **Test isolation** — planner picks between (a) `respx`-style mocking the cryptography Fernet (don't — Fernet is too fundamental), or (b) using real keys generated per-test via `Fernet.generate_key()`. Strongly prefer (b); real keys are free and the round-trip tests want real crypto.
- **Whether to use a SQLAlchemy `Mapped[bytes]` or `Mapped[bytes | None]` for `key_ciphertext`** — `Mapped[bytes | None]` because the seeded empty-state rows have NULL. Planner confirms.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` §"Requirements" row 41 ("API keys encrypted at rest via Fernet (`APP_ENCRYPTION_KEY` env var), never logged, only last-4 shown in admin UI"), row 53 ("`api_credentials` table (admin-managed, Fernet-encrypted keys)"), row 54 ("`app_settings` table for runtime-editable settings, seeded with `recommendation_region=US`"), §"Key Decisions" row "MultiFernet from day one, not single Fernet" (rotation-ready encryption is locked at the project level), row "Single uvicorn worker" (the in-memory `settings._cache` is consistent across requests because of this).
- `.planning/REQUIREMENTS.md` §"Security Hardening" SEC-08, SEC-09 — verbatim requirements mapped to this phase.
- `.planning/ROADMAP.md` §"Phase 3: Encryption + Settings" — goal sentence + 4 success criteria + Notes carrying SEC-2 (MultiFernet from day 1) and SEC-6 (no Pydantic model carries decrypted `api_key`; CI grep test for `model_dump\(\)` on `ApiCredential` lands in Phase 12).
- `.planning/STATE.md` — current decision accumulator + the three plan-phase research flags carried forward (Phase 1's Alpine CSP, Phase 7's web-search tool, Phase 10/11). None specific to Phase 3.
- `.planning/phases/00-foundation/00-CONTEXT.md` — Phase 0 D-17 (the 19 seeded `app_settings` rows, including `ai_provider_default`, `ai_tool_version_anthropic`, `ai_tool_version_openai`, `setup_completed`, etc.), D-18 in `<specifics>` (`APP_ENCRYPTION_KEY` is comma-separated; Phase 0 parses to string, Phase 3 builds `MultiFernet([Fernet(k) for k in keys])`).
- `.planning/phases/01-middleware/01-CONTEXT.md` D-14 (audit event taxonomy — Phase 3 extends with `ADMIN_APP_SETTING_CHANGED`, `ADMIN_API_CREDENTIAL_SET`, `ENCRYPTION_DECRYPT_FAILED`, `ENCRYPTION_STARTUP_OK`, `ENCRYPTION_REWRAP_COMPLETED`).
- `.planning/phases/02-auth/02-CONTEXT.md` — Phase 2's raw-SQL read of `setup_completed` is the eventual call site for `settings.get_bool("setup_completed")` (planner judges the swap; the `SELECT … FOR UPDATE` lock stays).

### Research output
- `.planning/research/PITFALLS.md` §5 — SEC-2 (MultiFernet from day one + rotation flow + admin "Rotate API key" button), SEC-6 (`ApiCredential` Pydantic model never includes decrypted `api_key`; transient dataclass passed to AI service; CI test that introspects schemas for forbidden field names — Phase 12 ships the CI test).
- `.planning/research/STACK.md` §1 (`cryptography` pinned `>=48,<49`, `Fernet.fernet`/`MultiFernet` API surface; pydantic-settings `>=2.14,<3.0` for the `APP_ENCRYPTION_KEY` string field already in `app/config.py`).

### Operational + spec
- `CLAUDE.md` §"Stack invariants" (Fernet for API key encryption — locked), §"Architectural invariants" ("AI keys live encrypted in the DB, not env vars. Never bypass `services/encryption.py`."), §"Things to never do silently" ("never bypass the encryption layer for stored API keys"; "never log API keys, passwords, or session tokens").
- `docs/snobbery-gsd-prompt.md` — original product brief; historical reference; CLAUDE.md and `.planning/` docs are authoritative where they diverge.

### External library docs (planner verifies via Context7 in plan-phase)
- `cryptography` (PyPI `>=48,<49`) — `cryptography.fernet.Fernet`, `cryptography.fernet.MultiFernet`, `Fernet.generate_key()`, `InvalidToken` exception surface. Confirm `MultiFernet([Fernet(k1), Fernet(k2)])` decrypts a token encrypted under either key.
- `anthropic` (PyPI `>=0.102,<1.0`) — `Anthropic(api_key=...)` constructor signature: confirm `api_key` is `str`, not `bytes`. Phase 7 is the actual consumer, but D-09 commits to `str` based on the assumption.
- `openai` (PyPI `>=2.37,<3.0`) — `OpenAI(api_key=...)` constructor signature: confirm `api_key` is `str`.
- SQLAlchemy 2.0 — `Mapped[bytes | None]` for `bytea`-backed columns; `mapped_column(LargeBinary, nullable=True)` shape; `Mapped[str]` with `mapped_column(Text)` for the `provider` enum-as-text.
- Alembic 1.18 — `op.create_table` with `bytea`; `op.bulk_insert` for the seed rows (matches the pattern Phase 0's `0001_initial.py` already uses for `app_settings` seeds).

### Existing code (read before changing)
- `app/config.py` — `APP_ENCRYPTION_KEY: str` already declared (raw comma-separated string). Phase 3 parses on use; no schema change to `Settings`. `settings.APP_ENCRYPTION_KEY.split(",")` is the conversion point in `services/encryption.py`.
- `app/db.py` — `SessionLocal` (sync) is what `services/settings.py` and `services/credentials.py` use; `AsyncSessionLocal` is the auth/sessions path, not used by this phase.
- `app/models/app_setting.py` — final schema; this phase consumes (reads + writes) but doesn't migrate.
- `app/models/base.py` — `Base` declarative base for the new `ApiCredential` model.
- `app/events.py` — extend with the five new constants listed in D-08 / D-15 / D-13 / D-14.
- `app/main.py` — lifespan block is the wiring point for D-16; this phase adds three calls.
- `app/migrations/versions/0001_initial.py` — references the existing `app_settings` shape; the new migration follows the same `op.bulk_insert` pattern for seeding the two `api_credentials` rows.
- `app/services/__init__.py` — empty package marker; this phase adds `encryption.py`, `settings.py`, `credentials.py`.
- `app/services/auth.py` + `app/services/setup.py` — Phase 2's service-module template (kwargs API, audit event emission); Phase 3 mirrors the style. Note: Phase 2 services are async; Phase 3 services are sync (D-07, D-11). The pattern is the structural template, not the async/sync choice.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (all already on disk from Phases 0 + 1 + 2)
- **`app.config.settings.APP_ENCRYPTION_KEY`** — string, comma-separated, already parsed from env at startup. Phase 3 splits on `,`, strips whitespace, instantiates `Fernet(k)` per key, wraps in `MultiFernet([...])`. Empty-or-whitespace key list is the malformed case; sentinel round-trip catches it.
- **`app.db.SessionLocal`** — sync sessionmaker bound to the SQLAlchemy 2.0 engine with the pool knobs from Phase 0 D-10 (`pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True, pool_recycle=300`). Both `services/settings.py` and `services/credentials.py` use this.
- **`app.models.app_setting.AppSetting`** — final schema (key PK, value nullable Text, value_type Text, description Text, updated_at TIMESTAMPTZ, updated_by_user_id BigInt FK users.id ON DELETE SET NULL). Phase 3 reads via SQLAlchemy `select()` and writes via `update()`.
- **`app.events`** — module already declares Phase 1 + Phase 2 event constants (`AUTH_LOGIN_SUCCEEDED`, etc.). Phase 3 appends `ADMIN_APP_SETTING_CHANGED`, `ADMIN_API_CREDENTIAL_SET`, `ENCRYPTION_DECRYPT_FAILED`, `ENCRYPTION_STARTUP_OK`, `ENCRYPTION_REWRAP_COMPLETED`. Same string-constant pattern.
- **`app.logging` / structlog setup** — already configured by Phase 0 D-16. Phase 3 code does `log = structlog.get_logger(); log.info(event=ENCRYPTION_STARTUP_OK, ...)` per the project-wide convention.
- **`app.main.lifespan`** — Phase 0 D-13 established the lifespan async context manager; Phase 1 wired middleware into it; Phase 2 added no lifespan calls. Phase 3 adds the three calls listed in D-16.
- **`0001_initial.py` seed pattern** — Phase 0 uses `sa.table()` + `op.bulk_insert()` (lightweight, no ORM dependency inside migrations — Alembic-safe). Phase 3's seed of the two `api_credentials` rows follows the same idiom.

### Established Patterns (set by Phases 0–2; Phase 3 follows)
- **"Stateful logic → services/"** (Phase 0 D-11). Phase 3 lands three service modules.
- **"All env reads go through `app/config.py`"** (Phase 0 establishes; Phase 1 adds CI test `test_no_direct_env.py`). Phase 3's encryption module reads only via `from app.config import settings`.
- **"Migrations are autogenerated from `Mapped[...]` models in `app/models/` via alembic env.py"** (Phase 0). Phase 3 adds `app/models/api_credential.py`; alembic autogenerate detects the new table.
- **"Audit events are structured-logger calls, not custom tables"** (Phase 1 D-14). Phase 3 extends the event taxonomy with five constants.
- **"Never bypass `services/encryption.py`"** (CLAUDE.md). D-12's two-module split is consistent: `credentials.py` *uses* `encryption.py` and never reimplements crypto.
- **"Sync DB for the bulk of CRUD; async DB reserved for the auth surface and the AI calls in Phase 7"** (STACK.md §3.3 + Phase 0 D-10 + Phase 2 contrast). Phase 3 commits to sync (D-07, D-11) because its callers span both sync (catalog, scheduler) and async (AI service); cache-hit reads are sync no matter what.

### Integration Points
- **`app/main.py` lifespan block** — three new sync calls added per D-16, after the engine-open / middleware-assembly already there. No new middleware introduced.
- **`app/migrations/versions/`** — new file (e.g., `p3_api_credentials.py`) creates the table + seeds two rows + adds the `encryption_key_primary_fingerprint` row to `app_settings`. Single migration per Phase 0 D-02 "one migration per logical change".
- **`app/models/api_credential.py`** — NEW file. `Mapped[...]` typed columns matching D-01 schema. Imported by `app/models/__init__.py` so alembic autogenerate sees it.
- **`app/services/encryption.py`** — NEW. Module-level `_multi_fernet: MultiFernet` constructed on first import from `settings.APP_ENCRYPTION_KEY`. Public surface: `encrypt(b: bytes) -> bytes`, `decrypt(b: bytes) -> bytes`, `primary_key_fingerprint() -> str` (hex of SHA-256 of first key string), `startup_check() -> None` (raises `EncryptionStartupError`).
- **`app/services/settings.py`** — NEW. Module-level `_cache: dict[str, _CachedSetting]` (empty until prewarm). Public surface: `prewarm_cache(db)`, `get_str(key)`, `get_int(key)`, `get_bool(key)`, `get_json(key)`, `get_raw(key)`, `set_setting(db, key, value, *, by_user_id)`, `invalidate(key)` (testing hook). Raises `SettingNotFoundError`, `SettingTypeError`.
- **`app/services/credentials.py`** — NEW. Public surface: `get_provider_credential(db, provider) -> ProviderCredential | None`, `set_provider_credential(db, provider, *, key, model_name, by_user_id)`, `set_provider_enabled(db, provider, enabled, *, by_user_id)`, `rewrap_if_needed(db)`. Defines `ProviderCredential` and `Provider = Literal["anthropic", "openai"]`.
- **`app/events.py`** — extends with five new constants (D-08, D-13, D-14, D-15).
- **`tests/`** — new files: `test_encryption.py` (round-trip + rotation + sentinel + InvalidToken), `test_settings.py` (cache prewarm + invalidation + accessor coercion + type-mismatch raise + audit event emit), `test_credentials.py` (set/get/rotate/disabled-returns-None/decrypt-failure-returns-None-and-emits/rewrap-on-fingerprint-change).

</code_context>

<specifics>
## Specific Ideas

- **The `setup_completed` Phase 2 call site stays raw SQL.** Phase 2 reads `setup_completed` via `SELECT value FROM app_settings WHERE key = 'setup_completed' FOR UPDATE`. The typed reader cache doesn't compose with `FOR UPDATE` — `settings.get_bool("setup_completed")` returns the cached value, not the locked row. Planner leaves the Phase 2 raw SQL in place for that one call site. The cached read could still be added for non-locked reads (e.g., the `GET /setup` redirect check) — planner's call.
- **`encryption_key_primary_fingerprint` is a NEW app_settings row added in this phase's migration.** Initial value NULL (`value_type='null'`); the first lifespan-startup of a deployment that has API credentials populated computes and writes it. Empty deploys (no credentials yet) leave it NULL until the admin first sets a key.
- **Rewrap edge case — first deploy with empty credentials.** `rewrap_if_needed` reads the fingerprint (None), counts populated rows (0), no-ops, does NOT write the fingerprint. The fingerprint is only written when the rewrap actually does work, so a future admin who sets a key sees the fingerprint set on the next startup or on the next `set_provider_credential()` call (planner picks the cleaner of the two; both work).
- **`EncryptionStartupError` is a custom exception in `app/services/encryption.py`.** Subclass of `RuntimeError`. Chains the underlying `cryptography.fernet.InvalidToken` or `binascii.Error` so the operator sees the root cause in the structured log.
- **Audit-event payload structure consistency.** Phase 3's events follow the Phase 1 D-14 shape: `event`, `request_id`, `timestamp_iso`, `level`, optional `user_id`. Lifespan-emitted events (`encryption.startup_ok`, `encryption.rewrap_completed`) have no `request_id` (no request context); use `request_id=None` or omit. Phase 1's structlog config handles either — planner verifies.
- **`provider` column values are case-sensitive lowercase.** `'anthropic'` and `'openai'`, never `'Anthropic'`. Enforced by the CHECK constraint and the migration seed. Aligns with the existing `app_settings.ai_provider_default = "anthropic"` row from Phase 0 D-17.
- **Test posture for Phase 3 carries forward to Phase 12 (TEST-03).** Phase 12 owns the formal encryption round-trip + rotation tests; Phase 3 ships test files that satisfy those requirements early so Phase 12's work is verification rather than new coverage. Tests use `Fernet.generate_key()` per test — no shared keys, no `respx`.

</specifics>

<deferred>
## Deferred Ideas

- **Admin UI for setting / rotating / enabling / disabling provider keys** — Phase 9 (ADMIN-02). Phase 3 provides the service-layer functions; Phase 9 wraps them in routes + templates.
- **Admin UI for editing `app_settings` rows** — Phase 9 (ADMIN-03). The `value_type`-driven input renderer consumes `services/settings.get_raw(key)`.
- **CI grep test for `model_dump\(\)` on `ApiCredential`** — Phase 12 (ROADMAP §"Phase 3: Notes" defers this explicitly).
- **API health panel exposing `last_ai_run_status` + decrypt-failure events** — Phase 9 (ADMIN-06). Phase 3 emits the events; Phase 9 reads the log stream or `app_settings.last_ai_run_status` row.
- **Admin "Rotate now" button** — Phase 9. D-14's auto-rewrap covers the common case; an explicit button is convenient but not essential. Revisit if rotation needs to happen without a container restart.
- **`SELECT … FOR UPDATE` on the rewrap transaction** — Claude's discretion at plan-phase. Belt-and-suspenders; cheap; planner picks.
- **A third AI provider (e.g., local Ollama).** Out of scope for v1. Adding it later would require: a third row in `api_credentials`, a new value in the `provider` CHECK constraint (migration), and a new branch in Phase 7's provider abstraction. The Literal type alias and CHECK design are easy to extend.
- **Per-row encryption-version column** for future algorithm migration (e.g., moving from Fernet to AES-GCM). Not in v1; if/when needed, add a `cipher_version` text column with default `'fernet-v1'` and branch in the decrypt path.
- **Bulk re-encrypt utility for non-`api_credentials` tables** (if/when other tables store ciphertext) — would generalize `rewrap_if_needed` into `encryption.rewrap_table(table, column)`. Speculative for now; the only encrypted column in v1 is `api_credentials.key_ciphertext`.
- **`settings.refresh_cache()` admin endpoint for out-of-band SQL edits** — Phase 9 might add this if operator-level psql edits become a workflow. Not needed at v1; the write-through invalidate path covers all in-app edits.
- **Redaction list for `admin.app_setting_changed`** — Phase 3 logs values verbatim because no current `app_settings` row holds sensitive data. If a future row does (e.g., a secret URL), add a per-key redaction config. Speculative.

</deferred>

---

*Phase: 3-Encryption + Settings*
*Context gathered: 2026-05-18*
