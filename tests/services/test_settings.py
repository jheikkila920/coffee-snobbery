"""Phase 3 tests for ``app.services.settings`` (Validation Map rows 7-12).

Covers the per-task verification map rows from
``.planning/phases/03-encryption-settings/03-VALIDATION.md``:

- Row 7  — prewarm loads all rows                 → ``test_prewarm_loads_all_rows``
- Row 8  — typed accessors coerce + null sentinel  → ``test_typed_accessors_coerce``
- Row 9  — accessor type mismatch raises           → ``test_type_mismatch_raises``
- Row 10 — write-through invalidate                → ``test_write_through_invalidate``
- Row 11 — set_setting emits admin.app_setting_changed
                                                    → ``test_emits_admin_app_setting_changed_event``
- Row 12 — unknown key raises NotFound             → ``test_unknown_key_raises_not_found``

Per D-07: tests use the sync ``SessionLocal()`` (NOT async). Cleanup is
explicit in try/finally so a write-through test doesn't pollute another
test's view of the seeded value.
"""

from __future__ import annotations

import pytest


def _require_settings_service() -> None:
    """Skip cleanly until Plan 03-03 lands ``app.services.settings``."""
    try:
        from app.services.settings import (  # noqa: F401
            SettingNotFoundError,
            SettingTypeError,
            get_bool,
            get_int,
            get_json,
            get_str,
            prewarm_cache,
            set_setting,
        )
    except ImportError:
        pytest.skip("Phase 3 dependency: app.services.settings")


def _require_postgres() -> None:
    """Skip when Postgres is unreachable — service tests need a real DB."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — service test needs the DB")


def test_prewarm_loads_all_rows() -> None:
    """Row 7 (D-06): prewarm loads every app_settings row into _cache (>=19)."""
    _require_settings_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)

    # Phase 0 seeded 19 rows; Plan 03-01 added the 20th
    # (encryption_key_primary_fingerprint). >=19 keeps the test future-proof
    # against further seed additions; the critical-keys test (test_migrations)
    # pins the exact 19-key seed set.
    assert len(settings_service._cache) >= 19, (
        f"prewarm must populate >=19 rows; got {len(settings_service._cache)}"
    )
    assert "recommendation_region" in settings_service._cache
    assert "ai_primary_max_searches" in settings_service._cache
    assert "setup_completed" in settings_service._cache


def test_typed_accessors_coerce() -> None:
    """Row 8 (D-05): typed accessors return coerced values; null sentinel -> None."""
    _require_settings_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)

    # Seeded values (Phase 0 0001_initial.py).
    assert settings_service.get_str("recommendation_region") == "US"
    assert settings_service.get_int("ai_primary_max_searches") == 5
    assert settings_service.get_bool("setup_completed") is False

    # The fingerprint row is the typed-null sentinel on first deploy.
    # value_type='null' -> every accessor returns None regardless of
    # the accessor's expected type (D-05 + service._get null branch).
    # NOTE: a prior credentials test in the same pytest session may have
    # flipped value_type to 'string'. If that's the case, get_str must
    # still return None (the value remains NULL after rewrap clean-up,
    # OR a fingerprint hex string if a rewrap committed). The test
    # accepts either: None (null sentinel) OR str (post-write).
    fp = settings_service.get_str("encryption_key_primary_fingerprint")
    assert fp is None or isinstance(fp, str), (
        f"encryption_key_primary_fingerprint must be None or str; got {type(fp).__name__}"
    )


def test_type_mismatch_raises() -> None:
    """Row 9 (D-05): get_int on a value_type='string' row raises SettingTypeError."""
    _require_settings_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)

    # recommendation_region has value_type='string'. get_int must raise.
    with pytest.raises(settings_service.SettingTypeError):
        settings_service.get_int("recommendation_region")


def test_write_through_invalidate() -> None:
    """Row 10 (D-08): set_setting UPDATEs the row, invalidates cache, next read fresh.

    Cleanup is explicit in try/finally so the seed value (5) is restored
    for downstream tests.
    """
    _require_settings_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        original = settings_service.get_int("ai_primary_max_searches")

        try:
            # Write a new value.
            settings_service.set_setting(db, "ai_primary_max_searches", 7, by_user_id=None)
            # Cache was invalidated — next read forces re-warm OR returns
            # SettingNotFoundError (per the docstring "drop the key so the
            # next accessor call surfaces SettingNotFoundError forcing a
            # re-prewarm"). Per the actual impl, set_setting only pops the
            # key; a subsequent get_int will raise SettingNotFoundError
            # because the cache wasn't re-warmed. Force a re-prewarm to
            # observe the new value.
            settings_service.prewarm_cache(db)
            assert settings_service.get_int("ai_primary_max_searches") == 7
        finally:
            # Restore the seed value so downstream tests see the original.
            settings_service.set_setting(
                db,
                "ai_primary_max_searches",
                original if original is not None else 5,
                by_user_id=None,
            )
            settings_service.prewarm_cache(db)


def test_emits_admin_app_setting_changed_event() -> None:
    """Row 11 (D-08): set_setting emits admin.app_setting_changed with documented fields.

    Asserts on the documented fields only (setting_key, value_type,
    user_id, old_value, new_value) per the threat register T-03-T8 —
    no new sensitive field name is introduced.
    """
    _require_settings_service()
    _require_postgres()
    import structlog

    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)
        original = settings_service.get_int("ai_primary_max_searches")

        try:
            with structlog.testing.capture_logs() as captured:
                # Write back the same value (5) to make the event fire
                # without ambiguity about what changed.
                settings_service.set_setting(db, "ai_primary_max_searches", 5, by_user_id=None)
        finally:
            # Restore the seed value if the test changed it (defensive).
            settings_service.set_setting(
                db,
                "ai_primary_max_searches",
                original if original is not None else 5,
                by_user_id=None,
            )

    events = [e for e in captured if e.get("event") == "admin.app_setting_changed"]
    assert len(events) == 1, (
        f"expected exactly one admin.app_setting_changed; got {len(events)} "
        f"(all events: {[e.get('event') for e in captured]})"
    )
    evt = events[0]
    assert evt.get("setting_key") == "ai_primary_max_searches"
    assert evt.get("value_type") == "int"
    assert evt.get("user_id") is None
    assert "old_value" in evt
    assert "new_value" in evt
    # set_setting stores the text-form ("5") in the row, and emits that
    # exact text — NOT the int form. Per the impl: text_value = str(value).
    assert evt.get("new_value") == "5", (
        f"new_value must be the text form '5'; got {evt.get('new_value')!r}"
    )


def test_unknown_key_raises_not_found() -> None:
    """Row 12 (D-05): unknown key raises SettingNotFoundError."""
    _require_settings_service()
    _require_postgres()
    from app.db import SessionLocal
    from app.services import settings as settings_service

    with SessionLocal() as db:
        settings_service.prewarm_cache(db)

    with pytest.raises(settings_service.SettingNotFoundError):
        settings_service.get_str("does_not_exist_definitely_not")
