# Phase 3: Encryption + Settings - Pattern Map

**Mapped:** 2026-05-18
**Files analyzed:** 11 (3 new services, 1 new model, 1 migration, 2 model file edits, `app/main.py` lifespan, `app/events.py` extension, 4 new test files)
**Analogs found:** 11 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/encryption.py` (NEW) | service / utility (pure crypto primitives) | transform (request-response, no DB) | `app/signing.py` (module-level signer, pure transforms over `settings.APP_SECRET_KEY`) + `app/services/auth.py` (module-level `_ph` singleton + `__all__` export discipline) | exact |
| `app/services/settings.py` (NEW) | service (typed reader + cache + write-through) | CRUD + cache (sync DB) | `app/services/sessions.py` (sync-ish DB CRUD helpers; the lifecycle helper for an Alembic-managed table) + `app/services/auth.py` (module-level cache pattern via `_ph`) | role-match (sessions is async; auth is sync; combine for the sync+cache shape) |
| `app/services/credentials.py` (NEW) | service (provider-credential CRUD + transient dataclass) | CRUD + transform | `app/services/setup.py` (single-transaction service with `with_for_update()` + audit emit at the call site) + `app/services/sessions.py` (table-private CRUD helper pattern) | role-match |
| `app/models/api_credential.py` (NEW) | model (SQLAlchemy 2.0 Mapped[...] row) | persistence | `app/models/app_setting.py` (Text PK, nullable value column, FK to users ON DELETE SET NULL, timestamptz with `server_default=func.now()`) + `app/models/session.py` (compact two-comment header style + `__tablename__` placement) | exact |
| `app/migrations/versions/p3_api_credentials.py` (NEW) | migration | DDL + seed insert | `app/migrations/versions/p1_sessions_table.py` (revision-id style, single `op.create_table`, btree indexes, clean reverse-order `downgrade`) + `app/migrations/versions/0001_initial.py` lines 196-359 (`sa.table()` + `op.bulk_insert()` for `app_settings` seed rows) | exact |
| `app/models/__init__.py` (MODIFY) | model registry | import-side-effect for Alembic autogenerate | itself (existing pattern at lines 15-31) | exact |
| `app/events.py` (MODIFY) | constant module | append-only string constants | itself (existing pattern at lines 38-71) | exact |
| `app/main.py` (MODIFY) | app factory / lifespan wiring | startup-shutdown | itself — existing `lifespan` body at `app/main.py:133-146` (Phase 3 adds 3 sync calls after the `SELECT 1` smoke) | exact |
| `tests/services/test_encryption.py` (NEW) | test (pure unit, no DB) | request-response | `tests/services/test_auth.py` (lazy-import gate via `_require_*_service()`; module-level singleton introspection via `_ph` reach-through) | exact |
| `tests/services/test_settings.py` (NEW) | test (DB + cache + audit-event capture) | CRUD + transform | `tests/services/test_setup.py` (DB-integration tests; `_require_postgres()` probe; `event.listen` on the engine to capture SQL) + `tests/test_logging.py` lines 37-82 (StringIO-backed capture handler for structlog assertions) | role-match (compose two patterns) |
| `tests/services/test_credentials.py` (NEW) | test (DB + crypto round-trip + audit-event capture) | CRUD + transform | `tests/services/test_setup.py` (multi-test file with module-level skip helpers + `async_session_factory` direct use, but Phase 3 swaps to **sync** `SessionLocal`) | role-match |
| `tests/test_migrations.py` (MODIFY) | test (schema introspection) | persistence (read-only) | itself — existing `pg_session` fixture at lines 40-61 + the per-table column tests at lines 92-202 | exact |

## Pattern Assignments

### `app/services/encryption.py` (service, pure crypto primitives)

**Analog:** `app/signing.py` + `app/services/auth.py`

**Imports pattern** (from `app/signing.py` lines 17-23 — module-level signer bound to one settings field):
```python
from __future__ import annotations

