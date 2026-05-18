# Phase 3: Encryption + Settings - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 03-encryption-settings
**Areas discussed:** api_credentials schema + model_name location, Settings reader (cache + coercion + sync/async), Decrypted-key handoff contract to AI service, Startup validation + rotation mechanics

---

## api_credentials schema + model_name location

### Q1 — Row shape

| Option | Description | Selected |
|--------|-------------|----------|
| One row per provider (UPDATE) | PK or UNIQUE on provider; rotating overwrites. Simpler reads, clearer 'current key' semantics; loses key history. Matches PROJECT.md row 11. | ✓ |
| Append-only + is_active | New row per rotation, partial unique index on is_active. Preserves history; every read needs WHERE is_active=true. | |

**User's choice:** One row per provider (UPDATE).

### Q2 — Model name location

| Option | Description | Selected |
|--------|-------------|----------|
| On api_credentials.model_name | Atomic with key during rotation. Matches Roadmap §9 success #2. | ✓ |
| In app_settings (ai_model_anthropic / ai_model_openai) | Consistent with existing tool-version rows. Splits provider state across two tables. | |

**User's choice:** On api_credentials.model_name.

### Q3 — last_four

| Option | Description | Selected |
|--------|-------------|----------|
| Denormalized last_four column | Phase 9 renders without decrypt; logs can include masked tail. Tiny consistency cost. | ✓ |
| Derived on decrypt | Single source of truth; needless round-trip for a value final at write time. | |

**User's choice:** Denormalized api_credentials.last_four.

### Q4 — Seeded providers

| Option | Description | Selected |
|--------|-------------|----------|
| Seed both rows with is_enabled=false, NULL ciphertext | Phase 9 form is always UPDATE; provider set locked at schema; NULL-ciphertext is single branch. | ✓ |
| Insert-on-first-edit (UPSERT) | Row implies set; nothing to render until admin clicks add. | |

**User's choice:** Seed both rows with empty ciphertext.

---

## Settings reader (cache + coercion + sync/async)

### Q1 — Public API surface

| Option | Description | Selected |
|--------|-------------|----------|
| Typed accessors (get_str / get_int / get_bool / get_json) | Mirrors value_type column. Type-safe at call site. | ✓ |
| Generic get(key) returning coerced value | Returns Any; flexible, loses static type info. | |
| Single dataclass mirror of all rows | Readable; adding a row edits two places; null rows fight the schema. | |

**User's choice:** Typed accessors.

### Q2 — Cache strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-warm at lifespan startup | One SELECT * at boot; reads are dict lookups. Single-worker means cache is consistent. | ✓ |
| Lazy-load on first access | First request pays SQL hit; negligible win. | |
| TTL-based re-read (60s) | Out-of-band changes propagate; adds repeated I/O. | |

**User's choice:** Pre-warm at lifespan startup.

### Q3 — DB session style

| Option | Description | Selected |
|--------|-------------|----------|
| Sync via app/db.py engine | Matches catalog + scheduler. AI service calls inline; no await overhead. | ✓ |
| Async via AsyncSessionLocal | Phase 9 admin async-native; forces sync callers into wrapper. | |

**User's choice:** Sync via app/db.py engine.

### Q4 — Invalidation + audit

| Option | Description | Selected |
|--------|-------------|----------|
| Write-through invalidate + emit admin.app_setting_changed event | Adds one event constant to app/events.py; Phase 9 inherits. | ✓ |
| Write-through invalidate only — no audit event | Silent admin writes; loses Phase 1 audit stream. | |
| Both: invalidate + event + refresh_cache() endpoint | Belt-and-suspenders; useful if psql edits become workflow. | |

**User's choice:** Write-through invalidate + audit event.

---

## Decrypted-key handoff contract to AI service

### Q1 — Transport shape

| Option | Description | Selected |
|--------|-------------|----------|
| Frozen+slots ProviderCredential(provider, key, model_name, last_four) | Bundles everything Phase 7 needs; no Pydantic; satisfies SEC-6. | ✓ |
| Raw bytes / str only | Minimal; AI service queries model_name separately; risks drift on rotate. | |
| Context manager that zeroes buffer on exit | Overkill for Python; GC handles; no real security benefit. | |

**User's choice:** Transient frozen dataclass.

### Q2 — Missing / disabled provider

