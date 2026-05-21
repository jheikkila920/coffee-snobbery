"""Phase 9 — Admin settings editor tests (ADMIN-03 / D-04 / D-05 / D-06).

Covers:
- test_settings_list: GET /admin/settings returns 200 for admin; body contains
  each seeded app_settings key; editable rows render type-appropriate inputs;
  read-only rows render without editable inputs or save controls.
- test_setting_save: POST /admin/settings/min_sessions_for_ai persists the new
  value AND invalidates the cache (subsequent get_int reads the updated value).
- test_readonly_rows_rejected: POST to setup_completed and last_backup_status
  each return 403 with no mutation.

Security invariants:
- A non-admin POST to /admin/settings/{key} returns 403.
- Read-only keys are never mutated even if accessed directly.

CSRF: follows the established Phase 4/5/9 pattern — prime via GET, set cookies
+ header on the client instance before any POST.
"""

from __future__ import annotations

from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prime_csrf(client: Any, signed_cookie: str) -> str:
    """Wire session_id + csrftoken onto the client; return the CSRF token.

    Mirrors the _prime_csrf pattern from test_admin_users.py.
    """
    client.cookies.set("session_id", signed_cookie)
    client.cookies.delete("csrftoken")
    resp = client.get("/admin/settings")
    token = resp.cookies.get("csrftoken") or client.cookies.get("csrftoken", "")
    if token:
        client.cookies.set("csrftoken", token)
        client.headers["X-CSRF-Token"] = token
    return token


def _get_setting_from_db(key: str) -> Any:
    """Read a setting directly from DB (bypasses cache) for post-save verification."""
    import asyncio

    from sqlalchemy import select

    from app.main import async_session_factory
    from app.models.app_setting import AppSetting

    async def _do() -> Any:
        async with async_session_factory() as db:
            row = await db.execute(
                select(AppSetting.value).where(AppSetting.key == key)
            )
            return row.scalar_one_or_none()

    return asyncio.run(_do())


# ---------------------------------------------------------------------------
# Task 1 tests — settings list page
# ---------------------------------------------------------------------------