import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings
```

**Module-level singleton pattern** (mirror `app/signing.py:29` and `app/services/auth.py:51-56`):
```python
# Build once at import; Phase 0 D-18 / CONTEXT D-13: APP_ENCRYPTION_KEY is a
# comma-separated string. First key = primary for encryption; all attempted
# for decryption (MultiFernet rotation behavior).
def _build_multi_fernet() -> MultiFernet:
    keys = [k.strip() for k in settings.APP_ENCRYPTION_KEY.split(",") if k.strip()]
    if not keys:
        raise EncryptionStartupError("APP_ENCRYPTION_KEY produced zero valid keys")
    return MultiFernet([Fernet(k.encode("utf-8")) for k in keys])


_multi_fernet: MultiFernet = _build_multi_fernet()
```

**Custom exception chained pattern** (CONTEXT `<specifics>` "EncryptionStartupError is a custom exception ... subclass of RuntimeError, chains the underlying cryptography error"):
```python
class EncryptionStartupError(RuntimeError):
    """Raised by startup_check() when the sentinel round-trip fails.

    Chains the underlying ``cryptography.fernet.InvalidToken`` or
    ``binascii.Error`` so the operator sees the root cause in the
    structured-log chain. Propagates out of ``lifespan`` → uvicorn
    exits non-zero → docker-compose healthcheck flips unhealthy.
    """
```

**Public surface pattern** (mirror `app/signing.py:62` and `app/services/auth.py:116`):
```python
def encrypt(plaintext: bytes) -> bytes: ...
def decrypt(ciphertext: bytes) -> bytes: ...
def primary_key_fingerprint() -> str:
    """Hex SHA-256 of the first key in APP_ENCRYPTION_KEY (D-14 rotation detector)."""
    primary = settings.APP_ENCRYPTION_KEY.split(",", 1)[0].strip().encode("utf-8")
    return hashlib.sha256(primary).hexdigest()


def startup_check() -> None:
    """Sentinel round-trip (D-13). Emits encryption.startup_ok on success."""
    ...


__all__ = ["EncryptionStartupError", "decrypt", "encrypt", "primary_key_fingerprint", "startup_check"]
```

**Structlog audit-emit pattern** (from `app/main.py:95,142`): module-level logger + named event constant + kwargs only:
```python
import structlog
from app.events import ENCRYPTION_STARTUP_OK

log = structlog.get_logger(__name__)

# Inside startup_check on success:
log.info(ENCRYPTION_STARTUP_OK)
# On failure: raise EncryptionStartupError("...") from exc
```

---

### `app/services/settings.py` (service, typed reader + cache + write-through)

**Analog:** `app/services/sessions.py` (CRUD shape) + `app/services/auth.py` (module-level singleton)

**Imports pattern** (mirror `app/services/sessions.py:32-40` but **sync** session per D-07):
```python
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
```

**Module-level cache pattern** (Claude's discretion in CONTEXT — frozen dataclass is the planner's pick; mirrors `_DUMMY_HASH` at `app/services/auth.py:67`):
```python
@dataclass(frozen=True, slots=True)
class _CachedSetting:
    value: str | None
    value_type: str
    coerced: Any


_cache: dict[str, _CachedSetting] = {}


class SettingNotFoundError(KeyError):
    """Raised when a key is queried but does not exist in ``app_settings``."""


class SettingTypeError(TypeError):
    """Raised when an accessor's expected type does not match the row's value_type."""
```

**Prewarm pattern** (D-06; mirror `select()` style from `app/services/sessions.py:118-126` but using sync `Session`):
```python
def prewarm_cache(db: Session) -> None:
    """Single SELECT * FROM app_settings → populate module-level cache. D-06."""
    _cache.clear()
    rows = db.execute(select(AppSetting)).scalars().all()
    for row in rows:
        _cache[row.key] = _CachedSetting(
            value=row.value,
            value_type=row.value_type,
            coerced=_coerce(row.value, row.value_type),
        )
