"""Phase 3 tests for ``app.services.credentials`` (Validation Map rows 13-22 + 27).

Covers the per-task verification map rows from
``.planning/phases/03-encryption-settings/03-VALIDATION.md``:

- Row 13 — set writes ciphertext + last_four
  → ``test_set_provider_credential_writes_ciphertext_and_last_four``
- Row 14 — get returns frozen+slots dataclass         → ``test_get_returns_frozen_dataclass``
- Row 15 — disabled-or-empty -> None                  → ``test_disabled_or_empty_returns_none``
- Row 16 — disabled-with-ciphertext -> None
  → ``test_disabled_with_ciphertext_returns_none``
- Row 17 — orphan ciphertext -> None + emits event
  → ``test_orphan_ciphertext_returns_none_and_emits``
- Row 18 — rotation overwrites in place               → ``test_rotation_overwrites_in_place``
- Row 19 — set emits event without key                → ``test_set_emits_event_without_key``
- Row 20 — rewrap no-op with no credentials           → ``test_rewrap_no_credentials_noop``
- Row 21 — rewrap idempotent when fingerprint matches
  → ``test_rewrap_idempotent_when_fingerprint_matches``
- Row 22 — rewrap rotates ciphertext + writes fp
  → ``test_rewrap_rotates_ciphertexts_and_writes_fingerprint``
- Row 27 — runtime placeholder for SEC-6 invariant    → ``test_no_pydantic_carries_decrypted_key``

DB cleanup: every test that mutates DB state wraps its body in
try/finally and resets BOTH api_credentials rows AND the fingerprint
row to their seeded shape. The single-worker invariant means there is
no test isolation in the DB beyond what these explicit cleanups
provide.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest
from sqlalchemy import text


def _require_credentials_service() -> None:
    """Skip cleanly until Plan 03-04 lands ``app.services.credentials``."""
    try:
        from app.services.credentials import (  # noqa: F401
            ProviderCredential,
            get_provider_credential,
            rewrap_if_needed,
            set_provider_credential,
            set_provider_enabled,
        )
    except ImportError:
        pytest.skip("Phase 3 dependency: app.services.credentials")


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — service test needs the DB")


def _reset_credentials_state(db) -> None:
    """Reset both api_credentials rows + the fingerprint row to seeded shape.

    Called from every test's finally block. Resets the api_credentials
    rows to the migration's seeded shape (provider, is_enabled=False,
    everything else NULL) and the fingerprint row back to value=NULL,
    value_type='null'.
    """
    db.execute(
        text(
            "UPDATE api_credentials SET key_ciphertext=NULL, last_four=NULL, "
            "model_name=NULL, is_enabled=false, updated_by_user_id=NULL"
        )
    )
    db.execute(
        text(
            "UPDATE app_settings SET value=NULL, value_type='null', "
            "updated_by_user_id=NULL WHERE key='encryption_key_primary_fingerprint'"
        )
    )
    db.commit()
    # The settings cache may hold a stale entry for the fingerprint row.
    # Force a fresh re-prewarm so the next test sees the typed-null
    # sentinel rather than a stale 'string' coercion.
    try:
        from app.services import settings as settings_service

        settings_service.invalidate("encryption_key_primary_fingerprint")
    except ImportError:
        pass


def test_set_provider_credential_writes_ciphertext_and_last_four(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 13 (SEC-08, D-01 + D-03): set writes ciphertext + last_four + is_enabled."""
    _require_credentials_service()
    _require_postgres()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.api_credential import ApiCredential
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        # Prewarm the settings cache so credentials' set_provider_credential
        # can read the fingerprint row via get_str.
        settings_service.prewarm_cache(db)
        try:
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-ant-test-1234",
                model_name="claude-opus-4-7",
                by_user_id=None,
            )
            # Read the row back directly (bypass the service to inspect
            # the persisted shape).
            row = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            assert row.key_ciphertext is not None, "key_ciphertext must be encrypted bytes"
            assert isinstance(row.key_ciphertext, bytes), (
                f"key_ciphertext must be bytes; got {type(row.key_ciphertext).__name__}"
            )
            assert row.last_four == "1234", (
                f"last_four must be the last 4 chars; got {row.last_four!r}"
            )
            assert row.model_name == "claude-opus-4-7"
            assert row.is_enabled is True, "set must flip is_enabled to True (D-01)"
        finally:
            _reset_credentials_state(db)