| Option | Description | Selected |
|--------|-------------|----------|
| Return None; caller branches | Matches Roadmap Phase 7 success #5; simple fallback. | ✓ |
| Raise ProviderUnavailableError | Explicit; same semantics with more boilerplate. | |

**User's choice:** Return None.

### Q3 — Sync vs async accessor

| Option | Description | Selected |
|--------|-------------|----------|
| Sync get_provider_credential(db, provider) | Pure CPU after cache warm; avoids await overhead. | ✓ |
| Async await get_provider_credential(provider) | Matches AI service idiom; async is theater under pre-warm cache. | |

**User's choice:** Sync.

### Q4 — Module split

| Option | Description | Selected |
|--------|-------------|----------|
| Two modules: services/encryption.py + services/credentials.py | Single-purpose; preserves "never bypass services/encryption.py" clearly; mirrors Phase 2 auth + setup split. | ✓ |
| One module doing both | Fewer files; conflates crypto with persistence + audit; ambiguates CLAUDE.md invariant. | |

**User's choice:** Two modules.

---

## Startup validation + rotation mechanics

### Q1 — Startup key verification

| Option | Description | Selected |
|--------|-------------|----------|
| Sentinel encrypt+decrypt round-trip in lifespan; raise on failure | Catches Fernet construction failure + runtime issues; single structured log line; non-zero exit. | ✓ |
| Trust Fernet constructor validation only | Sufficient in practice; misses subtler runtime issues. | |
| Both | Sentinel already exercises both paths; redundant. | |

**User's choice:** Sentinel round-trip.

### Q2 — Rotation flow

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-rewrap at startup when fingerprint mismatch detected | Stores SHA-256 of primary in app_settings; one TX; ≤2 rows; old keys removable on next deploy. | ✓ |
| Wait for next admin edit per row | Old primary must stay in env until each row touched; easy to forget. | |
| Admin 'Rotate now' button in Phase 9 | Same end state; defers work and depends on admin remembering. | |

**User's choice:** Auto-rewrap at startup on fingerprint mismatch.

### Q3 — Orphaned ciphertext

| Option | Description | Selected |
|--------|-------------|----------|
| Return None + emit encryption.decrypt_failed event | App stays up; admin can fix; consistent with disabled-provider None path. | ✓ |
| Raise EncryptionError and crash | Locks admin out of fixing; bad failure mode. | |
| Sentinel status on dataclass | Leaks crypto detail; adds third branch to AI service. | |

**User's choice:** Return None + emit event.

### Q4 — Hook location

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI lifespan startup block | After Alembic migrations; before serving traffic; structlog ready; exits cleanly on failure. | ✓ |
| Module import time in services/encryption.py | Catches earliest; raises before structlog is configured; ugly traceback. | |

**User's choice:** FastAPI lifespan startup block.

---

## Claude's Discretion

Listed inline in CONTEXT.md `<decisions>` under "Claude's Discretion":
- `provider` column type (text + CHECK vs Postgres ENUM)
- `key_ciphertext` column type (bytea vs text)
- Exact Phase 9 Pydantic form schemas (Phase 3 only lands the service-layer kwargs)
- Whether to wrap the rewrap transaction in `SELECT … FOR UPDATE` (forward-defense for multi-worker)
- Internal cache dataclass shape (NamedTuple vs frozen dataclass)
- Audit-event payload field naming for `admin.app_setting_changed`
- Test isolation approach (real per-test `Fernet.generate_key()` strongly preferred)
- SQLAlchemy `Mapped[bytes | None]` choice for `key_ciphertext`

## Deferred Ideas

Captured in CONTEXT.md `<deferred>`:
- Admin UI for credentials + app_settings (Phase 9)
- CI grep test for `model_dump()` on `ApiCredential` (Phase 12)
- API health panel surfacing decrypt-failure events (Phase 9 / ADMIN-06)
- Admin "Rotate now" button (Phase 9, optional)
- `SELECT … FOR UPDATE` on the rewrap transaction (planner's discretion)
- Third AI provider support (out of v1 scope)
- Per-row encryption-version column for future algorithm migration
- Bulk re-encrypt utility for non-`api_credentials` tables
- `settings.refresh_cache()` admin endpoint (Phase 9, optional)
- Redaction list for `admin.app_setting_changed` event payload (speculative)