```

**Typed accessor pattern** (D-05; raises `SettingTypeError` on type mismatch; `'null'` rows return None):
```python
def get_str(key: str) -> str | None:
    cached = _cache.get(key)
    if cached is None:
        raise SettingNotFoundError(key)
    if cached.value_type == "null":
        return None
    if cached.value_type != "string":
        raise SettingTypeError(f"{key!r} is {cached.value_type!r}, not 'string'")
    return cached.coerced  # str | None
```

**Write-through + audit pattern** (D-08; mirror the `update()` pattern at `app/services/setup.py:159-161`):
```python
def set_setting(
    db: Session,
    key: str,
    value: Any,
    *,
    by_user_id: int | None,
) -> None:
    """Validate value_type, UPDATE row, pop cache, emit audit event. D-08."""
    cached = _cache.get(key) or _load_one(db, key)
    old_value = cached.value
    serialized = _serialize(value, cached.value_type)
    db.execute(
        update(AppSetting)
        .where(AppSetting.key == key)
        .values(value=serialized, updated_by_user_id=by_user_id)
    )
    db.commit()
    _cache.pop(key, None)  # Re-loaded on next access.
    log.info(
        ADMIN_APP_SETTING_CHANGED,
        setting_key=key,
        old_value=old_value,
        new_value=serialized,
        value_type=cached.value_type,
        user_id=by_user_id,
    )
```

**Public surface and exports** (mirror `app/services/sessions.py:190-200`):
```python
__all__ = [
    "SettingNotFoundError",
    "SettingTypeError",
    "get_bool",
    "get_int",
    "get_json",
    "get_raw",
    "get_str",
    "invalidate",
    "prewarm_cache",
    "set_setting",
]
```

---

### `app/services/credentials.py` (service, api_credentials CRUD + transient dataclass)

**Analog:** `app/services/setup.py` (single-transaction service + audit emit) + `app/services/sessions.py` (table-private CRUD)

**Imports + dataclass pattern** (D-09 mandates frozen+slots; `Literal` type alias matches D-04 CHECK):
```python
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
from app.services import encryption, settings as settings_service

log = structlog.get_logger(__name__)

Provider = Literal["anthropic", "openai"]


@dataclass(frozen=True, slots=True)
class ProviderCredential:
    """Transient handoff to Phase 7 AI service. Lives only in caller scope.

    NEVER serialized through Pydantic (PITFALL SEC-6). The ``key`` field is
    str (not bytes) — both Anthropic and OpenAI SDKs accept ``api_key: str``.
    """

    provider: Provider
    key: str
    model_name: str
    last_four: str
```

**Get pattern (decrypt-failure path returns None + emits event)** (D-10, D-15; mirror `app/services/sessions.py:118-126` for read shape):
```python
def get_provider_credential(db: Session, provider: Provider) -> ProviderCredential | None:
    """D-10: returns None on missing/disabled/null-ciphertext/decrypt-failure."""
    row = db.execute(
        select(ApiCredential).where(ApiCredential.provider == provider)
    ).scalar_one_or_none()
    if row is None or not row.is_enabled or row.key_ciphertext is None:
        return None
    try:
        plain = encryption.decrypt(row.key_ciphertext)
    except InvalidToken:
        # D-15: app stays up; admin sees event; Phase 7 sees "no credential".
        log.warning(ENCRYPTION_DECRYPT_FAILED, provider=provider)
        return None
    return ProviderCredential(
        provider=provider,
        key=plain.decode("utf-8"),
        model_name=row.model_name or "",
        last_four=row.last_four or "",
    )