def test_get_returns_frozen_dataclass(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 14 (D-09 + D-11): get returns ProviderCredential frozen+slots dataclass."""
    _require_credentials_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service
    from app.services.credentials import ProviderCredential

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-ant-test-1234",
                model_name="claude-opus-4-7",
                by_user_id=None,
            )
            cred = credentials_service.get_provider_credential(db, "anthropic")
            assert cred is not None
            assert isinstance(cred, ProviderCredential)
            assert cred.provider == "anthropic"
            assert cred.key == "sk-ant-test-1234"
            assert cred.last_four == "1234"
            assert cred.model_name == "claude-opus-4-7"

            # frozen+slots: mutation must raise FrozenInstanceError.
            with pytest.raises(dataclasses.FrozenInstanceError):
                cred.key = "mutated"  # type: ignore[misc]

            # slots: __dict__ must not exist on the instance.
            assert not hasattr(cred, "__dict__"), (
                "ProviderCredential must use __slots__ (no __dict__) — D-09"
            )
        finally:
            _reset_credentials_state(db)


def test_disabled_or_empty_returns_none(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 15 (D-04 + D-10): freshly-seeded row (is_enabled=false, ciphertext=NULL) -> None."""
    _require_credentials_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        # Ensure clean seeded state first.
        _reset_credentials_state(db)
        try:
            # Seeded shape: is_enabled=False, key_ciphertext=NULL.
            assert credentials_service.get_provider_credential(db, "openai") is None
            assert credentials_service.get_provider_credential(db, "anthropic") is None
        finally:
            _reset_credentials_state(db)


def test_disabled_with_ciphertext_returns_none(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 16 (D-10): disabled row with populated ciphertext still returns None."""
    _require_credentials_service()
    _require_postgres()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.api_credential import ApiCredential
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-ant-test-1234",
                model_name="m",
                by_user_id=None,
            )
            credentials_service.set_provider_enabled(db, "anthropic", False, by_user_id=None)
            row = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            assert row.key_ciphertext is not None, "ciphertext must survive a disable toggle"
            assert row.is_enabled is False
            assert credentials_service.get_provider_credential(db, "anthropic") is None
        finally:
            _reset_credentials_state(db)


def test_orphan_ciphertext_returns_none_and_emits(
    monkeypatch: pytest.MonkeyPatch, fernet_key_str: str
) -> None:
    """Row 17 (SEC-08/SEC-09, D-15): orphaned ciphertext -> None + emits decrypt_failed event."""
    _require_credentials_service()
    _require_postgres()
    import importlib

    import structlog
    from cryptography.fernet import Fernet

    k1 = fernet_key_str
    k2 = Fernet.generate_key().decode("ascii")

    # Stage 1: only k1 — write a credential encrypted under it.
    monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", k1)
    import app.services.encryption as enc_mod

    importlib.reload(enc_mod)
    from app.db import SessionLocal
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-ant-orphan-9999",
                model_name="m",
                by_user_id=None,
            )

            # Stage 2: only k2 — k1 is GONE; the stored ciphertext is now
            # un-decryptable.
            monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", k2)
            importlib.reload(enc_mod)

            with structlog.testing.capture_logs() as captured:
                result = credentials_service.get_provider_credential(db, "anthropic")

            assert result is None, "orphan ciphertext (no key decrypts) must return None per D-15"
            decrypt_failed = [e for e in captured if e.get("event") == "encryption.decrypt_failed"]
            assert len(decrypt_failed) == 1, (
                f"expected exactly one encryption.decrypt_failed; got {len(decrypt_failed)}"
            )
            evt = decrypt_failed[0]
            assert evt.get("provider") == "anthropic"
            assert evt.get("error_class") == "InvalidToken", (
                f"error_class must be the class name; got {evt.get('error_class')!r}"
            )
        finally:
            _reset_credentials_state(db)
            # Restore encryption module to a known-good key for downstream tests.
            monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", k1)
            importlib.reload(enc_mod)


def test_rotation_overwrites_in_place(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 18 (D-01): rotating overwrites all four fields atomically; only one row exists."""
    _require_credentials_service()
    _require_postgres()
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models.api_credential import ApiCredential
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-test-1111",
                model_name="opus-4-7",
                by_user_id=None,
            )
            row_a = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            ct_a = row_a.key_ciphertext
            assert row_a.last_four == "1111"
            assert row_a.model_name == "opus-4-7"

            # Rotate to a new key.
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-test-2222",
                model_name="opus-4-8",
                by_user_id=None,
            )
            db.expire_all()  # force re-read from DB
            row_b = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()

            assert row_b.last_four == "2222"
            assert row_b.model_name == "opus-4-8"
            assert row_b.key_ciphertext != ct_a, "ciphertext must change on rotate"

            # Single row — UPDATE not INSERT (D-01).
            count = db.execute(
                select(func.count())
                .select_from(ApiCredential)
                .where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            assert count == 1, f"rotation must UPDATE; got {count} anthropic rows"
        finally:
            _reset_credentials_state(db)


def test_set_emits_event_without_key(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 19 (D-08, SEC-6): set emits admin.api_credential_set with NO key/ciphertext."""
    _require_credentials_service()
    _require_postgres()
    import structlog

    from app.db import SessionLocal
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        # Seed a user so updated_by_user_id satisfies the FK.
        # Inline SQL keeps the test sync — async fixtures don't compose here.
        suffix = uuid.uuid4().hex[:8]
        actor_id = db.execute(
            text(
                "INSERT INTO users (username, email, password_hash, is_admin, is_active) "
                "VALUES (:u, :e, :p, true, true) RETURNING id"
            ),
            {
                "u": f"admin-{suffix}",
                "e": f"admin-{suffix}@example.com",
                "p": "$argon2id$v=19$m=65536,t=3,p=4$test$test",
            },
        ).scalar_one()
        db.commit()
        try:
            with structlog.testing.capture_logs() as captured:
                credentials_service.set_provider_credential(
                    db,
                    "anthropic",
                    key="sk-secret-XXXX",
                    model_name="m",
                    by_user_id=actor_id,
                )

            set_events = [e for e in captured if e.get("event") == "admin.api_credential_set"]
            assert len(set_events) == 1, (
                f"expected exactly one admin.api_credential_set; "
                f"got {len(set_events)} (events: {[e.get('event') for e in captured]})"
            )
            evt = set_events[0]
            assert evt.get("provider") == "anthropic"
            assert evt.get("last_four") == "XXXX"
            assert evt.get("model_name") == "m"
            assert evt.get("user_id") == actor_id

            # Hard SEC-6 check: NO field carries the key or ciphertext.
            assert "key" not in evt, (
                f"event must not include 'key' field; got keys: {list(evt.keys())}"
            )
            assert "ciphertext" not in evt, (
                f"event must not include 'ciphertext' field; got keys: {list(evt.keys())}"
            )
            # The raw secret string must not appear ANYWHERE in the event repr.
            assert "sk-secret" not in str(evt), (
                f"raw key fragment must not appear in event: {evt!r}"
            )
        finally:
            _reset_credentials_state(db)
            db.execute(text("DELETE FROM users WHERE id = :id"), {"id": actor_id})
            db.commit()


def test_rewrap_no_credentials_noop(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 20 (D-14): first-deploy / empty-credentials rewrap is a no-op.

    Pre-condition: both api_credentials rows have ciphertext=NULL, and
    the fingerprint row is the typed-null sentinel. rewrap_if_needed
    must NOT write the fingerprint AND must NOT emit
    encryption.rewrap_completed (Pitfall 6 protection).
    """
    _require_credentials_service()
    _require_postgres()
    import structlog
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.app_setting import AppSetting
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        # Ensure a clean, seeded baseline.
        _reset_credentials_state(db)
        settings_service.prewarm_cache(db)
        try:
            fp_before = db.execute(
                select(AppSetting.value, AppSetting.value_type).where(
                    AppSetting.key == "encryption_key_primary_fingerprint"
                )
            ).one()
            assert fp_before.value is None, "fingerprint row must start NULL"
            assert fp_before.value_type == "null", (
                "fingerprint value_type must start as the typed-null sentinel"
            )

            with structlog.testing.capture_logs() as captured:
                credentials_service.rewrap_if_needed(db)

            fp_after = db.execute(
                select(AppSetting.value, AppSetting.value_type).where(
                    AppSetting.key == "encryption_key_primary_fingerprint"
                )
            ).one()
            assert fp_after.value is None, "no-op rewrap must NOT write the fingerprint"
            assert fp_after.value_type == "null"

            rewrap_events = [e for e in captured if e.get("event") == "encryption.rewrap_completed"]
            assert len(rewrap_events) == 0, (
                f"no-op rewrap must NOT emit rewrap_completed; got {len(rewrap_events)}"
            )
        finally:
            _reset_credentials_state(db)


def test_rewrap_idempotent_when_fingerprint_matches(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 21 (D-14): rewrap when fingerprint already matches -> byte-identical ciphertext."""
    _require_credentials_service()
    _require_postgres()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.api_credential import ApiCredential
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-ant-test-1234",
                model_name="m",
                by_user_id=None,
            )
            row_before = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            ct_before = bytes(row_before.key_ciphertext)

            # Re-warm so rewrap_if_needed sees the just-written fingerprint
            # (set_provider_credential wrote it inline + invalidated the cache).
            settings_service.prewarm_cache(db)

            credentials_service.rewrap_if_needed(db)

            db.expire_all()
            row_after = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            ct_after = bytes(row_after.key_ciphertext)

            assert ct_after == ct_before, (
                "idempotent rewrap (fingerprint matches) must NOT re-encrypt"
            )
        finally:
            _reset_credentials_state(db)


def test_rewrap_rotates_ciphertexts_and_writes_fingerprint(
    monkeypatch: pytest.MonkeyPatch, fernet_key_str: str
) -> None:
    """Row 22 (D-14): key rotation -> re-encrypt, new fingerprint, emit rewrap_completed."""
    _require_credentials_service()
    _require_postgres()
    import importlib

    import structlog
    from cryptography.fernet import Fernet
    from sqlalchemy import select

    k1 = fernet_key_str
    k2 = Fernet.generate_key().decode("ascii")

    # Stage 1: only k1 — set a credential.
    monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", k1)
    import app.services.encryption as enc_mod

    importlib.reload(enc_mod)

    from app.db import SessionLocal
    from app.models.api_credential import ApiCredential
    from app.models.app_setting import AppSetting
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-rotate-test",
                model_name="m",
                by_user_id=None,
            )
            row_before = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            ct_before = bytes(row_before.key_ciphertext)
            fp_before = db.execute(
                select(AppSetting.value).where(
                    AppSetting.key == "encryption_key_primary_fingerprint"
                )
            ).scalar_one()

            # Stage 2: k2 is primary, k1 is secondary. Rewrap should
            # decrypt under k1 (still present), re-encrypt under k2 (new
            # primary), and write the new fingerprint.
            monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", f"{k2},{k1}")
            importlib.reload(enc_mod)
            # Force the settings cache to forget the pre-rotation
            # fingerprint so rewrap_if_needed sees stale_fp != new_fp.
            settings_service.invalidate("encryption_key_primary_fingerprint")
            settings_service.prewarm_cache(db)

            with structlog.testing.capture_logs() as captured:
                credentials_service.rewrap_if_needed(db)

            db.expire_all()
            row_after = db.execute(
                select(ApiCredential).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            ct_after = bytes(row_after.key_ciphertext)
            fp_after = db.execute(
                select(AppSetting.value).where(
                    AppSetting.key == "encryption_key_primary_fingerprint"
                )
            ).scalar_one()

            assert ct_after != ct_before, "rewrap must re-encrypt under new primary"
            assert fp_after != fp_before, "rewrap must write a new fingerprint"

            # Decryption still works under (k2, k1) — the decrypted key
            # round-trips identically.
            cred = credentials_service.get_provider_credential(db, "anthropic")
            assert cred is not None
            assert cred.key == "sk-rotate-test"

            rewrap_events = [e for e in captured if e.get("event") == "encryption.rewrap_completed"]
            assert len(rewrap_events) == 1, (
                f"expected one encryption.rewrap_completed; got {len(rewrap_events)}"
            )
            assert rewrap_events[0].get("row_count") == 1, (
                f"row_count must reflect the rewrapped rows; got "
                f"{rewrap_events[0].get('row_count')}"
            )
        finally:
            _reset_credentials_state(db)
            # Restore the encryption module under a known-good key.
            monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", k1)
            importlib.reload(enc_mod)


def test_updated_at_advances_on_set_and_toggle(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Regression for CR-01: every write path advances ``updated_at``.

    ``ApiCredential.updated_at`` is written via Core ``update()`` statements,
    which bypass ORM ``onupdate=func.now()`` hooks. Each Core update site
    must include ``updated_at=func.now()`` explicitly. This test exercises
    ``set_provider_credential``, ``set_provider_enabled``, and the rewrap
    path's ORM-style mutation.
    """
    _require_credentials_service()
    _require_postgres()
    import time

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.api_credential import ApiCredential
    from app.services import credentials as credentials_service
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            seeded = db.execute(
                select(ApiCredential.updated_at).where(ApiCredential.provider == "anthropic")
            ).scalar_one()

            credentials_service.set_provider_credential(
                db,
                "anthropic",
                key="sk-test-aaaa",
                model_name="m",
                by_user_id=None,
            )
            db.expire_all()
            after_set = db.execute(
                select(ApiCredential.updated_at).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            assert after_set > seeded, (
                f"updated_at must advance on set; seeded={seeded}, after_set={after_set}"
            )

            time.sleep(0.01)  # ensure now() advances at sub-second resolution
            credentials_service.set_provider_enabled(db, "anthropic", False, by_user_id=None)
            db.expire_all()
            after_toggle = db.execute(
                select(ApiCredential.updated_at).where(ApiCredential.provider == "anthropic")
            ).scalar_one()
            assert after_toggle > after_set, (
                f"updated_at must advance on toggle; "
                f"after_set={after_set}, after_toggle={after_toggle}"
            )
        finally:
            _reset_credentials_state(db)


def test_fingerprint_baseline_rewritten_on_every_set(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Regression for CR-02: fingerprint baseline is unconditionally rewritten on set.

    A conditional ``if stored_fp is None`` guard left the fingerprint
    stale after a mid-session APP_ENCRYPTION_KEY rotation. The invariant
    "fingerprint == key the ciphertext is encrypted under" must hold
    after every ``set_provider_credential`` call, not just the first.
    """
    _require_credentials_service()
    _require_postgres()
    import importlib

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.app_setting import AppSetting
    from app.services import credentials as credentials_service
    from app.services import encryption as enc_mod
    from app.services import settings as settings_service

    def _read_fp_from_db(session) -> str | None:
        session.expire_all()
        return session.execute(
            select(AppSetting.value).where(AppSetting.key == "encryption_key_primary_fingerprint")
        ).scalar_one()

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        try:
            # First set establishes the baseline under key1.
            credentials_service.set_provider_credential(
                db, "anthropic", key="sk-aaaa1234", model_name="m", by_user_id=None
            )
            fp_after_first = _read_fp_from_db(db)
            assert fp_after_first is not None, "first set must write fingerprint"

            # Simulate mid-session key rotation: swap primary key, reload
            # encryption module so primary_key_fingerprint returns the
            # new value.
            new_key = "v2EKHcGqDpyu1MEqLkUaCSEHM8nP7p9C28xX-PoMUjQ="
            from app.config import settings as cfg

            original_key = cfg.APP_ENCRYPTION_KEY
            cfg.APP_ENCRYPTION_KEY = new_key
            try:
                importlib.reload(enc_mod)
                expected_fp = enc_mod.primary_key_fingerprint()
                assert expected_fp != fp_after_first, (
                    "test sanity check: rotated key must yield a different fingerprint"
                )

                # Second set under the rotated key MUST rewrite the fingerprint.
                credentials_service.set_provider_credential(
                    db, "openai", key="sk-bbbb5678", model_name="gpt", by_user_id=None
                )
                fp_after_second = _read_fp_from_db(db)
                assert fp_after_second == expected_fp, (
                    f"fingerprint must reflect the current primary after every set; "
                    f"expected {expected_fp}, got {fp_after_second}"
                )
            finally:
                cfg.APP_ENCRYPTION_KEY = original_key
                importlib.reload(enc_mod)
        finally:
            _reset_credentials_state(db)


def test_no_pydantic_carries_decrypted_key() -> None:
    """Row 27 (SEC-6 runtime placeholder): ProviderCredential is NOT a Pydantic model.

    The formal CI grep test for ``model_dump\\(\\)`` near ``ApiCredential``
    is deferred to Phase 12 per ROADMAP §"Phase 3: Notes". This test is
    the runtime-side placeholder: a dataclass has neither ``model_dump``
    nor ``model_validate``, so a regression that converts ProviderCredential
    to a Pydantic model would trip this assertion.
    """
    _require_credentials_service()
    from app.services.credentials import ProviderCredential

    assert not hasattr(ProviderCredential, "model_dump"), (
        "ProviderCredential must NOT be a Pydantic model (SEC-6); "
        "model_dump() would leak the decrypted key"
    )
    assert not hasattr(ProviderCredential, "model_validate"), (
        "ProviderCredential must NOT be a Pydantic model (SEC-6)"
    )
    assert dataclasses.is_dataclass(ProviderCredential), (
        "ProviderCredential must be a @dataclass(frozen=True, slots=True)"
    )