class TestSettingsList:
    """ADMIN-03: GET /admin/settings renders all settings rows."""

    def test_settings_list_admin_200(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Admin GET /admin/settings returns 200."""
        resp = client.get("/admin/settings", cookies=admin_session)
        assert resp.status_code == 200, (
            f"Expected 200 for admin on /admin/settings, got {resp.status_code}"
        )

    def test_settings_list_non_admin_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """Non-admin GET /admin/settings returns 403."""
        resp = client.get("/admin/settings", cookies=regular_session)
        assert resp.status_code == 403

    def test_settings_list_contains_known_keys(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Response body contains known app_settings keys."""
        resp = client.get("/admin/settings", cookies=admin_session)
        assert resp.status_code == 200
        body = resp.text
        # A sample of seeded keys that must appear in the rendered page
        for key in [
            "min_sessions_for_ai",
            "recommendation_region",
            "setup_completed",
            "last_backup_status",
        ]:
            assert key in body, f"Expected key {key!r} in settings list body"

    def test_editable_int_row_renders_number_input(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """An int-typed editable row (e.g. min_sessions_for_ai) renders a number input."""
        resp = client.get("/admin/settings", cookies=admin_session)
        assert resp.status_code == 200
        body = resp.text
        # The number input must be present alongside the key
        assert 'type="number"' in body, (
            "Expected a number input for int/float settings rows"
        )

    def test_readonly_row_has_no_save_control(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Read-only rows (setup_completed, last_backup_status) render without a save button.

        The test checks that the row containing 'setup_completed' does NOT have
        an hx-post attribute pointing to that key.
        """
        resp = client.get("/admin/settings", cookies=admin_session)
        assert resp.status_code == 200
        body = resp.text
        # No inline save form for read-only keys
        assert "hx-post=\"/admin/settings/setup_completed\"" not in body, (
            "setup_completed should be read-only — no save form expected"
        )
        assert "hx-post=\"/admin/settings/last_backup_status\"" not in body, (
            "last_backup_status should be read-only — no save form expected"
        )

    def test_readonly_row_shows_system_managed_note(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Read-only rows display a 'system-managed' note."""
        resp = client.get("/admin/settings", cookies=admin_session)
        assert resp.status_code == 200
        assert "system-managed" in resp.text


# ---------------------------------------------------------------------------
# Task 2 tests — per-row inline save handler + read-only guard
# ---------------------------------------------------------------------------


class TestSettingSave:
    """ADMIN-03 / D-06: POST /admin/settings/{key} persists value and invalidates cache."""

    def test_setting_save_persists(
        self,
        client: Any,
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """POST to an editable setting persists the new value in the DB."""
        signed_cookie = seeded_admin_user["signed_cookie"]
        token = _prime_csrf(client, signed_cookie)

        # Save a new value for min_sessions_for_ai (int type)
        resp = client.post(
            "/admin/settings/min_sessions_for_ai",
            data={"value": "7", "X-CSRF-Token": token},
            cookies={"session_id": signed_cookie, "csrftoken": token},
        )
        assert resp.status_code == 200, (
            f"Expected 200 on save, got {resp.status_code}: {resp.text[:200]}"
        )

        # Verify DB persistence directly (bypasses cache)
        db_value = _get_setting_from_db("min_sessions_for_ai")
        assert db_value == "7", (
            f"Expected DB value '7' for min_sessions_for_ai, got {db_value!r}"
        )

    def test_setting_save_cache_invalidated(
        self,
        client: Any,
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """After saving, cache is invalidated so the next typed read returns the new value.

        set_setting pops the cache key. After that, get_int would raise
        SettingNotFoundError until the next prewarm — so we re-prewarm from
        DB to prove the new value is persisted and can be re-loaded.
        """
        from sqlalchemy.orm import Session

        from app.models.app_setting import AppSetting
        from app.models.base import Base
        from app.services.settings import get_int, invalidate, prewarm_cache

        signed_cookie = seeded_admin_user["signed_cookie"]
        token = _prime_csrf(client, signed_cookie)

        # Save a distinct value
        resp = client.post(
            "/admin/settings/min_sessions_for_ai",
            data={"value": "9", "X-CSRF-Token": token},
            cookies={"session_id": signed_cookie, "csrftoken": token},
        )
        assert resp.status_code == 200

        # The cache key was popped by set_setting. Re-prewarm to load from DB.
        from sqlalchemy import create_engine

        from app.config import settings as app_settings_cfg

        engine = create_engine(app_settings_cfg.DATABASE_URL)
        with Session(engine) as db:
            prewarm_cache(db)
            val = get_int("min_sessions_for_ai")
        engine.dispose()
        assert val == 9, (
            f"Expected cached int 9 after prewarm, got {val!r}"
        )

    def test_setting_save_response_contains_saved_marker(
        self,
        client: Any,
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """Successful save response contains a 'Saved' confirmation marker."""
        signed_cookie = seeded_admin_user["signed_cookie"]
        token = _prime_csrf(client, signed_cookie)

        resp = client.post(
            "/admin/settings/home_recent_brews_limit",
            data={"value": "5", "X-CSRF-Token": token},
            cookies={"session_id": signed_cookie, "csrftoken": token},
        )
        assert resp.status_code == 200
        assert "Saved" in resp.text, (
            f"Expected 'Saved' confirmation in response, got: {resp.text[:300]}"
        )


class TestReadonlyRowsRejected:
    """D-04: POST to read-only rows returns 403; no mutation occurs."""

    def test_setup_completed_rejected(
        self,
        client: Any,
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """POST to setup_completed returns 403 (T-09-15 tamper block)."""
        signed_cookie = seeded_admin_user["signed_cookie"]
        token = _prime_csrf(client, signed_cookie)

        original = _get_setting_from_db("setup_completed")

        resp = client.post(
            "/admin/settings/setup_completed",
            data={"value": "false", "X-CSRF-Token": token},
            cookies={"session_id": signed_cookie, "csrftoken": token},
        )
        assert resp.status_code == 403, (
            f"Expected 403 for setup_completed POST, got {resp.status_code}"
        )

        # Value must not have changed
        after = _get_setting_from_db("setup_completed")
        assert after == original, (
            f"setup_completed mutated despite 403: {original!r} -> {after!r}"
        )

    def test_last_backup_status_rejected(
        self,
        client: Any,
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """POST to last_backup_status returns 403; no mutation."""
        signed_cookie = seeded_admin_user["signed_cookie"]
        token = _prime_csrf(client, signed_cookie)

        original = _get_setting_from_db("last_backup_status")

        resp = client.post(
            "/admin/settings/last_backup_status",
            data={"value": "hacked", "X-CSRF-Token": token},
            cookies={"session_id": signed_cookie, "csrftoken": token},
        )
        assert resp.status_code == 403, (
            f"Expected 403 for last_backup_status POST, got {resp.status_code}"
        )

        after = _get_setting_from_db("last_backup_status")
        assert after == original, (
            f"last_backup_status mutated despite 403: {original!r} -> {after!r}"
        )

    def test_encryption_key_fingerprint_rejected(
        self,
        client: Any,
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """POST to encryption_key_primary_fingerprint returns 403 (Research A1)."""
        signed_cookie = seeded_admin_user["signed_cookie"]
        token = _prime_csrf(client, signed_cookie)

        resp = client.post(
            "/admin/settings/encryption_key_primary_fingerprint",
            data={"value": "tampered", "X-CSRF-Token": token},
            cookies={"session_id": signed_cookie, "csrftoken": token},
        )
        assert resp.status_code == 403

    def test_non_admin_post_returns_403(
        self,
        client: Any,
        regular_session: dict[str, str],
        seeded_regular_user: dict[str, Any],
    ) -> None:
        """A non-admin POST to /admin/settings/{key} returns 403."""
        # Prime csrf via GET (will be denied, but we get a token cookie)
        signed_cookie = seeded_regular_user["signed_cookie"]
        client.cookies.set("session_id", signed_cookie)
        client.cookies.delete("csrftoken")
        resp_get = client.get("/admin/settings", cookies={"session_id": signed_cookie})
        # GET will be 403 for non-admin, but we can still attempt the POST
        token = resp_get.cookies.get("csrftoken") or client.cookies.get("csrftoken", "")
        if not token:
            token = "fake_token"

        resp = client.post(
            "/admin/settings/min_sessions_for_ai",
            data={"value": "99", "X-CSRF-Token": token},
            cookies={"session_id": signed_cookie, "csrftoken": token},
        )
        assert resp.status_code == 403, (
            f"Expected 403 for non-admin POST to settings, got {resp.status_code}"
        )