```

**Set / rotate pattern + audit emit** (D-03 writes `last_four = key[-4:]`; mirrors `app/services/setup.py:159-161` UPDATE pattern + audit at `app/routers/auth.py:192-197`):
```python
def set_provider_credential(
    db: Session,
    provider: Provider,
    *,
    key: str,
    model_name: str,
    by_user_id: int | None,
) -> None:
    """D-01 + D-03: UPDATE existing seeded row; write last_four denormalized."""
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
    db.commit()
    log.info(
        ADMIN_API_CREDENTIAL_SET,
        provider=provider,
        last_four=last_four,
        user_id=by_user_id,
    )
```

**Rewrap pattern with FOR UPDATE** (D-14; mirrors `app/services/setup.py:133-134` `with_for_update()` + transactional commit):
```python
def rewrap_if_needed(db: Session) -> None:
    """D-14: auto-rewrap when fingerprint changes. Bounded to ≤2 rows."""
    new_fp = encryption.primary_key_fingerprint()
    try:
        stored_fp = settings_service.get_str("encryption_key_primary_fingerprint")
    except settings_service.SettingNotFoundError:
        stored_fp = None  # Pre-prewarm path: row exists in DB but cache empty.

    rows = db.execute(
        select(ApiCredential)
        .where(ApiCredential.key_ciphertext.is_not(None))
        .with_for_update()  # belt-and-suspenders (CONTEXT discretion)
    ).scalars().all()

    if stored_fp == new_fp or (stored_fp is None and not rows):
        return

    for row in rows:
        plain = encryption.decrypt(row.key_ciphertext)
        row.key_ciphertext = encryption.encrypt(plain)
    settings_service.set_setting(
        db, "encryption_key_primary_fingerprint", new_fp, by_user_id=None
    )
    db.commit()
    log.info(ENCRYPTION_REWRAP_COMPLETED, row_count=len(rows))
```

---

### `app/models/api_credential.py` (NEW model, SQLAlchemy 2.0)

**Analog:** `app/models/app_setting.py` (closest by FK pattern + nullable columns) + `app/models/session.py` (compact docstring style)

**Imports + class shape** (mirror `app/models/app_setting.py:14-23`):
```python
"""``api_credentials`` table — admin-managed AI provider keys (D-01).

One row per provider (``'anthropic'``, ``'openai'``). Migration p3 seeds
both rows with ``is_enabled=false`` and ``key_ciphertext=NULL`` (D-04);
the Phase 9 admin form is always an UPDATE, never an INSERT. CLAUDE.md
"Architectural invariants": AI keys live encrypted in the DB, not env
vars. Never bypass ``services/encryption.py``.

``last_four`` is denormalized (D-03) so the Phase 9 admin list view can
mask the key without invoking the encryption service. The ciphertext is
``Mapped[bytes | None]`` because the seeded empty-state rows have NULL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, LargeBinary, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ApiCredential(Base):
    """One row per AI provider; UPDATE on rotation (D-01)."""

    __tablename__ = "api_credentials"

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
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "provider IN ('anthropic', 'openai')",
            name="api_credentials_provider_check",
        ),
    )
```

**Why these choices map to the analog:**
- `Mapped[int | None]` + `ForeignKey("users.id", ondelete="SET NULL")` is a verbatim copy of `app/models/app_setting.py:40-44`.
- `TIMESTAMP(timezone=True)` with `server_default=func.now()` is verbatim from `app/models/app_setting.py:37-39`.
- `__tablename__` placement (one blank line after docstring) follows both analog modules.

---

### `app/migrations/versions/p3_api_credentials.py` (NEW migration)

**Analog:** `app/migrations/versions/p1_sessions_table.py` (revision-id + single table shape) + `app/migrations/versions/0001_initial.py:218-359` (`op.bulk_insert` seed pattern)

**Header + revision identifiers** (verbatim shape from `p1_sessions_table.py:1-43`):
```python
"""p3_api_credentials: api_credentials table + seed + new app_settings row

Revision ID: p3_api_credentials
Revises: p1_sessions
Create Date: 2026-05-18

