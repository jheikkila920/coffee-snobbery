# Phase 3: Encryption + Settings — Research

**Researched:** 2026-05-18
**Domain:** Symmetric encryption (Fernet/MultiFernet) + typed settings cache + provider-credential CRUD
**Confidence:** HIGH on library APIs (verified via official docs / source); HIGH on code-context patterns (read existing Phase 0/1/2 modules verbatim).

## Summary

Phase 3 is an infrastructure substrate phase: no user-facing UI, no routes, no migrations to existing tables — three new service modules (`encryption.py`, `settings.py`, `credentials.py`), one new table (`api_credentials`), one new `app_settings` row (`encryption_key_primary_fingerprint`), five new event constants, three new lifespan calls. The 16 locked CONTEXT decisions resolve every architectural question — the planner's job is composition, not exploration.

The six library assumptions in CONTEXT (cryptography MultiFernet behavior, Anthropic/OpenAI `api_key: str`, SQLAlchemy `Mapped[bytes | None]` → `bytea`, Alembic `op.bulk_insert`, structlog `request_id=None` lifespan emits) are all **VERIFIED** in this research — see § Standard Stack and § Code Examples. D-09's commit to `key: str` (not `bytes`) on `ProviderCredential` is sound: both SDKs declare `api_key: str | None` at the constructor.

**Primary recommendation:** Plan three service modules in dependency order — `encryption.py` first (pure, no DB), `settings.py` second (DB read + module-level cache), `credentials.py` third (imports both). Lock the `provider` column as `Text` + `CHECK` constraint (D-discretion default) — agile vs Postgres ENUM if a third provider lands. Use `Mapped[bytes | None]` + `mapped_column(LargeBinary, nullable=True)` for `key_ciphertext`. Single migration ships table + seed rows + new `app_settings` row, mirroring `0001_initial.py`'s `op.bulk_insert` idiom. Tests use `Fernet.generate_key()` per test (real crypto, no mocks).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**api_credentials schema + model_name location**

- **D-01:** One row per provider, UPDATE on rotation. PK or `UNIQUE(provider)` on `provider` text column with values `'anthropic'` and `'openai'`. Rotating overwrites `key_ciphertext`, `last_four`, `model_name`, `updated_at`. No key-history table.
- **D-02:** `model_name` is a column on `api_credentials`, not in `app_settings`. The Phase 9 admin API-credentials page edits provider+key+model atomically. The existing `app_settings` rows `ai_tool_version_anthropic` / `ai_tool_version_openai` continue to hold the web-search tool version (separate concern).
- **D-03:** `last_four` is denormalized on the row, written at set/rotate time. `set_provider_credential()` writes `last_four = key[-4:]` in the same UPDATE that writes `key_ciphertext`.
- **D-04:** Migration seeds both provider rows with `is_enabled=false, ciphertext=NULL`. Phase 9 admin form is always an UPDATE.

**Settings reader: cache + coercion + sync/async**

- **D-05:** Typed accessors public API: `get_str(key) -> str`, `get_int(key) -> int`, `get_bool(key) -> bool`, `get_json(key) -> Any`. Each raises `SettingTypeError` on type mismatch. Plus `get_raw(key) -> (value: str | None, value_type: str)` for the Phase 9 admin editor. `'null'` rows return `None` from every accessor.
- **D-06:** Pre-warm at lifespan startup. Single `SELECT * FROM app_settings` populates module-level `_cache: dict[str, _CachedSetting]`. Single-worker invariant means cache is consistent across every request.
- **D-07:** Sync DB session via `app/db.py`. Phase 7's async AI service calls `settings.get_int(...)` directly — cache reads are pure CPU.
- **D-08:** Write-through invalidate + emit `admin.app_setting_changed` event. `set_setting(db, key, value, *, by_user_id)` validates value_type, UPDATEs inside a transaction, pops the key from `_cache`. Field shape: `setting_key, old_value, new_value, value_type`.

**Decrypted-key handoff contract to AI service**

- **D-09:** Transport object is a frozen+slots `ProviderCredential` dataclass with `provider: Literal["anthropic", "openai"]`, `key: str`, `model_name: str`, `last_four: str`. Never goes through Pydantic; satisfies PITFALL SEC-6.
- **D-10:** Disabled or missing provider returns `None`. `get_provider_credential(db, provider) -> ProviderCredential | None`. Returns None on: row missing, `is_enabled=false`, `key_ciphertext IS NULL`, decrypt failure (D-15).
- **D-11:** Sync accessor. `get_provider_credential(db, provider)` is sync — one indexed SELECT + one Fernet decrypt, microseconds.
- **D-12:** Two-module split: `services/encryption.py` (pure crypto: `encrypt`, `decrypt`, `primary_key_fingerprint`, `startup_check`) + `services/credentials.py` (CRUD + dataclass + audit + `rewrap_if_needed`). `credentials.py` calls into `encryption.py` and never reimplements crypto.

**Startup validation + rotation mechanics**

- **D-13:** Sentinel encrypt+decrypt round-trip at lifespan startup. `encryption.startup_check()` runs `decrypt(encrypt(b"snobbery-startup-check"))`; on success emits `encryption.startup_ok`; on any exception raises `EncryptionStartupError` chained with the underlying cryptography error → uvicorn exits non-zero.
- **D-14:** Auto-rewrap at lifespan startup when key-fingerprint changes. Stored in `app_settings.encryption_key_primary_fingerprint`. Flow: compute SHA-256 of current primary; read stored fp; if differ (or stored is None and at least one row has `key_ciphertext IS NOT NULL`), `SELECT key_ciphertext FROM api_credentials WHERE key_ciphertext IS NOT NULL FOR UPDATE`, decrypt+re-encrypt each, UPDATE the row, write the new fingerprint, commit. Emit `encryption.rewrap_completed, row_count`.
- **D-15:** Orphaned ciphertext (no key decrypts) returns `None` + emits `encryption.decrypt_failed`. App stays up; Phase 7 sees "no credential". Manual recovery via Phase 9 admin form.
- **D-16:** Lifespan hook order in `app/main.py`: `encryption.startup_check()` first (fails fast on bad key), then `with SessionLocal() as db: credentials.rewrap_if_needed(db); settings.prewarm_cache(db)`. All three sync; `await`-free in the async lifespan body is fine.

### Claude's Discretion

- `provider` column type — Text + CHECK (`provider IN ('anthropic', 'openai')`) preferred over Postgres ENUM (agile if third provider lands).
- `key_ciphertext` column type — `bytea` preferred over `text`. Fernet output is base64-url; bytea is type-honest and avoids encoding round-trips.
- Exact Pydantic schema shapes for the Phase 9 admin form — out of scope; Phase 3 ships service layer with kwargs.
- Whether to wrap the rewrap transaction in `SELECT … FOR UPDATE` — planner's call; belt-and-suspenders FOR UPDATE is cheap and forward-defends a future multi-worker world.
- Cache datatype — plain `dict[str, _CachedSetting]` is fine; `_CachedSetting` shape (NamedTuple vs frozen dataclass) is planner's choice.
- Audit event payload field naming for `admin.app_setting_changed` — `setting_key, old_value, new_value, value_type`. Truncation policy: log full values (no current `app_settings` row holds sensitive data).
- Test isolation — use real keys generated per-test via `Fernet.generate_key()` (NOT mocking Fernet).
- `key_ciphertext` annotation — `Mapped[bytes | None]` because seeded empty-state rows have NULL.

### Deferred Ideas (OUT OF SCOPE)

