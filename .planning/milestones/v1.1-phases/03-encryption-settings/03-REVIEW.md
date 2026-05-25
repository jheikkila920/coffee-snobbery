---
phase: 03-encryption-settings
reviewed: 2026-05-18T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - app/events.py
  - app/main.py
  - app/migrations/versions/p3_api_credentials.py
  - app/models/__init__.py
  - app/models/api_credential.py
  - app/services/credentials.py
  - app/services/encryption.py
  - app/services/settings.py
  - tests/conftest.py
  - tests/services/test_credentials.py
  - tests/services/test_encryption.py
  - tests/services/test_settings.py
  - tests/test_lifespan_phase3.py
  - tests/test_migrations.py
findings:
  critical: 2
  warning: 3
  info: 3
  total: 8
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-18
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 3 delivers the encryption primitives, settings cache, credentials CRUD, and lifespan wiring. The security-critical invariants are mostly upheld: no raw keys in log calls, encryption module is the sole Fernet instantiation site, `ProviderCredential` is a frozen+slots dataclass rather than a Pydantic model. The lifespan hook order matches D-16.

Two blockers were found. The first is a correctness bug: `ApiCredential.updated_at` uses `onupdate=func.now()` but the production code exclusively uses SQLAlchemy Core `update()` statements, not ORM-level attribute assignment. SQLAlchemy's `onupdate` only fires on ORM flush; Core UPDATE bypasses it entirely, so `updated_at` never advances on key rotation, enable/disable, or rewrap. The second is a subtle but real security gap: the `set_provider_credential` path reads the stored fingerprint via the settings cache before the credential UPDATE is committed. The cache may contain a stale `None` for the fingerprint key even after a prior `set_provider_credential` already wrote and committed a real fingerprint value (because `invalidate()` only drops the key, not re-reads it). On the second call, `stored_fp is None` is `False` (if the cache was warmed after the first write) but the inline fingerprint UPDATE block is silently skipped, leaving the fingerprint stale if the primary key has changed between the two calls. This is a narrower window than it first appears, but the logic is objectively incorrect for the rotation-then-set sequence.

Three warnings cover: the `rewrap_if_needed` FOR UPDATE lock acquires rows but then returns early without committing or releasing the lock cleanly on the no-op path (the session context manager handles this, but the lock is held unnecessarily through the early-return branches); the `monkeypatched_app_encryption_key` fixture does not restore `_multi_fernet` after the test, leaving a contaminated module state for subsequent tests in the same session; and `set_setting` accepts `value: Any` but does not validate the incoming type against `value_type` before storing, so a caller can silently write `"true"` into an `int` row.

---

## Critical Issues

### CR-01: `updated_at` never advances on Core UPDATE statements

**File:** `app/models/api_credential.py:67-72`

**Issue:** `updated_at` is declared with `onupdate=func.now()`:

```python
updated_at: Mapped[datetime] = mapped_column(
    TIMESTAMP(timezone=True),
    nullable=False,
    server_default=func.now(),
    onupdate=func.now(),
)
```

SQLAlchemy's Python-side `onupdate` hook fires **only when the ORM emits an UPDATE via `Session.flush()`** (i.e., when the ORM detects a dirty mapped object). It is silently ignored by the `db.execute(update(ApiCredential).where(...).values(...))` Core-style UPDATE that `set_provider_credential`, `set_provider_enabled`, and `rewrap_if_needed` all use exclusively.

The result: `updated_at` is permanently frozen at the `created_at` value for every row after the migration seeds it. Key rotations, enable/disable toggles, and rewrap events produce no timestamp change. The column exists for auditing and the Phase 9 admin view will display it, making this a silent data integrity failure.

`server_onupdate` is the correct mechanism for a server-side trigger, but PostgreSQL does not fire it automatically either — it requires a trigger or explicit inclusion in the VALUES clause. The practical fix is to include `updated_at` explicitly in every Core UPDATE:

**Fix:** Two options. Preferred: add `server_onupdate=FetchedValue()` AND include `updated_at=func.now()` in every `values(...)` call in `credentials.py`. Simpler and consistent with the rest of the codebase's explicit-values pattern:

```python
# In set_provider_credential, set_provider_enabled, and rewrap_if_needed:
.values(
    ...,
    updated_at=func.now(),  # add this to every Core UPDATE on api_credentials
)
```

Remove the `onupdate=func.now()` from the model column definition to avoid giving future readers the false impression the timestamp auto-advances:

```python
updated_at: Mapped[datetime] = mapped_column(
    TIMESTAMP(timezone=True),
    nullable=False,
    server_default=func.now(),
    # onupdate removed — model uses Core UPDATE statements exclusively
)
```

The migration already uses `server_default=sa.func.now()` for `updated_at` and does not need changing.

---

### CR-02: Fingerprint baseline write in `set_provider_credential` can be silently skipped on second call after key change

**File:** `app/services/credentials.py:239-261`

**Issue:** The baseline-write guard reads `stored_fp` from the settings cache:

```python
try:
    stored_fp = settings_service.get_str(_FINGERPRINT_KEY)
except settings_service.SettingNotFoundError:
    stored_fp = None
if stored_fp is None:
    db.execute(update(AppSetting)...)
    settings_service.invalidate(_FINGERPRINT_KEY)
```

After the first `set_provider_credential` call, the fingerprint row is committed with the current primary key's fingerprint hash and the cache is invalidated. On the next call (e.g., rotating the key), if the cache has since been prewarmed by any path (including the lifespan prewarm that ran before), `get_str(_FINGERPRINT_KEY)` returns the **previously written fingerprint string** (not `None`). The guard condition `stored_fp is None` is `False`, so the inline fingerprint UPDATE is skipped entirely.

This means if an operator: (1) sets a credential under key K1 (fingerprint written = fp1), (2) changes `APP_ENCRYPTION_KEY` to K2 WITHOUT restarting the container, and (3) calls `set_provider_credential` again — the fingerprint in `app_settings` remains fp1 while the ciphertext is now encrypted under K2. The next container restart's `rewrap_if_needed` will detect the mismatch and rewrap correctly, so data is not lost. However the invariant "fingerprint reflects the key the ciphertext is encrypted under" is violated between the set and the next restart.

The deeper issue: `set_provider_credential`'s fingerprint guard is trying to do something that `rewrap_if_needed` already owns. The guard's comment says "avoid rewrap spamming rewrap_completed with zero rows," but the no-op early-return in `rewrap_if_needed` already handles that case. The guard in `set_provider_credential` is insufficiently scoped for key-rotation correctness.

**Fix:** The baseline write in `set_provider_credential` should unconditionally update the fingerprint to the current primary key (not only when `stored_fp is None`), since encrypting under the new primary key is always the correct post-write state:

```python
# Replace the conditional block with an unconditional fingerprint write:
db.execute(
    update(AppSetting)
    .where(AppSetting.key == _FINGERPRINT_KEY)
    .values(
        value=encryption.primary_key_fingerprint(),
        value_type="string",
        updated_by_user_id=by_user_id,
    )
)
settings_service.invalidate(_FINGERPRINT_KEY)
```

This is unconditionally correct: `set_provider_credential` always encrypts under the current primary key, so the fingerprint should always reflect the current primary key after a set.

---

## Warnings

### WR-01: FOR UPDATE lock held through early-return branches in `rewrap_if_needed`

**File:** `app/services/credentials.py:348-365`

**Issue:** `rewrap_if_needed` acquires a FOR UPDATE row lock on all populated `api_credentials` rows before evaluating the early-return guards:

```python
rows = (
    db.execute(
        select(ApiCredential).where(ApiCredential.key_ciphertext.is_not(None)).with_for_update()
    )
    .scalars()
    .all()
)

# Early-return guards (D-14 + RESEARCH.md Pitfall 6):
if stored_fp == new_fp:
    return  # <-- lock held; not committed or rolled back here
if stored_fp is None and not rows:
    return  # <-- lock held; not committed or rolled back here
```

When the common-case `stored_fp == new_fp` early return fires, the session exits the `with SessionLocal() as db:` block in `lifespan`, which triggers `Session.__exit__` → `rollback()` (since no `commit()` was called). The rollback releases the lock, so there is no permanent deadlock. However, the lock is held for the entire duration between the SELECT and the `with` block exit, which includes any work done after `rewrap_if_needed` returns but before the `with` block exits (currently only `prewarm_cache`, which is read-only and DB-hitting — another connection).