Creates the ``api_credentials`` table (Phase 3 D-01..D-04), seeds two
provider rows (``'anthropic'``, ``'openai'``) with ``is_enabled=false`` and
``key_ciphertext=NULL`` per D-04, and inserts the new
``encryption_key_primary_fingerprint`` row into ``app_settings``
(value=NULL, value_type='null') so D-14's rotation-detector has a row to
read on first lifespan startup.

Requirements traceability:
* SEC-08 — Fernet-encrypted API keys at rest (MultiFernet day-one)
* SEC-09 — Fingerprint storage enables auto-rewrap on rotation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p3_api_credentials"
down_revision: str | Sequence[str] | None = "p1_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```

**Create-table pattern** (mirror `p1_sessions_table.py:46-67` + 0001_initial `app_settings`):
```python
def upgrade() -> None:
    op.create_table(
        "api_credentials",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("key_ciphertext", sa.LargeBinary, nullable=True),  # bytea
        sa.Column("last_four", sa.Text, nullable=True),
        sa.Column("model_name", sa.Text, nullable=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'openai')",
            name="api_credentials_provider_check",
        ),
    )
```

**Bulk-insert seed pattern** (verbatim shape from `0001_initial.py:218-230`):
```python
    # Lightweight sa.table() — migration body must NOT import app.models
    # (Alembic-safe pattern from 0001_initial.py).
    api_credentials_table = sa.table(
        "api_credentials",
        sa.column("provider", sa.Text),
        sa.column("is_enabled", sa.Boolean),
    )
    op.bulk_insert(
        api_credentials_table,
        [
            {"provider": "anthropic", "is_enabled": False},
            {"provider": "openai", "is_enabled": False},
        ],
    )

    # New app_settings row for D-14 rotation detector.
    app_settings_table = sa.table(
        "app_settings",
        sa.column("key", sa.Text),
        sa.column("value", sa.Text),
        sa.column("value_type", sa.Text),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        app_settings_table,
        [
            {
                "key": "encryption_key_primary_fingerprint",
                "value": None,
                "value_type": "null",
                "description": (
                    "SHA-256 hex of the current primary Fernet key; written by "
                    "credentials.rewrap_if_needed when the key rotates (D-14)."
                ),
            },
        ],
    )
```

**Downgrade** (mirror `p1_sessions_table.py:70-74`):
```python
def downgrade() -> None:
    op.execute(
        "DELETE FROM app_settings WHERE key = 'encryption_key_primary_fingerprint'"
    )
    op.drop_table("api_credentials")
```

---

### `app/models/__init__.py` (MODIFY)

**Analog:** itself (lines 15-31).

**Concrete edit** — add the new import + extend `__all__` (the docstring already documents the rule):
```python
from app.models.ai_recommendation import AIRecommendation
from app.models.api_credential import ApiCredential  # NEW
from app.models.app_setting import AppSetting
# ... existing imports unchanged ...

__all__ = [
    "AIRecommendation",
    "ApiCredential",  # NEW
    "AppSetting",
    # ... existing entries unchanged ...
]
```

---

### `app/events.py` (MODIFY)

**Analog:** itself (lines 38-71).

**Concrete edit** — append five constants matching the existing dotted-snake convention; extend `__all__`:
```python
# --- admin.* (Phase 9 wires) ----------------------------------------------
# ... existing admin.* constants unchanged ...
ADMIN_APP_SETTING_CHANGED = "admin.app_setting_changed"
ADMIN_API_CREDENTIAL_SET = "admin.api_credential_set"  # noqa: S105 — event name, not a credential

# --- encryption.* (Phase 3) -----------------------------------------------
# Lifespan-emitted events have no request_id (no request context); per
# CONTEXT <specifics> "use request_id=None or omit". Operational events
# the admin/operator reads to confirm key rotation and decrypt failures.
ENCRYPTION_STARTUP_OK = "encryption.startup_ok"
ENCRYPTION_REWRAP_COMPLETED = "encryption.rewrap_completed"
ENCRYPTION_DECRYPT_FAILED = "encryption.decrypt_failed"
```