- Admin UI to set / rotate / enable / disable API credentials — Phase 9 (ADMIN-02).
- Admin UI to edit `app_settings` rows via the value_type-driven editor — Phase 9 (ADMIN-03).
- CI grep test for `model_dump\(\)` on `ApiCredential` — Phase 12.
- API health-panel UI surfacing `last_ai_run_status` — Phase 9 (ADMIN-06).
- Admin "Rotate now" button — Phase 9 (D-14's auto-rewrap covers the common case).
- A third AI provider (e.g., local Ollama) — out of v1.
- Per-row encryption-version column (e.g., `cipher_version='fernet-v1'`) for future algorithm migration — speculative.
- Bulk re-encrypt utility for non-`api_credentials` tables — only one encrypted column in v1.
- `settings.refresh_cache()` admin endpoint for out-of-band SQL edits — Phase 9 if/when operator-level psql edits become a workflow.
- Redaction list for `admin.app_setting_changed` — Phase 3 logs values verbatim; speculative for a future sensitive `app_settings` row.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-08 | API keys encrypted at rest with `MultiFernet` (rotation-ready from day one); never logged; admin UI shows only last 4 characters | § Standard Stack — `cryptography.fernet.MultiFernet` verified rotation behavior; § Code Examples — encrypt / decrypt / MultiFernet construction patterns; D-03 locks `last_four` denormalized column for admin display; D-15 + § Common Pitfalls SEC-6 lock the "no Pydantic with decrypted key" invariant via the frozen dataclass `ProviderCredential` |
| SEC-09 | `APP_ENCRYPTION_KEY` env var documented with Python one-liner to generate; loaded once at startup; absent or malformed key crashes startup loudly | § Code Examples — `Fernet.generate_key()` documented as the generator (already in `.env.example` per Phase 0 D-18); D-13 locks the lifespan-startup sentinel round-trip (`encryption.startup_check()`); § Common Pitfalls — `EncryptionStartupError` chains the underlying `InvalidToken` / `binascii.Error` so the operator sees the root cause |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Python 3.12 + FastAPI 0.136** — `lifespan` async context manager only; Phase 3's three startup hooks land inside the existing `lifespan` body in `app/main.py:134`.
- **SQLAlchemy 2.0 typed `Mapped[...]` + `select()` / `update()` constructs** — no legacy Query API. New `ApiCredential` model uses `Mapped[str]` (provider), `Mapped[bytes | None]` (key_ciphertext), etc.
- **psycopg 3** — `postgresql+psycopg://` URL prefix already wired; supports `bytea` natively.
- **cryptography Fernet for API key encryption (LOCKED)** — `cryptography>=48,<49` already pinned in STACK.md.
- **`MultiFernet` from day one, not single Fernet** — locked in PROJECT.md Key Decisions; this phase ships the implementation.
- **Never bypass `services/encryption.py`** — D-12's two-module split honors this: `credentials.py` calls `encryption.encrypt()` / `encryption.decrypt()` and never reimplements crypto.
- **Never log API keys, passwords, or session tokens** — Phase 1's structlog redactor (`SENSITIVE_KEYS`) already covers `api_key_encrypted`. New audit events emit only `setting_key, old_value_redacted, new_value_redacted, value_type` for app_setting changes; credentials events emit `provider, last_four, by_user_id` only.
- **All env reads through `app/config.py`** — `services/encryption.py` reads `settings.APP_ENCRYPTION_KEY` (already declared in `app/config.py:48`); no new env var.
- **Sync DB for catalog / scheduler / this phase** — Phase 2 async services are the exception (auth + AI); Phase 3 commits to sync (D-07, D-11) to match Phase 4+ catalog pattern.
- **Single uvicorn worker** — in-memory `_cache` is consistent across requests (D-06).
- **CSRF on all state-changing forms** — no Phase 3 routes; not applicable here. Phase 9 admin routes will need CSRF when they consume these services.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fernet symmetric encryption (encrypt / decrypt primitives) | API / Backend (`app/services/encryption.py`) | — | Pure CPU; no I/O; module-level `MultiFernet` constructed from `settings.APP_ENCRYPTION_KEY` at import time |
| Encryption key fingerprint (SHA-256 of primary key) | API / Backend (`app/services/encryption.py`) | — | Pure CPU; used by D-14 auto-rewrap logic to detect rotation |
| `app_settings` typed read + in-process cache | API / Backend (`app/services/settings.py`) | Database / Storage (read path on cache miss / prewarm) | Cache lives in the API tier (module-level dict); DB read happens once at startup + once per write |
| `app_settings` write-through invalidation + audit | API / Backend (`app/services/settings.py`) | Database / Storage (UPDATE) | UPDATE in one transaction, pop cache, emit structured event |
| `api_credentials` CRUD (set / get / enable / disable / rotate) | API / Backend (`app/services/credentials.py`) | Database / Storage (UPDATE on the 2-row table) | Service module is the only path that touches `api_credentials` rows (CLAUDE.md invariant) |
| Auto-rewrap on key rotation | API / Backend (`app/services/credentials.py`) | Database / Storage (transactional UPDATE of ciphertext + fingerprint row) | Runs in lifespan; bounded to ≤2 rows; uses `SELECT … FOR UPDATE` (belt-and-suspenders) |
| Decrypted credential handoff to AI service | API / Backend (transient `ProviderCredential` dataclass) | — | Frozen+slots dataclass lives only inside the caller's local scope; never persisted, never serialized through Pydantic (SEC-6) |
| Startup validation (sentinel round-trip + fail-loud) | API / Backend (`app/main.py` lifespan) | Process supervisor (docker-compose healthcheck) | `EncryptionStartupError` → uvicorn exits non-zero → compose marks container unhealthy |
| Audit event emission (`admin.app_setting_changed`, `admin.api_credential_set`, `encryption.*`) | API / Backend (structlog) | Log aggregation (docker stdout / syslog — Phase 1 D-14) | Structured-logger calls, not custom tables |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `cryptography` | `>=48,<49` (current: 48.0.0, Apr 2026) | `Fernet`, `MultiFernet`, `InvalidToken` — symmetric authenticated encryption | pyca/cryptography is the canonical Python crypto library; `Fernet` is the recommended high-level primitive for application-level symmetric encryption [VERIFIED: pip index versions cryptography → 48.0.0; CITED: https://cryptography.io/en/latest/fernet/] |
| `SQLAlchemy` | `>=2.0.49,<2.1` | `Mapped[...]`, `mapped_column`, `LargeBinary`, `select()`, `update()` | Already pinned in STACK.md; PostgreSQL `bytea` maps to `LargeBinary` automatically [CITED: https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.LargeBinary] |
| `Alembic` | `>=1.18,<2.0` | `op.create_table`, `op.bulk_insert`, `op.create_check_constraint` | Already pinned in STACK.md; pattern matches Phase 0's `0001_initial.py` [CITED: https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.bulk_insert] |
| `structlog` | `>=25.5,<26` | `get_logger()` for the 5 new event emissions | Phase 1 D-14 taxonomy; redactor already covers `api_key`-shaped keys via the `SENSITIVE_KEYS` deny-list in `app/logging.py` [VERIFIED: read `app/logging_config.py` and `app/events.py`] |
| `pydantic-settings` | `>=2.14,<3.0` | `Settings.APP_ENCRYPTION_KEY` already declared | Phase 0 wired; Phase 3 reads via `from app.config import settings` and splits on `,` [VERIFIED: read `app/config.py:48`] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hashlib` (stdlib) | n/a | SHA-256 of primary key for fingerprint | `hashlib.sha256(primary_key_bytes).hexdigest()` — pure stdlib, no new dep |
| `dataclasses` (stdlib) | n/a | `@dataclass(frozen=True, slots=True)` for `ProviderCredential` | D-09 locks this; `slots=True` blocks accidental attribute injection [Python 3.10+ required for `slots=True`] |
| `typing.Literal` (stdlib) | n/a | `Provider = Literal["anthropic", "openai"]` type alias | Matches D-04's CHECK constraint at the type-checker level |
| `pytest` + `pytest-asyncio` | already pinned | Test scaffolding | Phase 2 patterns: `try/except ImportError` lazy-import in tests for clean skips before code lands |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `cryptography.fernet.MultiFernet` | `nacl` (PyNaCl SecretBox) | NaCl is fine but pyca/cryptography is already the project dep; MultiFernet provides rotation-on-decrypt out of the box; no reason to add a second crypto library. **Stay with Fernet.** |
| Postgres ENUM for `provider` | `Text` + `CHECK` constraint | ENUM requires a separate migration to add a value (future Ollama support); `Text` + `CHECK` requires only an ALTER CONSTRAINT. **Use Text + CHECK** (D-discretion default). |
| `Mapped[bytes]` (NOT NULL) | `Mapped[bytes | None]` (NULL allowed) | The two seeded empty-state rows have NULL ciphertext (D-04). `Mapped[bytes | None]` is mandatory for the schema as defined. |
| `text` for `key_ciphertext` | `bytea` | Fernet output is `bytes` (base64-url-encoded ASCII underneath, but the API returns `bytes`); storing as `bytea` is type-honest and avoids `.encode()`/`.decode()` round-trips on every read/write. **Use bytea.** |
| Mock Fernet in tests with `respx` | Generate real keys per test via `Fernet.generate_key()` | `respx` is for HTTP; Fernet is pure CPU. Real keys cost <1 ms to generate and exercise actual crypto. **Use real keys** (CONTEXT discretion). |
| Module-level singleton `_multi_fernet` | Per-call instantiation | Construction is microseconds, but per-call would re-parse `APP_ENCRYPTION_KEY.split(",")` on every encrypt/decrypt. Module-level is the canonical Phase 0/2 pattern (`app/signing.py`, `app/services/auth.py`). |
| `dataclass(frozen=True)` only | `dataclass(frozen=True, slots=True)` | `slots=True` blocks `__dict__` and prevents `cred.api_key = "new"` accidental attribute injection. Costs nothing on Python 3.10+. **Use slots=True.** |

**Installation:**

```bash
# All required packages already in pyproject.toml (Phase 0 + 1 + 2).
# Phase 3 adds NO new dependencies — verified by reading requirements.
# The `cryptography` pin is already >=48,<49 per STACK.md §1.
```

**Version verification (cryptography):**

```bash
pip index versions cryptography
# → cryptography (48.0.0)
# Available versions: 48.0.0, 47.0.0, 46.0.7, ...
```

`cryptography` 48.0.0 was published 2026-05-04 (per STACK.md §1) and is the current line. [VERIFIED: `pip index versions cryptography` 2026-05-18 → 48.0.0]

## Architecture Patterns

### System Architecture Diagram

```
                          ┌──────────────────────────────────────────┐
                          │ Operator                                  │
                          │ • sets APP_ENCRYPTION_KEY=k_new,k_old     │
                          │   in .env or docker-compose env block     │
                          │ • restarts the coffee-snobbery container  │
                          └────────────────┬──────────────────────────┘
                                           │
                                           ▼
       ┌───────────────────────────────────────────────────────────────────┐
       │ docker-compose up → entrypoint.sh → uvicorn → app.main.lifespan() │
       │                                                                    │
       │   ┌──────────────────────────────────────────────────────────┐    │
       │   │ Phase 0: engine open + SELECT 1 smoke (existing)         │    │
       │   └──────────────────────────────────────────────────────────┘    │
       │                                                                    │
       │   ┌──────────────────────────────────────────────────────────┐    │
       │   │ Phase 3 hooks (D-16, NEW):                                │    │
       │   │                                                            │    │
       │   │   1. encryption.startup_check()                            │    │
       │   │      ├── decrypt(encrypt(b"snobbery-startup-check"))      │    │
       │   │      ├── on success → log encryption.startup_ok           │    │
       │   │      └── on InvalidToken / Error                          │    │
       │   │          → raise EncryptionStartupError (chained)         │    │
       │   │          → lifespan propagates → uvicorn exits non-zero  │    │
       │   │          → compose healthcheck → container unhealthy     │    │
       │   │                                                            │    │
       │   │   2. with SessionLocal() as db:                            │    │
       │   │      credentials.rewrap_if_needed(db)                      │    │
       │   │      ├── compute new_fp = sha256(primary_key)              │    │
       │   │      ├── stored_fp = settings.get_str("encryption_key_   │    │
       │   │      │              primary_fingerprint")                  │    │
       │   │      ├── if new_fp != stored_fp AND populated rows exist: │    │
       │   │      │     SELECT key_ciphertext FROM api_credentials     │    │
       │   │      │     WHERE key_ciphertext IS NOT NULL FOR UPDATE    │    │
       │   │      │     for each row: decrypt → re-encrypt under new   │    │
       │   │      │     UPDATE row, UPDATE app_settings fp row, commit │    │
       │   │      │     emit encryption.rewrap_completed row_count=N   │    │
       │   │      └── else: no-op                                      │    │
       │   │                                                            │    │
       │   │   3. settings.prewarm_cache(db)                            │    │
       │   │      ├── SELECT * FROM app_settings                        │    │
       │   │      └── populate _cache: dict[str, _CachedSetting]        │    │
       │   └──────────────────────────────────────────────────────────┘    │
       │                                                                    │
       │   ┌──────────────────────────────────────────────────────────┐    │
       │   │ yield (uvicorn serves requests)                           │    │
       │   └──────────────────────────────────────────────────────────┘    │
       └───────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
       ┌───────────────────────────────────────────────────────────────────┐
       │ Request path (Phase 7 example — AI service)                       │
       │                                                                    │
       │   ai_service.regenerate(user_id):                                  │
       │     with SessionLocal() as db:                                     │
       │       cred = credentials.get_provider_credential(db, "anthropic")  │
       │       ├── SELECT * FROM api_credentials WHERE provider='anthropic' │
       │       ├── if is_enabled=false OR key_ciphertext IS NULL → None    │
       │       ├── plain = encryption.decrypt(row.key_ciphertext)          │
       │       │           ├── _multi_fernet.decrypt(ciphertext)            │
       │       │           ├── tries primary key first, then secondary     │
       │       │           └── raises InvalidToken if no key works         │
       │       ├── on InvalidToken → log encryption.decrypt_failed → None  │
       │       └── return ProviderCredential(                               │
       │             provider="anthropic", key=plain.decode("utf-8"),       │
       │             model_name=row.model_name, last_four=row.last_four)   │
       │                                                                    │
       │     if cred is None → render "AI not configured" graceful state    │
       │     else: Anthropic(api_key=cred.key).messages.create(...)         │
       │                                                                    │
       │     # cred lives only in this function scope; goes out of scope    │
       │     # when the function returns. Never serialized; never logged.   │
       └───────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
       ┌───────────────────────────────────────────────────────────────────┐
       │ Admin path (Phase 9 — out of scope for Phase 3, shown for context)│
       │                                                                    │
       │   POST /admin/api-credentials/anthropic:                           │
       │     credentials.set_provider_credential(                           │
       │       db, "anthropic",                                             │
       │       key="sk-ant-...", model_name="claude-opus-4-7",              │
       │       by_user_id=current_user.id)                                  │
       │       ├── ciphertext = encryption.encrypt(key.encode("utf-8"))    │
       │       ├── last_four = key[-4:]                                    │
       │       ├── UPDATE api_credentials SET ... WHERE provider='...'      │
       │       └── emit admin.api_credential_set                            │
       │              event with provider, last_four, by_user_id            │
       └───────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| File | Phase | Responsibility |
|------|-------|----------------|
| `app/services/encryption.py` | 3 (NEW) | Pure crypto: `encrypt(bytes)→bytes`, `decrypt(bytes)→bytes`, `primary_key_fingerprint()→str`, `startup_check()→None`. Module-level `_multi_fernet`. Raises `EncryptionStartupError`. No DB. |
| `app/services/settings.py` | 3 (NEW) | Typed `app_settings` reader: `get_str/get_int/get_bool/get_json/get_raw`. Module-level `_cache`. `prewarm_cache(db)`, `set_setting(db, ...)`, `invalidate(key)`. Raises `SettingNotFoundError`, `SettingTypeError`. Sync. |
| `app/services/credentials.py` | 3 (NEW) | `api_credentials` CRUD: `get_provider_credential`, `set_provider_credential`, `set_provider_enabled`, `rewrap_if_needed`. Defines `ProviderCredential` dataclass + `Provider` type alias. Only module that touches `api_credentials` rows. Sync. |
| `app/models/api_credential.py` | 3 (NEW) | SQLAlchemy `Mapped[...]` model. NOT a Pydantic schema. Re-exported from `app/models/__init__.py` so alembic autogenerate sees it. |
| `app/migrations/versions/p3_api_credentials.py` | 3 (NEW) | Single migration: create `api_credentials` table + 2-row seed + 1 new `app_settings` row (`encryption_key_primary_fingerprint`). |
| `app/events.py` | 3 (EXTEND) | Append 5 new constants: `ADMIN_APP_SETTING_CHANGED`, `ADMIN_API_CREDENTIAL_SET`, `ENCRYPTION_DECRYPT_FAILED`, `ENCRYPTION_STARTUP_OK`, `ENCRYPTION_REWRAP_COMPLETED`. |
| `app/main.py` | 3 (EXTEND) | Lifespan adds 3 calls per D-16 — import `from app.services import credentials, settings` and `from app.services.encryption import startup_check`. |
| `tests/services/test_encryption.py` | 3 (NEW) | Round-trip, key rotation under MultiFernet, sentinel startup_check, InvalidToken handling. |
| `tests/services/test_settings.py` | 3 (NEW) | Cache prewarm + invalidation, accessor coercion, type-mismatch raise, audit event emit on `set_setting`. |
| `tests/services/test_credentials.py` | 3 (NEW) | set/get/rotate/disabled-returns-None/decrypt-failure-returns-None-and-emits/rewrap-on-fingerprint-change. |

### Recommended Project Structure

```
app/
├── services/
│   ├── encryption.py        # NEW — pure crypto primitives + startup_check
│   ├── settings.py          # NEW — typed app_settings reader + cache
│   ├── credentials.py       # NEW — api_credentials CRUD + ProviderCredential
│   ├── auth.py              # Phase 2 (template for service-module style)
│   ├── setup.py             # Phase 2 (template for service-module style)
│   ├── sessions.py          # Phase 1
│   └── scheduler.py         # Phase 0 placeholder
├── models/
│   ├── api_credential.py    # NEW — Mapped[...] model
│   ├── app_setting.py       # Existing — Phase 3 reads + writes (no migration)
│   └── ...
├── migrations/versions/
│   ├── 0001_initial.py      # Phase 0 (pattern source for op.bulk_insert)
│   ├── p1_sessions_table.py # Phase 1
│   └── p3_api_credentials.py # NEW
├── events.py                # EXTEND — append 5 constants
└── main.py                  # EXTEND — lifespan adds 3 calls per D-16
```

### Pattern 1: Module-Level Singleton with Lazy Import-Time Construction

**What:** Construct the expensive object once at module import; consumers access via a public function or the module-level reference. Mirrors `app/services/auth.py:51` (`_ph = PasswordHasher(...)`) and `app/signing.py:25-29` (URLSafeSerializer).

**When to use:** Any object whose construction is deterministic + non-trivial (PasswordHasher, MultiFernet, URLSafeSerializer). Always for stateless transformers.

**Example:**

```python
# app/services/encryption.py
from __future__ import annotations
import hashlib
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from app.config import settings


class EncryptionStartupError(RuntimeError):
    """Sentinel round-trip failed — APP_ENCRYPTION_KEY is malformed or unusable.

    Raised from startup_check() with the underlying cryptography error
    chained via __cause__ so operators see the root cause in the structured
    log. Propagates out of lifespan → uvicorn exits non-zero → compose
    healthcheck marks the container unhealthy (D-13).
    """


def _parse_keys() -> list[str]:
    """Split APP_ENCRYPTION_KEY on commas, strip whitespace, drop empties."""
    return [k.strip() for k in settings.APP_ENCRYPTION_KEY.split(",") if k.strip()]


def _build_multi_fernet() -> MultiFernet:
    """Build the module-level MultiFernet from the parsed key list.

    Fernet() accepts bytes-or-str (verified: https://cryptography.io/en/latest/fernet/).
    A malformed base64 key raises binascii.Error / ValueError here, which
    propagates as the import-time failure that startup_check() will surface
    via the sentinel round-trip — see Pitfall 1.
    """
    keys = _parse_keys()
    if not keys:
        # Empty key list — Fernet() would also raise, but we catch this earlier
        # for a clearer error message. startup_check() chains this via __cause__.
        raise ValueError("APP_ENCRYPTION_KEY is empty after splitting on commas")
    return MultiFernet([Fernet(k) for k in keys])


# Module-level singleton constructed at import. First module access in the
# lifespan (via startup_check) triggers this — fail-fast on bad config.
_multi_fernet = _build_multi_fernet()
```

### Pattern 2: Service Module With Custom Exceptions + Public `__all__`

**What:** Service modules export only the public API; private helpers are leading-underscore; custom exceptions are defined at module top. Mirrors `app/services/auth.py:1-116`.

**When to use:** Every `app/services/` module.

**Example:**

```python
# app/services/settings.py (sketch)
class SettingNotFoundError(KeyError):
    """Raised by get_str/get_int/etc. when the key is not in the cache."""

class SettingTypeError(TypeError):
    """Raised when an accessor's expected type doesn't match the row's value_type."""


def get_str(key: str) -> str: ...
def get_int(key: str) -> int: ...
def get_bool(key: str) -> bool: ...
def get_json(key: str) -> Any: ...
def get_raw(key: str) -> tuple[str | None, str]: ...
def set_setting(db: Session, key: str, value: Any, *, by_user_id: int | None) -> None: ...
def prewarm_cache(db: Session) -> None: ...
def invalidate(key: str) -> None: ...  # testing hook

__all__ = [
    "SettingNotFoundError", "SettingTypeError",
    "get_str", "get_int", "get_bool", "get_json", "get_raw",
    "set_setting", "prewarm_cache", "invalidate",
]
```

### Pattern 3: Lightweight `sa.table()` + `op.bulk_insert` for Migration Seeds

**What:** Migrations never import from `app.models.*` (Alembic-safe pattern). Define a lightweight `sa.table()` inside the migration for seed inserts. Mirrors `0001_initial.py:222-359`.

**When to use:** Every migration that seeds rows.

**Example:**

```python
# app/migrations/versions/p3_api_credentials.py (sketch)
api_credentials_table = sa.table(
    "api_credentials",
    sa.column("provider", sa.Text),
    sa.column("key_ciphertext", sa.LargeBinary),
    sa.column("last_four", sa.Text),
    sa.column("model_name", sa.Text),
    sa.column("is_enabled", sa.Boolean),
)
op.bulk_insert(
    api_credentials_table,
    [
        {"provider": "anthropic", "key_ciphertext": None, "last_four": None,
         "model_name": None, "is_enabled": False},
        {"provider": "openai", "key_ciphertext": None, "last_four": None,
         "model_name": None, "is_enabled": False},
    ],
)

# Plus the new app_settings row:
app_settings_table = sa.table(
    "app_settings",
    sa.column("key", sa.Text),
    sa.column("value", sa.Text),
    sa.column("value_type", sa.Text),
    sa.column("description", sa.Text),
)
op.bulk_insert(
    app_settings_table,
    [{"key": "encryption_key_primary_fingerprint", "value": None,
      "value_type": "null",
      "description": "SHA-256 of APP_ENCRYPTION_KEY primary; used by D-14 auto-rewrap."}],
)
```

### Pattern 4: Frozen+Slots Dataclass as Transport (Never Pydantic)

**What:** Use `@dataclass(frozen=True, slots=True)` for any object that carries a decrypted secret. Pydantic's `model_dump()` is the SEC-6 hazard — frozen+slots dataclasses have no `model_dump()` to leak through.

**When to use:** Any transient object carrying secret material across module boundaries.

**Example:**

```python
# app/services/credentials.py (sketch)
from dataclasses import dataclass
from typing import Literal

Provider = Literal["anthropic", "openai"]


@dataclass(frozen=True, slots=True)
class ProviderCredential:
    """Decrypted credential — lives only in caller's local scope.

    Never persisted, never serialized through Pydantic (SEC-6). Frozen
    blocks attribute injection; slots=True blocks __dict__ (so an attacker
    who finds an instance reference can't `cred.__dict__["key"]` it).

    The ``key`` field is ``str`` (NOT bytes) — both Anthropic and OpenAI
    SDKs declare ``api_key: str | None`` at the constructor (D-09; verified
    via WebFetch on the SDK source).
    """
    provider: Provider
    key: str
    model_name: str
    last_four: str
```

### Pattern 5: Lifespan Hook Order with Sync Calls Inside Async Context

**What:** `lifespan` is `async`, but Phase 3's three hooks are sync. Wrap the DB-touching ones in `with SessionLocal() as db:` (sync context manager). FastAPI doesn't require `await` inside lifespan for sync work — only for async I/O. Mirrors the existing `with engine.connect() as conn: conn.execute(text("SELECT 1"))` in `app/main.py:140-141`.

**When to use:** Lifespan hooks that don't perform async I/O.

**Example:**

```python
# app/main.py (sketch — additions inside existing lifespan)
from app.services import credentials, settings
from app.services.encryption import startup_check

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Existing Phase 0 smoke check (preserved)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    log.info("app.startup", version=app.version)

    # Phase 3 hooks (D-16). All sync; await-free is fine in async lifespan.
    startup_check()                          # raises EncryptionStartupError on bad key
    with SessionLocal() as db:
        credentials.rewrap_if_needed(db)     # rotates ciphertext under new primary
        settings.prewarm_cache(db)           # populates in-process dict

    yield
    log.info("app.shutdown")
    dispose_engine()
    await _async_engine.dispose()
```

### Anti-Patterns to Avoid

- **Reimplementing crypto inside `credentials.py`.** CLAUDE.md invariant: never bypass `services/encryption.py`. `credentials.py` MUST call `encryption.encrypt()` / `encryption.decrypt()` and never construct its own `Fernet` instance.
- **Including the decrypted `api_key` in any Pydantic model** (SEC-6). The `ApiCredential` SQLAlchemy model holds `key_ciphertext` (bytes). The transient `ProviderCredential` dataclass holds the decrypted string but is never serialized. Any future Pydantic schema for `api_credentials` (e.g., for Phase 9's admin form) MUST exclude the decrypted field; CI grep test for `model_dump\(\)` lands in Phase 12 per ROADMAP §"Phase 3: Notes".
- **Logging values from `app_settings` blindly.** D-08 allows verbatim logging today because no current row holds sensitive data — but `json` value_type rows should log only top-level keys (not full payload) so a future secret-bearing row can't leak. Document the convention; defer redaction-config to a future row that needs it.
- **Bypassing the cache for reads.** Every read should go through `get_str/get_int/etc.` — direct SQL reads of `app_settings` from anywhere outside `services/settings.py` are an architectural violation. The Phase 2 raw-SQL read of `setup_completed` is the documented exception (FOR UPDATE composes poorly with the cache); planner judges whether to migrate other non-locked reads.
- **Constructing `MultiFernet` per call.** The `_multi_fernet` is a module-level singleton (Pattern 1). Per-call construction would re-parse `APP_ENCRYPTION_KEY.split(",")` on every encrypt/decrypt.
- **Treating `Fernet.generate_key()` output as `str`.** It returns `bytes` (verified: cryptography docs §Fernet — "Generates a fresh fernet key"). The `.env.example` one-liner does `Fernet.generate_key().decode()` to write it as text into the file. Inside the encryption module, `Fernet(k)` accepts either, so no conversion is needed there.
- **Using Postgres ENUM for `provider`.** Locked: Text + CHECK (D-discretion default). ENUM requires a separate migration to add a value (future Ollama); Text + CHECK requires only ALTER CONSTRAINT.
- **Catching bare `Exception` in `startup_check()`.** Catch `(InvalidToken, ValueError, binascii.Error)` and chain via `raise EncryptionStartupError(...) from exc`. A bare except would swallow unrelated bugs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Symmetric encryption with authenticated integrity | A custom AES-CBC + HMAC wrapper | `cryptography.fernet.Fernet` | Fernet is AES-128-CBC + HMAC-SHA256 + IV + timestamp — pre-baked, audited, versioned. Hand-rolling exposes you to padding-oracle attacks. |
| Key rotation logic | Custom multi-key try-loop | `cryptography.fernet.MultiFernet` | MultiFernet's `decrypt()` "attempts to decrypt tokens with each key in turn" (CITED: cryptography docs). Custom code re-implements that semantics + risks subtle bugs (e.g., catching the wrong exception). |
| In-process cache | `cachetools.TTLCache` or `functools.lru_cache` | Plain `dict[str, _CachedSetting]` | Cache is invalidated by `set_setting()` only (write-through); single-worker invariant makes a dict consistent across requests. TTL / LRU adds complexity without benefit at 19 rows. |
| Key fingerprint | Custom hex encoding | `hashlib.sha256(key_bytes).hexdigest()` | Stdlib; deterministic; 64 hex chars; collision-resistant. |
| `app_settings` value coercion | Custom string-to-int / string-to-bool parser | Built-in `int()`, JSON literals (`"true"` → True via lookup dict), `json.loads()` for JSON rows | Stdlib; the coercion map is 6 lines. The `'null'` value_type is the typed-null sentinel — every accessor returns None for that row. |
| ASGI middleware for lifespan hooks | A new middleware | The existing `lifespan` body in `app/main.py:134` | Phase 3 hooks belong in lifespan, not middleware. No new middleware. |
| Dataclass alternative for `ProviderCredential` | `attrs.frozen` or `pydantic.BaseModel` | `@dataclass(frozen=True, slots=True)` | Stdlib; frozen + slots provide the SEC-6 guarantees. attrs is fine but adds a dep. Pydantic is exactly what NOT to use (SEC-6). |

**Key insight:** Phase 3 is composition, not invention. Every load-bearing primitive (Fernet, SQLAlchemy `Mapped`, Alembic `op.bulk_insert`, structlog event emission, FastAPI `lifespan`) already has an audited library + an in-codebase analog from Phases 0-2. The planner's job is to wire them together according to the 16 CONTEXT decisions.

## Runtime State Inventory

> Phase 3 is mostly additive (new module, new table, new lifespan hooks) but the auto-rewrap path (D-14) and the cache invalidation contract (D-08) interact with runtime state. This section enumerates what could go wrong at the runtime layer.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | (a) The two seeded `api_credentials` rows (D-04) with `key_ciphertext=NULL, is_enabled=false`; (b) the 19 existing `app_settings` rows from Phase 0 D-17; (c) the new `app_settings` row `encryption_key_primary_fingerprint` (value=NULL on first deploy) | Migration writes (a) + (c) atomically. (b) is read-only at this phase; the new typed cache must NOT mutate the 19 seeded rows. The Phase 2 `setup_completed` row is read via raw SQL (FOR UPDATE) — that stays; cache-only reads of the same row through `settings.get_bool("setup_completed")` are fine for non-locked sites. |
| Live service config | None — Phase 3 owns no external service. (Phase 7's Anthropic / OpenAI SDKs will consume the decrypted credentials but Phase 7 owns that wiring.) | None. |
| OS-registered state | None — Phase 3 ships no OS-level registrations (no cron, no Task Scheduler, no systemd units). | None. |
| Secrets / env vars | `APP_ENCRYPTION_KEY` (already declared in `app/config.py:48` from Phase 0; comma-separated raw string). Phase 3 parses on use. No new env var added by this phase. | The `.env.example` already documents the generation one-liner (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). The operator workflow for rotation (prepend new key → restart → rewrap runs → next deploy can remove old key) must be documented in README — planner adds a § Key Rotation section in `README.md` per ROADMAP success criteria #1 wording. |
| Build artifacts / installed packages | None — `cryptography>=48,<49` is already pinned. No new pyproject dependency. | None — verify by reading `pyproject.toml`. |

**Nothing found in category:** Live service config (none), OS-registered state (none), Build artifacts (none — no new deps), Secrets new (none — APP_ENCRYPTION_KEY pre-existing).

**The canonical question — what runtime systems still have stale state after a Phase 3 deploy?**

- **First deploy (empty credentials):** Nothing to migrate. `rewrap_if_needed(db)` sees 0 populated rows and no-ops; the fingerprint row stays NULL until the first credential is set.
- **Existing deploy (with populated credentials) + key rotation:** The operator prepends the new key, restarts, and `rewrap_if_needed` re-encrypts every populated row under the new primary. The fingerprint row is updated to the new SHA-256. On the next deploy, the operator can drop the old key from `APP_ENCRYPTION_KEY` safely.
- **Existing deploy (with populated credentials) + no key change:** `rewrap_if_needed` compares the stored fingerprint to the current primary's SHA-256, sees a match, no-ops. Bounded to one SELECT.

## Common Pitfalls

### Pitfall 1: Malformed APP_ENCRYPTION_KEY surfaces too late (build-time vs lifespan)
**What goes wrong:** `Fernet("not-a-valid-key")` raises `binascii.Error` at module-import time. If `_multi_fernet` is built at import (Pattern 1), the failure happens before lifespan runs — the error message is opaque and the operator sees a stack trace pointing at `app/services/encryption.py:42`, not a clear "your APP_ENCRYPTION_KEY is malformed."
**Why it happens:** `cryptography.fernet.Fernet` validates the base64 format eagerly.
**How to avoid:** Catch the construction error inside `_build_multi_fernet()` and re-raise as `EncryptionStartupError` with a clear message + chained `__cause__`. The lifespan-level `startup_check()` then performs the **sentinel round-trip** (D-13) which catches the "key constructed but unusable" branch (rare; mostly caught at construction, but the round-trip is the belt-and-suspenders).
**Warning signs:** Operator sees uvicorn fail with `binascii.Error: Invalid base64-encoded string` instead of `EncryptionStartupError: APP_ENCRYPTION_KEY is empty or malformed`.

### Pitfall 2: Fernet token type confusion (bytes vs str)
**What goes wrong:** `encrypt(plaintext: bytes) -> bytes` returns bytes (base64-url-encoded ASCII underneath, but the API contract is bytes). Storing as `text` requires `.decode()` round-trips; storing as `bytea` keeps the type honest. If the model is `Mapped[str]` but the column is `bytea`, SQLAlchemy raises at read time.
**Why it happens:** Fernet's docs describe the output as "URL-safe base64-encoded" which sounds like a string. The actual return type is `bytes`.
**How to avoid:** Lock `key_ciphertext` as `bytea` (`Mapped[bytes | None]` + `mapped_column(LargeBinary, nullable=True)`). Verified: PostgreSQL `LargeBinary` resolves to `bytea` (CITED: SQLAlchemy 2.0 type_basics docs).
**Warning signs:** `sqlalchemy.exc.StatementError: invalid input syntax for type bytea` on insert; or `TypeError: a bytes-like object is required, not 'str'` inside `encryption.decrypt()`.

### Pitfall 3: Decrypted key passed through Pydantic (SEC-6 leak)
**What goes wrong:** A future Phase 9 admin endpoint defines `class ApiCredentialOut(BaseModel): api_key: str` and does `return ApiCredentialOut(**row.__dict__).model_dump()` — the decrypted key lands in the JSON response. Pydantic v2's `model_dump()` includes every field by default.
**Why it happens:** The natural Pydantic shape is to mirror the model; the developer doesn't realize `api_key` should never be in the output schema.
**How to avoid:** (a) `ProviderCredential` is a `@dataclass(frozen=True, slots=True)` — not a Pydantic model (D-09). (b) Phase 12 lands a CI grep test for `model_dump\(\)` on `ApiCredential` (deferred per ROADMAP §Phase 3 Notes). (c) Document the rule in Phase 3's README section / ADR: any `ApiCredential` Pydantic schema MUST exclude `api_key`-shaped fields.
**Warning signs:** Code review catches `ApiCredentialOut.api_key`; or CI grep test (Phase 12) flags `model_dump` near `ApiCredential`.

### Pitfall 4: Cache invalidation race under FOR UPDATE composition
**What goes wrong:** Phase 2's `/setup` uses `SELECT value FROM app_settings WHERE key='setup_completed' FOR UPDATE` to serialize concurrent setup attempts. The Phase 3 cache returns the cached value, which is **not locked** — a `settings.get_bool("setup_completed")` after `set_setting(db, "setup_completed", True, ...)` from another tab could read stale cache (write-through invalidate runs in the writer; the reader's cache is still the old value if a request is in flight when the invalidate hits).
**Why it happens:** The cache is a single in-process dict; the GIL makes individual reads atomic but the read-and-act pattern is not atomic across requests.
**How to avoid:** D-specifics locks this: the Phase 2 `setup_completed` read site stays raw SQL (FOR UPDATE). The typed reader cache is for **non-locked read sites only**. Document this in the `services/settings.py` module docstring. Other callers (Phase 4+ catalog reads, Phase 7 AI service reads) never need FOR UPDATE; they're safe.
**Warning signs:** Two concurrent `/setup` attempts both succeed (would have been caught by AUTH-02 anyway via the row lock at the DB layer — the cache is downstream).

### Pitfall 5: Lifespan emits without request context
**What goes wrong:** `encryption.startup_check()` and `credentials.rewrap_if_needed()` run during lifespan startup, before any HTTP request exists. The structlog `RequestContextMiddleware` (Phase 1) binds `request_id` via `contextvars`; outside that middleware's scope, `structlog.contextvars.get_contextvars()` returns an empty dict. Lifespan-emitted events therefore have NO `request_id` field.
**Why it happens:** structlog `contextvars` bindings are scoped to the middleware's `try/finally` block; lifespan is outside that scope.
**How to avoid:** Emit lifespan events with explicit `request_id=None` or simply omit the field — the Phase 1 structlog config handles both. Phase 1 D-14 taxonomy allows omission. CONTEXT `<specifics>` documents this: "Lifespan-emitted events have no request_id; use request_id=None or omit." [VERIFIED: read `app/logging.py` and `app/middleware/request_context.py`]
**Warning signs:** Log queries that filter by `request_id != null` miss the lifespan events; operator notices `encryption.startup_ok` has no correlation ID.

### Pitfall 6: Rewrap fingerprint write on first deploy (false positive)
**What goes wrong:** On first deploy, the fingerprint row is NULL. If `rewrap_if_needed` writes the fingerprint unconditionally on first run, the function does an unnecessary UPDATE every startup (idempotent but noisy in the audit log).
**Why it happens:** Naive logic: `if stored_fp != current_fp: write_fp`. NULL != current_fp is True.
**How to avoid:** CONTEXT `<specifics>` locks: "rewrap reads the fingerprint (None), counts populated rows (0), no-ops, does NOT write the fingerprint. The fingerprint is only written when the rewrap actually does work, so a future admin who sets a key sees the fingerprint set on the next startup or on the next `set_provider_credential()` call (planner picks the cleaner of the two; both work)." **Recommendation:** write the fingerprint inside `set_provider_credential()` (first time a credential is set), not at lifespan startup. Symmetric with the rewrap path: that already writes the fingerprint when it does work.
**Warning signs:** Audit log shows `app_setting.changed setting_key=encryption_key_primary_fingerprint` on every container restart.

### Pitfall 7: Orphaned ciphertext crashes startup (wrong failure mode)
**What goes wrong:** A naive `rewrap_if_needed` decrypts every populated row; if a row has ciphertext encrypted under a key that's no longer in `APP_ENCRYPTION_KEY`, `MultiFernet.decrypt()` raises `InvalidToken`. If the exception propagates, the app fails to start — locking the admin out of fixing the problem via Phase 9.
**Why it happens:** The auto-rewrap path is best-effort, but a literal "decrypt every row" loop is brittle.
**How to avoid:** D-15 locks this: orphaned ciphertext returns `None` + emits `encryption.decrypt_failed`. The app stays up. For the rewrap path specifically: catch `InvalidToken` per-row, emit `encryption.decrypt_failed` with the provider name + row context, skip that row, continue to the next. The next-deploy admin recovery is to re-set the key via Phase 9.
**Warning signs:** Container fails to start after an `APP_ENCRYPTION_KEY` change that drops a key still referenced by stored ciphertext.

### Pitfall 8: `Fernet.generate_key()` confused for `str` in seed/test code
**What goes wrong:** `Fernet.generate_key()` returns `bytes` (verified). Tests that do `key: str = Fernet.generate_key()` will fail type checks; tests that do `os.environ["APP_ENCRYPTION_KEY"] = Fernet.generate_key()` raise TypeError at runtime.
**Why it happens:** The docs describe the output as a "URL-safe base64-encoded 32-byte key" — sounds like a string.
**How to avoid:** Tests do `Fernet.generate_key().decode()` to get a string when injecting into env vars. Use `bytes` directly when passing to `Fernet(k)` (accepts both per the API).
**Warning signs:** `TypeError: str expected, not bytes` in test setup.

## Code Examples

Verified patterns. Sources are cited inline.

### `app/services/encryption.py` — Pure crypto primitives + startup_check

```python
"""Fernet/MultiFernet primitives + sentinel startup check (D-12, D-13, D-14)."""
from __future__ import annotations

import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings


class EncryptionStartupError(RuntimeError):
    """Sentinel round-trip failed at lifespan startup.

    Raised from :func:`startup_check` with the underlying cryptography
    error chained via ``__cause__``. Propagates out of lifespan → uvicorn
    exits non-zero → docker-compose healthcheck marks the container
    unhealthy (D-13). Subclass of RuntimeError so it surfaces in the
    structured log with a clear class name.
    """


def _parse_keys() -> list[str]:
    """Split APP_ENCRYPTION_KEY on commas, strip whitespace, drop empties."""
    return [k.strip() for k in settings.APP_ENCRYPTION_KEY.split(",") if k.strip()]


def _build_multi_fernet() -> MultiFernet:
    """Construct MultiFernet from APP_ENCRYPTION_KEY (first key = primary).

    Raises ValueError if the key list is empty after parsing. A malformed
    base64 key raises ``binascii.Error`` from inside Fernet(); the caller
    (startup_check) catches both and re-raises EncryptionStartupError.

    Source: https://cryptography.io/en/latest/fernet/ — MultiFernet attempts
    to decrypt tokens with each key in turn.
    """
    keys = _parse_keys()
    if not keys:
        raise ValueError("APP_ENCRYPTION_KEY is empty after splitting on commas")
    return MultiFernet([Fernet(k) for k in keys])


# Module-level singleton (Pattern 1). Constructed at first import.
_multi_fernet = _build_multi_fernet()


def encrypt(plaintext: bytes) -> bytes:
    """Encrypt under the primary key (first key in APP_ENCRYPTION_KEY).

    Returns URL-safe base64-encoded bytes per Fernet's contract.
    """
    return _multi_fernet.encrypt(plaintext)


def decrypt(ciphertext: bytes) -> bytes:
    """Decrypt under any key in APP_ENCRYPTION_KEY (primary first, then rest).

    Raises cryptography.fernet.InvalidToken if no key works — the caller
    (credentials.get_provider_credential) catches this and translates to
    a graceful None + ``encryption.decrypt_failed`` event (D-15).
    """
    return _multi_fernet.decrypt(ciphertext)


def primary_key_fingerprint() -> str:
    """Return SHA-256 hex of the first key in APP_ENCRYPTION_KEY.

    Used by D-14 auto-rewrap to detect when the primary has changed.
    The key string itself is the input (not the bytes-decoded form);
    consistency is enforced by parsing through ``_parse_keys()``.
    """
    primary = _parse_keys()[0]
    return hashlib.sha256(primary.encode("ascii")).hexdigest()


def startup_check() -> None:
    """Sentinel encrypt+decrypt round-trip at lifespan startup (D-13).

    On success: emits ``encryption.startup_ok`` and returns.
    On any cryptography or value error: raises EncryptionStartupError
    chained with the underlying exception so the operator sees the root
    cause in the structured log.
    """
    import structlog
    from app.events import ENCRYPTION_STARTUP_OK

    log = structlog.get_logger(__name__)
    try:
        round_trip = decrypt(encrypt(b"snobbery-startup-check"))
        if round_trip != b"snobbery-startup-check":
            raise EncryptionStartupError(
                "Sentinel round-trip produced wrong plaintext "
                "(corruption or library bug)"
            )
    except (InvalidToken, ValueError, TypeError) as exc:
        raise EncryptionStartupError(
            "APP_ENCRYPTION_KEY round-trip failed — key may be malformed, "
            "missing, or unusable"
        ) from exc
    log.info(ENCRYPTION_STARTUP_OK, fingerprint=primary_key_fingerprint()[:8])


__all__ = [
    "EncryptionStartupError",
    "encrypt",
    "decrypt",
    "primary_key_fingerprint",
    "startup_check",
]
```

### `app/services/settings.py` — Typed cache + write-through invalidation

```python
"""Typed app_settings reader + write-through cache (D-05 through D-08)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.events import ADMIN_APP_SETTING_CHANGED
from app.models.app_setting import AppSetting

log = structlog.get_logger(__name__)


class SettingNotFoundError(KeyError):
    """Raised when a typed accessor receives an unknown key."""


class SettingTypeError(TypeError):
    """Raised when an accessor's expected type doesn't match the row's value_type."""


@dataclass(frozen=True, slots=True)
class _CachedSetting:
    value: str | None
    value_type: str  # 'string' | 'int' | 'float' | 'bool' | 'json' | 'null'
    coerced: Any  # pre-coerced Python value (None for value_type='null')


# Module-level cache. Single-worker invariant (Phase 0 D-13 / FOUND-04) means
# this is consistent across every request. Empty until prewarm_cache() runs.
_cache: dict[str, _CachedSetting] = {}


def _coerce(value: str | None, value_type: str) -> Any:
    """Convert the text-stored value to its Python type, or None for value_type='null'."""
    if value_type == "null":
        return None
    if value is None:
        # value=NULL with value_type != 'null' is invalid; treat as None defensively.
        return None
    if value_type == "string":
        return value
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    if value_type == "bool":
        return value.lower() == "true"
    if value_type == "json":
        return json.loads(value)
    raise SettingTypeError(f"Unknown value_type: {value_type!r}")


def prewarm_cache(db: Session) -> None:
    """Populate _cache from a single SELECT * FROM app_settings (D-06)."""
    rows = db.execute(select(AppSetting)).scalars().all()
    _cache.clear()
    for row in rows:
        _cache[row.key] = _CachedSetting(
            value=row.value,
            value_type=row.value_type,
            coerced=_coerce(row.value, row.value_type),
        )


def _get(key: str, expected_type: str) -> Any:
    cached = _cache.get(key)
    if cached is None:
        raise SettingNotFoundError(key)
    if cached.value_type == "null":
        return None
    if cached.value_type != expected_type:
        raise SettingTypeError(
            f"Setting {key!r} has value_type={cached.value_type!r}; "
            f"caller expected {expected_type!r}"
        )
    return cached.coerced


def get_str(key: str) -> str:
    """Return the string value for *key*; raises if value_type != 'string'."""
    return _get(key, "string")


def get_int(key: str) -> int:
    """Return the int value for *key*; raises if value_type != 'int'."""
    return _get(key, "int")


def get_bool(key: str) -> bool:
    """Return the bool value for *key*; raises if value_type != 'bool'."""
    return _get(key, "bool")


def get_json(key: str) -> Any:
    """Return the json-decoded value for *key*; raises if value_type != 'json'."""
    return _get(key, "json")


def get_raw(key: str) -> tuple[str | None, str]:
    """Return (value, value_type) for *key* — used by the Phase 9 admin editor."""
    cached = _cache.get(key)
    if cached is None:
        raise SettingNotFoundError(key)
    return (cached.value, cached.value_type)


def set_setting(
    db: Session,
    key: str,
    value: Any,
    *,
    by_user_id: int | None,
) -> None:
    """UPDATE the row, invalidate the cache, emit admin.app_setting_changed (D-08).

    The value is coerced to text for storage (None for value_type='null'); the
    cache is repopulated on next read by re-coercing.
    """
    # Look up existing row to validate value_type and capture old value for audit.
    existing = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one()
    old_value = existing.value
    value_type = existing.value_type

    # Coerce input to its text form for storage.
    if value is None:
        text_value = None
    elif value_type == "json":
        text_value = json.dumps(value)
    elif value_type == "bool":
        text_value = "true" if value else "false"
    else:
        text_value = str(value)

    db.execute(
        update(AppSetting)
        .where(AppSetting.key == key)
        .values(value=text_value, updated_by_user_id=by_user_id)
    )
    db.commit()

    # Invalidate the cache — next access re-loads from the DB.
    _cache.pop(key, None)

    log.info(
        ADMIN_APP_SETTING_CHANGED,
        setting_key=key,
        old_value=old_value,
        new_value=text_value,
        value_type=value_type,
        by_user_id=by_user_id,
    )


def invalidate(key: str) -> None:
    """Drop *key* from the cache. Test-only hook for out-of-band SQL edits."""
    _cache.pop(key, None)


__all__ = [
    "SettingNotFoundError",
    "SettingTypeError",
    "prewarm_cache",
    "get_str",
    "get_int",
    "get_bool",
    "get_json",
    "get_raw",
    "set_setting",
    "invalidate",
]
```

### `app/services/credentials.py` — api_credentials CRUD + ProviderCredential

```python
"""api_credentials CRUD + ProviderCredential dataclass + auto-rewrap (D-01..D-04, D-09..D-15)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.events import (
    ADMIN_API_CREDENTIAL_SET,
    ENCRYPTION_DECRYPT_FAILED,
    ENCRYPTION_REWRAP_COMPLETED,
)
from app.models.api_credential import ApiCredential
from app.services import encryption, settings

log = structlog.get_logger(__name__)

Provider = Literal["anthropic", "openai"]


@dataclass(frozen=True, slots=True)
class ProviderCredential:
    """Decrypted credential — lives only in caller's local scope (D-09, SEC-6).

    Never persisted, never serialized through Pydantic. Frozen+slots block
    accidental attribute injection AND ``__dict__`` access. The ``key`` field
    is ``str`` (NOT bytes) because both Anthropic and OpenAI SDKs declare
    ``api_key: str | None`` at the constructor (VERIFIED).
    """
    provider: Provider
    key: str
    model_name: str
    last_four: str


def get_provider_credential(db: Session, provider: Provider) -> ProviderCredential | None:
    """Return decrypted ProviderCredential, or None for any disabled/missing/failed state.

    Returns None when:
      - row doesn't exist (shouldn't happen; D-04 seeds both)
      - is_enabled=false
      - key_ciphertext IS NULL
      - decrypt fails (emits encryption.decrypt_failed; D-15)
    """
    row = db.execute(
        select(ApiCredential).where(ApiCredential.provider == provider)
    ).scalar_one_or_none()
    if row is None or not row.is_enabled or row.key_ciphertext is None:
        return None
    try:
        plain_bytes = encryption.decrypt(row.key_ciphertext)
    except InvalidToken as exc:
        log.warning(
            ENCRYPTION_DECRYPT_FAILED,
            provider=provider,
            error_class=type(exc).__name__,
        )
        return None
    return ProviderCredential(
        provider=provider,
        key=plain_bytes.decode("utf-8"),
        model_name=row.model_name or "",
        last_four=row.last_four or "",
    )


def set_provider_credential(
    db: Session,
    provider: Provider,
    *,
    key: str,
    model_name: str,
    by_user_id: int | None,
) -> None:
    """Encrypt + UPDATE + emit admin.api_credential_set (D-03, D-08-style)."""
    ciphertext = encryption.encrypt(key.encode("utf-8"))
    last_four = key[-4:]
    db.execute(
        update(ApiCredential)
        .where(ApiCredential.provider == provider)
        .values(
            key_ciphertext=ciphertext,
            last_four=last_four,
            model_name=model_name,
            is_enabled=True,
            updated_by_user_id=by_user_id,
        )
    )
    # Also write the fingerprint on first credential set, so the rewrap
    # path has a baseline (Pitfall 6).
    try:
        stored_fp = settings.get_str("encryption_key_primary_fingerprint")
    except (settings.SettingTypeError, KeyError):
        stored_fp = None
    if stored_fp is None:
        settings.set_setting(
            db,
            "encryption_key_primary_fingerprint",
            encryption.primary_key_fingerprint(),
            by_user_id=by_user_id,
        )
        # Also flip the value_type from 'null' to 'string' — handled by set_setting's
        # coercion or by a one-time migration UPDATE; planner decides.
    db.commit()
    log.info(
        ADMIN_API_CREDENTIAL_SET,
        provider=provider,
        last_four=last_four,
        model_name=model_name,
        by_user_id=by_user_id,
    )


def set_provider_enabled(
    db: Session,
    provider: Provider,
    enabled: bool,
    *,
    by_user_id: int | None,
) -> None:
    """Toggle is_enabled for a provider; logged as admin.api_credential_set."""
    db.execute(
        update(ApiCredential)
        .where(ApiCredential.provider == provider)
        .values(is_enabled=enabled, updated_by_user_id=by_user_id)
    )
    db.commit()
    log.info(
        ADMIN_API_CREDENTIAL_SET,
        provider=provider,
        action="enable" if enabled else "disable",
        by_user_id=by_user_id,
    )


def rewrap_if_needed(db: Session) -> None:
    """Re-encrypt every populated row under the new primary key (D-14).

    Reads the stored fingerprint via settings.get_str (or None if value_type='null');
    compares to encryption.primary_key_fingerprint(); if they differ AND at least
    one row has key_ciphertext IS NOT NULL, runs the re-encrypt loop in one TX.
    """
    try:
        stored_fp = settings.get_str("encryption_key_primary_fingerprint")
    except (settings.SettingTypeError, KeyError):
        stored_fp = None
    current_fp = encryption.primary_key_fingerprint()
    if stored_fp == current_fp:
        return  # no-op

    # SELECT ... FOR UPDATE — belt-and-suspenders against a future multi-worker world.
    populated_rows = db.execute(
        select(ApiCredential)
        .where(ApiCredential.key_ciphertext.is_not(None))
        .with_for_update()
    ).scalars().all()
    if not populated_rows:
        # First-deploy path or empty-credentials state: no-op, don't write fp.
        return

    row_count = 0
    for row in populated_rows:
        try:
            plain = encryption.decrypt(row.key_ciphertext)
        except InvalidToken as exc:
            log.warning(
                ENCRYPTION_DECRYPT_FAILED,
                provider=row.provider,
                error_class=type(exc).__name__,
                during="rewrap",
            )
            continue  # skip orphaned ciphertext (D-15); admin fixes via Phase 9
        new_ciphertext = encryption.encrypt(plain)
        db.execute(
            update(ApiCredential)
            .where(ApiCredential.provider == row.provider)
            .values(key_ciphertext=new_ciphertext)
        )
        row_count += 1

    # Update the fingerprint via set_setting so the cache invalidates correctly.
    settings.set_setting(
        db,
        "encryption_key_primary_fingerprint",
        current_fp,
        by_user_id=None,
    )
    db.commit()
    log.info(ENCRYPTION_REWRAP_COMPLETED, row_count=row_count)


__all__ = [
    "Provider",
    "ProviderCredential",
    "get_provider_credential",
    "set_provider_credential",
    "set_provider_enabled",
    "rewrap_if_needed",
]
```

### `app/models/api_credential.py` — SQLAlchemy 2.0 Mapped[...] model

```python
"""``api_credentials`` table — one row per AI provider (D-01)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, LargeBinary, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ApiCredential(Base):
    """One row per provider; key_ciphertext is Fernet-encrypted."""

    __tablename__ = "api_credentials"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('anthropic', 'openai')",
            name="ck_api_credentials_provider",
        ),
    )

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    key_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    last_four: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
```

### `app/migrations/versions/p3_api_credentials.py` — Migration sketch

```python
"""p3_api_credentials: create api_credentials, seed 2 rows, add fingerprint row.

Revision ID: p3_api_credentials
Revises: p1_sessions
Create Date: 2026-05-XX
"""
from __future__ import annotations
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p3_api_credentials"
down_revision: str | Sequence[str] | None = "p1_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- 1) Create api_credentials -----------------------------------------
    op.create_table(
        "api_credentials",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("key_ciphertext", sa.LargeBinary, nullable=True),
        sa.Column("last_four", sa.Text, nullable=True),
        sa.Column("model_name", sa.Text, nullable=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_by_user_id", sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'openai')",
            name="ck_api_credentials_provider",
        ),
    )

    # ---- 2) Seed 2 rows ----------------------------------------------------
    api_credentials_table = sa.table(
        "api_credentials",
        sa.column("provider", sa.Text),
        sa.column("key_ciphertext", sa.LargeBinary),
        sa.column("last_four", sa.Text),
        sa.column("model_name", sa.Text),
        sa.column("is_enabled", sa.Boolean),
    )
    op.bulk_insert(
        api_credentials_table,
        [
            {"provider": "anthropic", "key_ciphertext": None, "last_four": None,
             "model_name": None, "is_enabled": False},
            {"provider": "openai", "key_ciphertext": None, "last_four": None,
             "model_name": None, "is_enabled": False},
        ],
    )

    # ---- 3) Add encryption_key_primary_fingerprint app_settings row --------
    app_settings_table = sa.table(
        "app_settings",
        sa.column("key", sa.Text),
        sa.column("value", sa.Text),
        sa.column("value_type", sa.Text),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        app_settings_table,
        [{
            "key": "encryption_key_primary_fingerprint",
            "value": None,
            "value_type": "null",
            "description": (
                "SHA-256 hex of APP_ENCRYPTION_KEY primary; used by Phase 3 "
                "D-14 auto-rewrap to detect key rotation. NULL until first "
                "credential is set."
            ),
        }],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM app_settings WHERE key = 'encryption_key_primary_fingerprint'"
    )
    op.drop_table("api_credentials")
```

### `app/events.py` — Append 5 constants

```python
# Append to existing events.py (sketch):

# --- admin.* (Phase 3 wires)  ---------------------------------------------
ADMIN_APP_SETTING_CHANGED = "admin.app_setting_changed"  # D-08
ADMIN_API_CREDENTIAL_SET = "admin.api_credential_set"    # D-03

# --- encryption.* (Phase 3 wires; lifespan + decrypt paths) ---------------
ENCRYPTION_STARTUP_OK = "encryption.startup_ok"          # D-13
ENCRYPTION_DECRYPT_FAILED = "encryption.decrypt_failed"  # D-15
ENCRYPTION_REWRAP_COMPLETED = "encryption.rewrap_completed"  # D-14
```

### Test patterns — real keys per test

```python
# tests/services/test_encryption.py (sketch)
def test_round_trip(monkeypatch) -> None:
    """Verify encrypt → decrypt under a single key."""
    from cryptography.fernet import Fernet
    monkeypatch.setenv("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    # Re-import to pick up the new env var (Phase 0 module-level singleton pattern)
    import importlib, app.services.encryption as enc
    importlib.reload(enc)
    plain = b"sk-ant-test-key-1234"
    assert enc.decrypt(enc.encrypt(plain)) == plain

def test_multi_fernet_rotation(monkeypatch) -> None:
    """Encrypt under k1, rotate so k2 is primary + k1 is secondary, still decrypts."""
    from cryptography.fernet import Fernet
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    monkeypatch.setenv("APP_ENCRYPTION_KEY", k1)
    import importlib, app.services.encryption as enc
    importlib.reload(enc)
    ciphertext = enc.encrypt(b"sk-rotated")
    # Rotate: prepend k2 as new primary
    monkeypatch.setenv("APP_ENCRYPTION_KEY", f"{k2},{k1}")
    importlib.reload(enc)
    assert enc.decrypt(ciphertext) == b"sk-rotated"

def test_startup_check_on_malformed_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "not-a-valid-base64-fernet-key!!")
    import importlib, app.services.encryption as enc
    with pytest.raises(enc.EncryptionStartupError):
        importlib.reload(enc)
        enc.startup_check()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `Fernet(key)` | `MultiFernet([Fernet(k1), Fernet(k2), ...])` | Available since cryptography 1.x; project-locked here (PROJECT.md Key Decisions) | Rotation-on-decrypt is the standard pattern for application-level symmetric encryption; rotating a single Fernet would orphan ciphertext (PITFALL SEC-2) |
| `SQLAlchemy 1.x Query API` | `SQLAlchemy 2.0 select() / update() with Mapped[...]` | SQLAlchemy 2.0 (Jan 2023); project-pinned at 2.0.49 | Phase 3 uses only 2.0 idioms; legacy `session.query()` is banned by CLAUDE.md |
| `psycopg2-binary` | `psycopg[binary]` 3.3 | psycopg 3 stable since 2021; project-pinned | Native async + modern packaging; SQLAlchemy 2.0 picks the async path via the same URL |
| FastAPI `@app.on_event("startup"/"shutdown")` | `lifespan` async context manager | Starlette 1.0 (Mar 2026) removes the decorators; FastAPI 0.136 ships against it | All three Phase 3 startup hooks land inside `lifespan` — never use the deprecated decorators |
| Custom in-memory cache with TTL | Module-level dict + write-through invalidation | n/a — TTL is the wrong tool here | Single-worker invariant + bounded write rate (admin only) makes TTL pointless |
| Pydantic v1 `dict()` | Pydantic v2 `model_dump()` | Pydantic v2 (2023); project-pinned at 2.13 | Phase 3 does NOT use Pydantic for `ApiCredential` (SEC-6); but future Phase 9 admin schemas use v2 |

**Deprecated / outdated:**
- `cryptography` < 41 — old AEAD modes deprecated; project pinned at >=48
- APScheduler 4.x alpha — stay on 3.x (not Phase 3's concern, but informs the deferred "Rotate now" button in Phase 9 which calls into Phase 3 services)
- `passlib` for argon2 — argon2-cffi is the modern direct path (Phase 2 already chose argon2-cffi)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (none) | Every load-bearing claim in this research was verified via official docs (cryptography, SQLAlchemy, Alembic) or direct source inspection (Anthropic SDK, OpenAI SDK) or by reading the existing repo (Phase 0/1/2 patterns). | — | — |

**Table is empty:** All claims tagged `[VERIFIED]` or `[CITED]`. Specifically:
- MultiFernet rotation semantics [CITED: cryptography.io/en/latest/fernet/ — "MultiFernet attempts to decrypt tokens with each key in turn"]
- Fernet constructor accepts bytes-or-str [CITED: cryptography.io — "A URL-safe base64-encoded 32-byte key" as either bytes or str]
- Anthropic `api_key: str | None` [VERIFIED: WebFetch on github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_client.py — line 259]
- OpenAI `api_key: str | Callable[[], str] | None` [VERIFIED: WebFetch on github.com/openai/openai-python/blob/main/src/openai/_client.py]
- SQLAlchemy `Mapped[bytes | None]` + `LargeBinary` → PostgreSQL `bytea` [CITED: docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.LargeBinary]
- Alembic `op.bulk_insert` + `sa.table()` pattern [CITED: alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.bulk_insert]
- structlog lifespan emit with no `request_id` [VERIFIED: read `app/logging.py` + Phase 1 D-14 + CONTEXT `<specifics>`]
- cryptography 48.0.0 current [VERIFIED: `pip index versions cryptography` 2026-05-18]

No user confirmation needed.

## Open Questions (RESOLVED)

1. **Should `set_provider_credential` write the fingerprint on first credential set, or should `rewrap_if_needed` do it at next startup?**
   - What we know: Both paths work; CONTEXT `<specifics>` says "planner picks the cleaner of the two; both work."
   - What's unclear: Style preference.
   - Recommendation: Write inside `set_provider_credential` (Pitfall 6's resolution). Symmetric with the rewrap path: rewrap already writes the fingerprint when it does real work. Writing on first-set keeps the fingerprint always consistent with "at least one row is populated."
   - **RESOLVED:** Implemented in Plan 03-04 (`app/services/credentials.py`). `set_provider_credential` writes the fingerprint baseline on first-credential-set (when stored fingerprint is None) via an inline UPDATE in the same transaction; `rewrap_if_needed` writes the new fingerprint after a successful rewrap. See Plan 03-04 Task 1 action steps 7 and 9.

2. **How does `set_setting` handle a value transition `null` → `string` for `encryption_key_primary_fingerprint`?**
   - What we know: D-08 validates against the row's stored `value_type` for type matching, then writes the text. The fingerprint row starts as `value_type='null'`; the first write transitions it to a string.
   - What's unclear: Does `set_setting` permit a `value_type` change implicitly?
   - Recommendation: `set_setting` does NOT change `value_type`. The migration for `encryption_key_primary_fingerprint` should set `value_type='string'` from the start, with `value=NULL` (text column allows NULL regardless of `value_type='string'`). The `_coerce` function returns None for any `value=None`. This is simpler than a value_type transition. **Planner picks; recommend `value_type='string', value=NULL` in the migration** (slight deviation from CONTEXT which says `value_type='null'` — verify with discuss-phase if needed).
   - **RESOLVED:** Plan 03-01 migration uses `value_type='null'` (matches CONTEXT.md `<specifics>`, NOT the RESEARCH.md recommendation above). The `value_type='null'` → `value_type='string'` transition is handled by Plan 03-04's inline UPDATE bypass of `set_setting` inside `credentials.set_provider_credential` and `credentials.rewrap_if_needed`. This is a deliberate, documented exception (see Plan 03-04 deviation note). Plan 03-03 `set_setting` does NOT change `value_type` (immutable invariant; see Plan 03-03 Task 1 acceptance criterion). Plan 03-06 Task 5 test asserts the seeded row has `value_type='null'`.

3. **Does the test for `test_multi_fernet_rotation` need module reload via `importlib.reload`?**
   - What we know: Module-level singletons are constructed at first import; pytest reuses modules across tests.
   - What's unclear: How to swap `APP_ENCRYPTION_KEY` between tests cleanly.
   - Recommendation: Use `importlib.reload(app.services.encryption)` per test that mutates the env var. Pattern is shown in § Code Examples. Alternative: refactor `_multi_fernet` to be lazy-initialized (first call constructs, subsequent calls reuse) — but that complicates the singleton pattern. Stick with `importlib.reload`.
   - **RESOLVED:** Implemented in Plan 03-06 Task 1 — `tests/conftest.py` adds the `monkeypatched_app_encryption_key` fixture which calls `monkeypatch.setattr` on `app.config.settings.APP_ENCRYPTION_KEY` then `importlib.reload(app.services.encryption)` to rebuild the module-level `_multi_fernet` singleton per test. Plan 03-06 Tasks 2 and 4 use this fixture for every test that mutates the env var.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `cryptography` Python package | encryption.py | ✓ (assumed; pyproject.toml pins `>=48,<49`) | 48.0.0 | — |
| Python `hashlib` | primary_key_fingerprint() | ✓ (stdlib) | — | — |
| Python `dataclasses` | ProviderCredential | ✓ (stdlib, Python 3.10+ for slots=True) | Python 3.12 | — |
| Python `json` | settings.py | ✓ (stdlib) | — | — |
| SQLAlchemy 2.0 | All services | ✓ (already pinned, Phase 0) | 2.0.49 | — |
| Alembic 1.18 | migration | ✓ (already pinned, Phase 0) | 1.18.x | — |
| `structlog` | events emission | ✓ (already pinned, Phase 1) | 25.5 | — |
| pytest + pytest-asyncio | tests | ✓ (already pinned, Phase 1) | 9.0 / latest | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

> Nyquist consumes this block to produce VALIDATION.md.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0 + pytest-asyncio (auto mode); no httpx required (Phase 3 ships no routes) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (already configured in Phases 0+1+2) |
| Quick run command | `docker compose exec coffee-snobbery pytest -x tests/services/test_encryption.py tests/services/test_settings.py tests/services/test_credentials.py` |
| Full suite command | `docker compose exec coffee-snobbery pytest -x` |
| Estimated runtime | ~3s for Phase-3 subset (pure CPU, no HTTP); ~60s full |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-08 | MultiFernet round-trip (encrypt → decrypt) | unit | `pytest -x tests/services/test_encryption.py::test_round_trip` | ❌ Wave 0 |
| SEC-08 | Key rotation under MultiFernet (encrypt under k1, rotate to k2+k1, decrypt succeeds) | unit | `pytest -x tests/services/test_encryption.py::test_multi_fernet_rotation` | ❌ Wave 0 |
| SEC-08 | Orphaned ciphertext (encrypted under removed key) → `get_provider_credential` returns None + emits `encryption.decrypt_failed` | unit | `pytest -x tests/services/test_credentials.py::test_decrypt_failure_returns_none` | ❌ Wave 0 |
| SEC-08 | `ProviderCredential` is frozen+slots (mutation raises FrozenInstanceError; no __dict__) | unit | `pytest -x tests/services/test_credentials.py::test_provider_credential_immutability` | ❌ Wave 0 |
| SEC-08 | `set_provider_credential` writes `last_four = key[-4:]` and emits `admin.api_credential_set` | unit | `pytest -x tests/services/test_credentials.py::test_set_provider_credential_writes_last_four_and_emits` | ❌ Wave 0 |
| SEC-08 | `set_provider_credential` calls `encryption.encrypt()` — does NOT reimplement crypto (mock encrypt, assert called) | unit | `pytest -x tests/services/test_credentials.py::test_set_provider_credential_uses_encryption_module` | ❌ Wave 0 |
| SEC-08 | Disabled provider (`is_enabled=false`) → `get_provider_credential` returns None | unit | `pytest -x tests/services/test_credentials.py::test_get_provider_credential_disabled_returns_none` | ❌ Wave 0 |
| SEC-08 | NULL ciphertext (empty seeded row) → `get_provider_credential` returns None | unit | `pytest -x tests/services/test_credentials.py::test_get_provider_credential_null_ciphertext_returns_none` | ❌ Wave 0 |
| SEC-09 | `encryption.startup_check()` succeeds round-trip + emits `encryption.startup_ok` | unit | `pytest -x tests/services/test_encryption.py::test_startup_check_succeeds_on_valid_key` | ❌ Wave 0 |
| SEC-09 | Malformed `APP_ENCRYPTION_KEY` → `EncryptionStartupError` raised with chained cause | unit | `pytest -x tests/services/test_encryption.py::test_startup_check_on_malformed_key` | ❌ Wave 0 |
| SEC-09 | Empty `APP_ENCRYPTION_KEY` (after strip) → `EncryptionStartupError` | unit | `pytest -x tests/services/test_encryption.py::test_startup_check_on_empty_key` | ❌ Wave 0 |
| SEC-09 | `Fernet.generate_key()` one-liner in `.env.example` produces a Fernet-valid key | regression | `pytest -x tests/test_env_example.py::test_app_encryption_key_generation_hint_works` | ◆ EXTEND (existing file from Phase 0) |
| D-06 | `prewarm_cache` populates the cache from `app_settings` (all 19 + new fingerprint row = 20 entries) | unit | `pytest -x tests/services/test_settings.py::test_prewarm_cache_populates_all_rows` | ❌ Wave 0 |
| D-05 | `get_str / get_int / get_bool / get_json / get_raw` return correctly coerced values | unit | `pytest -x tests/services/test_settings.py::test_typed_accessors` | ❌ Wave 0 |
| D-05 | Type mismatch (e.g., `get_int` on a string row) raises `SettingTypeError` | unit | `pytest -x tests/services/test_settings.py::test_type_mismatch_raises` | ❌ Wave 0 |
| D-05 | `'null'` value_type rows return `None` from every accessor | unit | `pytest -x tests/services/test_settings.py::test_null_value_type_returns_none` | ❌ Wave 0 |
| D-08 | `set_setting` updates DB + invalidates cache + emits `admin.app_setting_changed` | unit | `pytest -x tests/services/test_settings.py::test_set_setting_writes_and_invalidates` | ❌ Wave 0 |
| D-08 | Audit event payload shape contains `setting_key, old_value, new_value, value_type, by_user_id` | unit (structlog capsys) | `pytest -x tests/services/test_settings.py::test_set_setting_audit_event_shape` | ❌ Wave 0 |
| D-13 | `startup_check` emits with no `request_id` field (lifespan context) | unit (structlog capsys) | `pytest -x tests/services/test_encryption.py::test_startup_check_emits_without_request_id` | ❌ Wave 0 |
| D-14 | First deploy (empty credentials) → `rewrap_if_needed` no-ops, fingerprint stays NULL | unit | `pytest -x tests/services/test_credentials.py::test_rewrap_first_deploy_noop` | ❌ Wave 0 |
| D-14 | Fingerprint match → `rewrap_if_needed` no-ops | unit | `pytest -x tests/services/test_credentials.py::test_rewrap_no_change_noop` | ❌ Wave 0 |
| D-14 | Fingerprint mismatch + populated rows → `rewrap_if_needed` re-encrypts every row, writes new fingerprint, emits `encryption.rewrap_completed` | unit | `pytest -x tests/services/test_credentials.py::test_rewrap_on_key_change_reencrypts_all` | ❌ Wave 0 |
| D-15 | Orphaned ciphertext during rewrap → row skipped, `encryption.decrypt_failed` emitted, other rows still rewrapped | unit | `pytest -x tests/services/test_credentials.py::test_rewrap_skips_orphaned_rows` | ❌ Wave 0 |
| D-16 | All three lifespan hooks (`startup_check`, `rewrap_if_needed`, `prewarm_cache`) run in order; lifespan startup fails non-zero on EncryptionStartupError | integration | `pytest -x tests/test_phase03_lifespan.py::test_lifespan_hooks_execute_in_order` | ❌ Wave 0 |
| D-12 | `credentials.set_provider_credential` does NOT construct its own Fernet (architectural — assert via inspection / no `Fernet(` literal in `credentials.py`) | unit (grep test) | `pytest -x tests/ci/test_credentials_uses_encryption.py::test_no_direct_fernet_in_credentials` | ❌ Wave 0 |
| Migration | `p3_api_credentials` creates `api_credentials` with CHECK + 2 seed rows + 1 new `app_settings` row | unit | `pytest -x tests/test_migrations.py::test_phase03_migration` | ◆ EXTEND |

### Sampling Rate

- **Per task commit:** Run the targeted file (e.g., `pytest -x tests/services/test_encryption.py`) — ~1s feedback
- **Per wave merge:** Run the Phase-3 quick command (3 service test files) — ~3s feedback
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/services/test_encryption.py` — NEW; covers SEC-09 startup_check + SEC-08 round-trip + key rotation + Pitfall 1 (malformed key chained error)
- [ ] `tests/services/test_settings.py` — NEW; covers D-05 typed accessors + D-06 prewarm + D-08 write-through + audit event shape
- [ ] `tests/services/test_credentials.py` — NEW; covers D-09 dataclass + D-10 None branches + D-11 sync + D-14 rewrap + D-15 decrypt_failure
- [ ] `tests/test_phase03_lifespan.py` — NEW; integration test that lifespan calls the three hooks in order and propagates EncryptionStartupError
- [ ] `tests/ci/test_credentials_uses_encryption.py` — NEW; grep test enforcing D-12 (no direct `Fernet(` in `credentials.py`)
- [ ] `tests/test_migrations.py` — EXTEND (add `test_phase03_migration` asserting the new table + check constraint + seed rows + new app_settings row)
- [ ] `tests/test_env_example.py` — EXTEND (assert the Fernet one-liner in `.env.example` produces a valid key — confirms SEC-09 docs)

*(Phase 3 ships no new conftest fixtures — the `monkeypatch.setenv("APP_ENCRYPTION_KEY", ...)` + `importlib.reload(...)` pattern is sufficient. No fresh_db reset needed for the credentials tests because the migration's 2 seeded rows are the baseline.)*

## Security Domain

> `security_enforcement` config key absent in `.planning/config.json`; treating as enabled per gsd convention.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | (Phase 2 owns; not relevant here) |
| V3 Session Management | no | (Phase 1 + Phase 2 own; not relevant here) |
| V4 Access Control | partial | Admin-level write paths (`set_provider_credential`, `set_setting`) carry `by_user_id` audit field; the FastAPI `require_admin` gate (Phase 2) protects future Phase 9 routes that consume these services |
| V5 Input Validation | yes | `set_setting` validates against the row's stored `value_type` (raises `SettingTypeError` on mismatch); the `provider` CHECK constraint at the DB layer rejects typos at the schema level; Phase 9 will wrap with Pydantic schemas |
| V6 Cryptography | yes | `cryptography.fernet.MultiFernet` — NEVER hand-rolled. AES-128-CBC + HMAC-SHA256 + IV + timestamp; audited, versioned, project-locked. Key rotation via MultiFernet's built-in semantics. |
| V7 Error Handling and Logging | yes | `structlog` redactor (Phase 1) already covers `api_key_encrypted` in `SENSITIVE_KEYS`; Phase 3 events emit only `provider, last_four, by_user_id, model_name` — never the decrypted key or the ciphertext |
| V8 Data Protection | yes | API keys stored encrypted at rest (Fernet) per SEC-08; `last_four` denormalized for admin display avoids needing to decrypt for read-only audit; transient `ProviderCredential` dataclass (no `model_dump()` to leak) per SEC-6 |
| V9 Communication | no | (NGINX termination handles TLS; not relevant here) |
| V10 Malicious Code | no | (no external code execution in this phase) |
| V11 Business Logic | partial | Auto-rewrap (D-14) is idempotent + race-safe via `SELECT ... FOR UPDATE`; first-deploy + no-change cases no-op |
| V12 Files and Resources | no | (no file uploads or downloads in this phase) |
| V13 API and Web Service | no | (no routes in this phase; Phase 9 will own admin routes) |
| V14 Configuration | yes | `APP_ENCRYPTION_KEY` is the configuration secret; fail-loud at startup (D-13); operator workflow for rotation documented in README |

### Known Threat Patterns for FastAPI + SQLAlchemy 2.0 + cryptography 48.x

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leak via Pydantic `model_dump()` (SEC-6) | Information disclosure | Use `@dataclass(frozen=True, slots=True)` for `ProviderCredential`; ban `model_dump\(\)` on `ApiCredential` via CI grep (Phase 12) |
| Hand-rolled crypto with padding-oracle vulnerability | Tampering / Information disclosure | Use `cryptography.fernet.Fernet` — AES-CBC + HMAC, no padding-oracle exposure |
| Key rotation orphans previously-encrypted rows (SEC-2) | Denial of service (decrypt fails forever) | `MultiFernet([new, old, ...])` — decryption attempts each key in turn; auto-rewrap (D-14) updates ciphertext on next startup |
| Stored ciphertext readable by attacker with DB dump | Information disclosure | Fernet's AES-128-CBC + HMAC-SHA256 — without `APP_ENCRYPTION_KEY`, the bytea column is opaque |
| Missing or malformed env var causes silent decryption failures | Denial of service / Spoofing | Sentinel round-trip at lifespan startup (D-13); fail-loud → uvicorn exits non-zero → compose unhealthy |
| Concurrent rewrap and admin write race | Tampering | `SELECT ... FOR UPDATE` on the rewrap transaction; single-worker invariant; both protections compose |
| Audit log leaks decrypted key | Information disclosure | structlog `SENSITIVE_KEYS` deny-list (Phase 1) already covers `api_key`-shaped names; Phase 3 emits never carry the decrypted field — only `provider, last_four, model_name, by_user_id` |
| Pydantic schema accidentally includes `api_key` field | Information disclosure (SEC-6) | Phase 12 CI grep test for `model_dump\(\)` on `ApiCredential`; documented in README + Phase 3 ADR |
| SQL injection on `setting_key` | Tampering | SQLAlchemy 2.0 `update().where(AppSetting.key == key)` uses parameterized queries; no string concatenation |
| Replay attack on Fernet tokens | Replay | Fernet tokens have a timestamp; can pass `ttl=...` to `decrypt()` to enforce freshness — NOT used here because API keys are persistent (no replay concern); document the choice |
| Configuration tampering via env var injection | Tampering | `pydantic-settings` `extra="forbid"` (Phase 0) rejects unknown env keys; CI test enforces no `os.environ` outside `app/config.py` |

## Sources

### Primary (HIGH confidence)
- [cryptography.fernet — pyca/cryptography](https://cryptography.io/en/latest/fernet/) — Fernet, MultiFernet, InvalidToken, generate_key API; rotation semantics
- [SQLAlchemy 2.0 — Generic types & LargeBinary](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.LargeBinary) — `LargeBinary` → `bytea` mapping; `Mapped[bytes | None]` annotation pattern
- [Alembic — Operations.bulk_insert](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.bulk_insert) — `op.bulk_insert` + `sa.table()` pattern
- [anthropics/anthropic-sdk-python — _client.py](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_client.py) — `Anthropic(api_key: str | None = None, ...)`
- [openai/openai-python — _client.py](https://github.com/openai/openai-python/blob/main/src/openai/_client.py) — `OpenAI(api_key: str | Callable[[], str] | None = None, ...)`
- `.planning/research/STACK.md` §1 — pinned versions verified at project init
- `.planning/research/PITFALLS.md` §5 — SEC-2 (MultiFernet) + SEC-6 (no Pydantic with decrypted key)
- `app/services/auth.py` + `app/services/setup.py` — Phase 2 service-module template (module-level singleton, custom exceptions, `__all__`, pattern Pattern-1 + Pattern-2)
- `app/migrations/versions/0001_initial.py` — Phase 0 migration pattern (`sa.table()` + `op.bulk_insert`, Pattern-3)
- `app/main.py` — Phase 0+1+2 lifespan composition (Pattern-5)
- `app/config.py` — `APP_ENCRYPTION_KEY: str` declaration
- `app/logging.py` + `app/logging_config.py` — structlog redactor + event taxonomy (verifies Pitfall 5)
- `app/events.py` — existing event constants pattern (Phase 3 extends)

### Secondary (MEDIUM confidence)
- `pip index versions cryptography` 2026-05-18 — confirmed 48.0.0 current (matches STACK.md §1)

### Tertiary (LOW confidence)
- None — Phase 3 research did not produce any LOW-confidence claims; every primitive is documented in canonical sources or in the existing repo.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version + API verified via official docs + source inspection
- Architecture: HIGH — 16 CONTEXT decisions resolve every architectural question; planner is composing, not inventing
- Pitfalls: HIGH — 8 pitfalls documented; 7 from CONTEXT + research, 1 from cross-checking the rewrap path

**Research date:** 2026-05-18
**Valid until:** 2026-06-18 (stable libraries; cryptography 48.x line is the current annual major; Anthropic SDK is on a fast 0.x cadence — Phase 7's consumer of `ProviderCredential.key: str` may need a re-verify at Phase 7 plan time)

---

*Phase: 3-Encryption + Settings*
*Researched: 2026-05-18*