On a single-worker household app this is unlikely to cause visible latency, but it is a correctness smell: locks should be held for the minimum duration needed. The common early-return should not hold a lock at all.

**Fix:** Move the early-return check before the FOR UPDATE SELECT. Compute `new_fp`, read `stored_fp`, check the fingerprint match, and only acquire the lock when a rewrap is actually needed:

```python
new_fp = encryption.primary_key_fingerprint()
try:
    stored_fp = settings_service.get_str(_FINGERPRINT_KEY)
except settings_service.SettingNotFoundError:
    stored_fp = None

# Check fingerprint match BEFORE acquiring the lock
if stored_fp == new_fp:
    return  # No lock acquired; common path is entirely lockless

# Only lock rows when we actually need to rewrap
rows = (
    db.execute(
        select(ApiCredential)
        .where(ApiCredential.key_ciphertext.is_not(None))
        .with_for_update()
    )
    .scalars()
    .all()
)

if stored_fp is None and not rows:
    return  # First deploy with no credentials; no lock to release (rows is empty)
```

---

### WR-02: `monkeypatched_app_encryption_key` fixture does not restore `_multi_fernet` after test

**File:** `tests/conftest.py:422-445`

**Issue:** The `monkeypatched_app_encryption_key` fixture patches `APP_ENCRYPTION_KEY` and reloads `app.services.encryption`, but relies on `monkeypatch` teardown to restore `APP_ENCRYPTION_KEY`. However, `importlib.reload(enc_mod)` permanently replaces the module-level `_multi_fernet` singleton in `app.services.encryption` for the duration of the pytest session. After the test exits and `monkeypatch` restores the string value on `settings.APP_ENCRYPTION_KEY`, the module's `_multi_fernet` is still the test key's MultiFernet — not the original.

The fixture comment acknowledges this: "the module's `_multi_fernet` stays rebuilt with the test key, which is harmless because every Phase 3 test that touches the singleton requests this fixture." This is only safe if every test that needs a real `_multi_fernet` also requests `monkeypatched_app_encryption_key`. If a non-Phase-3 test runs after a Phase-3 test in the same session without requesting the fixture, it inherits a contaminated `_multi_fernet` built from a test key that no longer exists.

In practice the conftest-level `APP_ENCRYPTION_KEY` stub is a valid-shape Fernet key, so the contamination is a test key rather than `None`. But `test_bad_encryption_key_fails_lifespan_before_db` patches the key to `""` and reloads (line 151 of `test_lifespan_phase3.py`), which causes the reload to raise `ValueError`. After that test, `app.services.encryption._multi_fernet` may be in an inconsistent state if the reload partially executed.

**Fix:** Add explicit teardown to the fixture that reloads the module a second time (with the original key restored) after `monkeypatch` has run its teardown, or use a `finally` block:

```python
@pytest.fixture
def monkeypatched_app_encryption_key(
    monkeypatch: pytest.MonkeyPatch, fernet_key_str: str
) -> str:
    import importlib
    monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", fernet_key_str)
    import app.services.encryption as enc_mod
    importlib.reload(enc_mod)
    yield fernet_key_str
    # Restore the module state after monkeypatch has already restored
    # settings.APP_ENCRYPTION_KEY to the conftest stub value.
    importlib.reload(enc_mod)
```

---

### WR-03: `set_setting` does not validate the incoming value type against `value_type`

**File:** `app/services/settings.py:199-272`

**Issue:** `set_setting` reads the row's `value_type` from the DB, then serializes the incoming `value: Any` to text with a type-specific coercion (lines 237-244). However, it never checks that the incoming Python type is actually appropriate for `value_type`. A caller can pass `value="not-a-number"` to a row with `value_type="int"`, and the function will call `str("not-a-number")` = `"not-a-number"` and commit that string to an `int` row. The next `get_int()` call on that key will raise `ValueError` from `int("not-a-number")` inside `_coerce()`, which is not caught and will surface as an unhandled server error.