Then extend `__all__` with the five new names (alphabetical, matching the existing block at lines 61-72).

---

### `app/main.py` (MODIFY — lifespan)

**Analog:** itself — existing `lifespan` body at lines 133-146.

**Imports to add** (top of file, alphabetical with existing `from app.X import Y` block at lines 73-88):
```python
from app.db import SessionLocal, dispose_engine, engine  # SessionLocal is NEW here
from app.services import credentials, settings as settings_service
from app.services.encryption import startup_check as encryption_startup_check
```

**Lifespan body extension** (D-16; insert AFTER the `SELECT 1` smoke, BEFORE `log.info("app.startup", ...)`):
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup smoke + Phase 3 hooks (D-16) + clean shutdown."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    # Phase 3 hooks (D-16). All three are sync; await-free is fine inside the
    # async lifespan body. startup_check runs FIRST so a bad APP_ENCRYPTION_KEY
    # fails fast before any DB I/O. rewrap_if_needed runs BEFORE prewarm_cache
    # so the new fingerprint written by rewrap lands in the cache.
    encryption_startup_check()  # raises EncryptionStartupError → uvicorn exits non-zero
    with SessionLocal() as db:
        credentials.rewrap_if_needed(db)
        settings_service.prewarm_cache(db)

    log.info("app.startup", version=app.version)
    yield
    log.info("app.shutdown")
    dispose_engine()
    await _async_engine.dispose()
```

**Why this order matches D-16 verbatim:** the three calls are inserted after `SELECT 1` (Phase 0 invariant) and before the `app.startup` event so a startup-time encryption failure does not emit `app.startup` — operators looking at the log stream see the exception chain instead.

---

### `tests/services/test_encryption.py` (NEW — unit, no DB)

**Analog:** `tests/services/test_auth.py` (lazy-import gate + module-level singleton introspection).

**Lazy-import gate pattern** (verbatim shape from `tests/services/test_auth.py:29-42`):
```python
from __future__ import annotations

import pytest


def _require_encryption_service() -> None:
    """Skip cleanly until Phase 3 lands ``app.services.encryption``."""
    try:
        from app.services.encryption import (  # noqa: F401
            EncryptionStartupError,
            decrypt,
            encrypt,
            primary_key_fingerprint,
            startup_check,
        )
    except ImportError:
        pytest.skip("Phase 3 dependency: app.services.encryption")
```

**Round-trip test pattern** (mirror `test_argon2_roundtrip` at `tests/services/test_auth.py:45-56`):
```python
def test_encrypt_decrypt_roundtrip() -> None:
    """SEC-08: encrypt(plaintext) → decrypt → plaintext identical."""
    _require_encryption_service()
    from app.services.encryption import decrypt, encrypt

    plaintext = b"sk-ant-test-key-not-real"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext
```

**Rotation test pattern using real keys per test** (CONTEXT discretion: use `Fernet.generate_key()` per test; no mocks):
```python
def test_multifernet_decrypts_under_old_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """MultiFernet decrypts a token encrypted under any configured key."""
    _require_encryption_service()
    from cryptography.fernet import Fernet

    old = Fernet.generate_key().decode("utf-8")
    new = Fernet.generate_key().decode("utf-8")
    # Stage 1: old key only — encrypt under it.
    monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", old)
    # ... re-import module via importlib or rebuild _multi_fernet ...
```

(Planner picks the rebuild-mechanism — module reload vs a `_rebuild_multi_fernet()` helper. Test posture documented in CONTEXT `<specifics>`: "Tests use ``Fernet.generate_key()`` per test — no shared keys, no respx".)

---

### `tests/services/test_settings.py` (NEW — DB + cache + audit-event capture)

**Analog:** `tests/services/test_setup.py` (`_require_postgres()` gate + `event.listen` to capture SQL) + `tests/test_logging.py:37-82` (StringIO capture handler for structlog audit assertions).

**Postgres reachability gate** (verbatim from `tests/services/test_setup.py:32-43`):
```python
def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — service test needs the DB")
```

**Sync-session test body pattern** (Phase 3 commits to **sync** via D-07, so swap `async_session_factory()` for `SessionLocal()`):
```python
def test_prewarm_then_get_str_returns_seed_value() -> None:
    """D-06 prewarm + D-05 get_str: cached read returns seeded recommendation_region."""
    _require_settings_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)

    # Cache-only call site — no db argument.
    assert settings_service.get_str("recommendation_region") == "US"
```

**Audit-event capture pattern** (mirror `tests/test_logging.py:37-82` StringIO handler — but planner may simplify to `structlog.testing.capture_logs` for unit tests; reuse the existing pattern for end-to-end):
```python
def test_set_setting_emits_admin_app_setting_changed() -> None:
    """D-08: set_setting emits structured event with setting_key/old/new/value_type."""
    _require_settings_service()
    _require_postgres()
    import structlog

    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        with structlog.testing.capture_logs() as captured:
            settings_service.set_setting(
                db, "home_recent_brews_limit", 20, by_user_id=None
            )

    events = [e for e in captured if e.get("event") == "admin.app_setting_changed"]
    assert len(events) == 1
    assert events[0]["setting_key"] == "home_recent_brews_limit"
    assert events[0]["new_value"] == "20"
    assert events[0]["value_type"] == "int"
```

---

### `tests/services/test_credentials.py` (NEW — DB + crypto + audit)

**Analog:** Combine `tests/services/test_setup.py` (multi-test file, `_require_*` gates, full DB) with the sync-session swap from `tests/services/test_settings.py` above.

**Test list** (per CONTEXT `<code_context>`):
1. `test_set_provider_credential_writes_ciphertext_and_last_four` — D-01 + D-03.
2. `test_get_provider_credential_disabled_returns_none` — D-10.
3. `test_get_provider_credential_null_ciphertext_returns_none` — D-10.
4. `test_get_provider_credential_decrypt_failure_returns_none_and_emits_event` — D-15; uses `structlog.testing.capture_logs`.
5. `test_rotate_overwrites_existing_row` — D-01 (rotate = UPDATE, not INSERT).
6. `test_rewrap_when_fingerprint_changes` — D-14 happy path; verify ciphertext changes AND fingerprint app_setting row updates.
7. `test_rewrap_noop_when_no_populated_rows` — D-14 first-deploy edge case (CONTEXT `<specifics>`).
8. `test_set_provider_credential_emits_admin_api_credential_set` — D-08 + audit emit.

---

### `tests/test_migrations.py` (MODIFY — extend, do not rewrite)

**Analog:** itself — extend the existing `pg_session` fixture-based pattern at lines 40-202.

**New tests to append** (each mirrors `test_bags_columns` / `test_app_settings_critical_keys_present` shape):
- `test_api_credentials_table_exists` — mirror `test_five_tables_exist:77-89`.
- `test_api_credentials_columns` — mirror `test_bags_columns:92-125` (assert types + nullability for the 8 columns).
- `test_api_credentials_provider_check_constraint` — query `information_schema.check_constraints`.
- `test_api_credentials_seeded_with_two_rows` — mirror `test_app_settings_seeded_with_19_rows:204-212`.
- `test_app_settings_has_encryption_key_primary_fingerprint_row` — mirror `test_app_settings_critical_keys_present:215-244`.

## Shared Patterns

### Structlog audit emission
**Source:** `app/main.py:95,142` + `app/routers/auth.py:84,192-197`
**Apply to:** `services/encryption.py`, `services/settings.py`, `services/credentials.py`
```python
import structlog

log = structlog.get_logger(__name__)