The docstring says the function coerces to text "according to the row's existing `value_type`," but the coercion only converts Python native types to text — it does not validate that the Python type is coherent with `value_type`. The `json` branch (`json.dumps(value)`) will raise `TypeError` on non-serializable values, so that case self-defends. The `bool` branch serializes any truthy Python value, which is fine. The `int` and `float` branches (`str(value)`) accept any value that has a `__str__`, including strings that are not numeric.

This is not exploitable from outside (it requires an authenticated admin action in Phase 9), but it creates a subtle foot-gun at the service layer.

**Fix:** Add a type coherence check before serialization:

```python
# After reading value_type from the existing row:
if value is not None:
    if value_type == "int" and not isinstance(value, int):
        raise SettingTypeError(
            f"Setting {key!r} expects int value; got {type(value).__name__}"
        )
    if value_type == "float" and not isinstance(value, (int, float)):
        raise SettingTypeError(
            f"Setting {key!r} expects float value; got {type(value).__name__}"
        )
    if value_type == "bool" and not isinstance(value, bool):
        raise SettingTypeError(
            f"Setting {key!r} expects bool value; got {type(value).__name__}"
        )
    if value_type == "string" and not isinstance(value, str):
        raise SettingTypeError(
            f"Setting {key!r} expects str value; got {type(value).__name__}"
        )
```

---

## Info

### IN-01: `_coerce` silently returns `None` for `value=None` with non-null `value_type`

**File:** `app/services/settings.py:90-95`

**Issue:** The defensive fallback in `_coerce` for `value=None` with a non-`null` `value_type` silently returns `None`:

```python
if value is None:
    # Defensive: value=None with a non-'null' value_type is an
    # invalid row, but we surface it as Python None rather than crash
    return None
```

This means a corrupted row (e.g., `value_type='int'` with `value=NULL`) is silently treated as a `null` sentinel. The caller using `get_int(key)` will receive `None` with no indication that the row is malformed. The comment acknowledges this is invalid but accepts the silent path. A structured log warning here would help diagnose the data integrity issue without crashing:

**Fix:**
```python
if value is None:
    log.warning(
        "settings.invalid_null_value",
        key="<unknown>",  # key not available here; log at call site
        value_type=value_type,
    )
    return None
```

Or surface the warning at the `prewarm_cache` call site where the key is available.

---

### IN-02: `test_migrations.py` does not verify `api_credentials` table after Phase 3 migration

**File:** `tests/test_migrations.py:77-89`

**Issue:** `test_five_tables_exist` was written for Phase 0 and checks exactly `{'users', 'bags', 'wishlist_entries', 'ai_recommendations', 'app_settings'}`. The Phase 3 migration adds a sixth table (`api_credentials`). While `test_api_credentials_table_exists` (line 276) tests the new table separately, `test_five_tables_exist` is now misnamed and does not test all tables. Its name and fixed expected set will silently exclude `api_credentials` from the "all tables present" assertion forever, which is a maintenance trap.

**Fix:** Rename the test to `test_core_tables_exist` and update the expected set to include `api_credentials`, or update the docstring to document that it only covers the Phase 0 table set.

---

### IN-03: `test_emits_admin_app_setting_changed_event` fires a second `set_setting` in `finally` outside `capture_logs`, leaking potential duplicate event noise into other structlog captures

**File:** `tests/services/test_settings.py:183-190`

**Issue:** The `with structlog.testing.capture_logs() as captured:` block covers only the primary `set_setting` call. The `finally` block's restore call to `set_setting` runs outside the capture context. This is correct for the assertion (only the intended call is captured), but if any structlog output from the restore call bleeds into a surrounding capture context (e.g., a test running this as a sub-step), it would add a second `admin.app_setting_changed` event to the outer capture. This is a minor test isolation issue rather than a production bug, but it could make debugging test failures confusing.

**Fix:** Wrap the restore call in `structlog.testing.capture_logs()` and discard the result, or use `settings_service.invalidate` + a direct DB UPDATE if the test's goal is just cleanup:

```python
finally:
    with structlog.testing.capture_logs():  # discard restore-emit noise
        settings_service.set_setting(
            db,
            "ai_primary_max_searches",
            original if original is not None else 5,
            by_user_id=None,
        )
```

---

_Reviewed: 2026-05-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