# Always emit via a named constant from app.events — never hard-code event strings:
log.info(ADMIN_APP_SETTING_CHANGED, setting_key=key, old_value=old, new_value=new, value_type=vt, user_id=by_user_id)
```
The structlog config (`app/logging.py:55-75`) already redacts `api_key`, `api_key_encrypted`, `secret`, `encryption_key`. Phase 3 must not introduce new sensitive-key spellings without adding them to `SENSITIVE_KEYS`.

### Module-level singleton constructed at import time
**Source:** `app/signing.py:29` + `app/services/auth.py:51` + `app/services/auth.py:67`
**Apply to:** `services/encryption.py` (`_multi_fernet`), `services/settings.py` (`_cache`)
```python
# Build expensive object exactly once at module import; never re-construct
# per call. Mirrors PasswordHasher and URLSafeSerializer instantiation.
_multi_fernet: MultiFernet = _build_multi_fernet()
_cache: dict[str, _CachedSetting] = {}
```

### `__all__` discipline + leading-underscore private surfaces
**Source:** `app/services/auth.py:116`, `app/signing.py:62`, `app/services/sessions.py:190-200`
**Apply to:** all three new service modules
```python
__all__ = [<public function names alphabetized>]
# Tests may reach into _ph / _DUMMY_HASH / _cache via "sanctioned test-side access";
# production code never imports a leading-underscore name from another module.
```

### Lazy-import gate in test files
**Source:** `tests/services/test_auth.py:29-42`, `tests/services/test_setup.py:24-30`
**Apply to:** all three new test files
```python
def _require_<service>_service() -> None:
    try:
        from app.services.<module> import <public names>  # noqa: F401
    except ImportError:
        pytest.skip("Phase 3 dependency: app.services.<module>")
```
Lets tests be committed BEFORE the implementation lands without breaking pytest collection.

### Postgres reachability probe for DB-touching tests
**Source:** `tests/conftest.py:270-298` (`_postgres_reachable`) + `tests/services/test_setup.py:32-43` (`_require_postgres`)
**Apply to:** `test_settings.py`, `test_credentials.py`, the new appendages to `test_migrations.py`
```python
def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — service test needs the DB")
```

### Sync DB session via `SessionLocal()` context manager
**Source:** `app/db.py:15-22` (docstring example) + `app/main.py:140` (`engine.connect()` style in lifespan)
**Apply to:** every call site in `services/settings.py`, `services/credentials.py`, the three lifespan additions, and the sync test bodies
```python
from app.db import SessionLocal

with SessionLocal() as db:
    # ... db.execute(select(...)) / db.execute(update(...)) ; db.commit()
```
Phase 3 commits to **sync** per D-07 / D-11. The auth surface uses `async_session_factory` from `app/main.py:104-105` and `app/dependencies/db.py:32`; Phase 3 does NOT touch that path.

### Alembic-safe migration body (no app.models import)
**Source:** `app/migrations/versions/0001_initial.py:222-228` ("Lightweight `sa.table()` used here so the migration is self-contained and does NOT depend on the SQLAlchemy ORM model classes")
**Apply to:** `app/migrations/versions/p3_api_credentials.py`
Migration uses `sa.table()` + `sa.column()` + `op.bulk_insert()` for the seed rows; never `from app.models import ApiCredential` inside the migration body — that would close a circular import the moment the ORM model is renamed.

## No Analog Found

All Phase 3 deliverables have strong codebase analogs. No file needs to fall back to RESEARCH-only patterns.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | None — Phases 0/1/2 established analogs for every Phase 3 file. |

## Metadata

**Analog search scope:** `app/services/`, `app/models/`, `app/migrations/versions/`, `app/`, `tests/services/`, `tests/`
**Files scanned:** 18 (8 model/service modules, 2 migrations, `app/main.py`, `app/events.py`, `app/config.py`, `app/db.py`, `app/logging.py`, `app/signing.py`, 4 test files)
**Pattern extraction date:** 2026-05-18
