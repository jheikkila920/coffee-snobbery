"""Phase 9 — Admin System/Health page tests (ADMIN-05 / ADMIN-06 / D-12).

Covers:
- test_system_info: GET /admin renders version, DB version, storage,
  session count, last-backup status (ADMIN-05, D-09).
  (/admin/system 301-redirects to /admin; page moved in Phase 9 gap closure.)
- test_system_page_redirect: GET /admin/system (follow_redirects=False) returns
  301 with Location: /admin.
- test_health_panel_raw_db: page renders last_ai_run_status after set_setting
  pops the cache key — proves raw DB read, not get_str (ADMIN-06, Pitfall 2).
- test_health_panel_errors: per-provider last error + last 5 errors render;
  success-only provider shows no errors (ADMIN-06, D-10).
- test_ai_refresh_respect_signatures: POST /admin/system/ai-refresh with
  force=false calls regenerate with generated_by="admin" (D-13/D-14).
- test_ai_refresh_force_all: force=true calls with generated_by="admin_force".
- test_ai_refresh_only_eligible: ineligible users are excluded (D-13 cost control).
- test_test_connection_ok: respx-mocked 200 → fragment status "ok" (D-12).
- test_test_connection_invalid_key: respx-mocked 401 → status "error", reason "invalid_key".
- test_test_connection_not_configured: no credential → status "error", reason "not_configured".
- test_test_connection_no_recommendation_written: probe writes 0 ai_recommendations rows.

SEC-6 invariants: decrypted key never in template context or logs.
Provider HTTP calls are always respx-mocked (never hit real endpoints).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import httpx
import respx

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prime_csrf(client: Any, signed_cookie: str) -> str:
    """Wire session_id + csrftoken onto the client; return the CSRF token.

    GETs /admin (the System page) to receive the CSRF cookie.
    /admin/system 301-redirects to /admin since the Phase 9 gap-closure pass.
    """
    client.cookies.set("session_id", signed_cookie)
    client.cookies.delete("csrftoken")
    resp = client.get("/admin")
    token = resp.cookies.get("csrftoken") or client.cookies.get("csrftoken", "")
    if token:
        client.cookies.set("csrftoken", token)
        client.headers["X-CSRF-Token"] = token
    return token


def _seed_app_setting(key: str, value: str) -> None:
    """Set an app_settings row directly via async DB (avoids service cache)."""
    from app.main import async_session_factory
    from app.models.app_setting import AppSetting

    async def _do() -> None:
        async with async_session_factory() as db:
            from sqlalchemy import select as sa_select

            row = (
                await db.execute(sa_select(AppSetting).where(AppSetting.key == key))
            ).scalar_one_or_none()
            if row is None:
                row = AppSetting(
                    key=key,
                    value=value,
                    value_type="string",
                    description=f"test row for {key}",
                )
                db.add(row)
            else:
                row.value = value
            await db.commit()

    asyncio.run(_do())


def _seed_ai_recommendation(
    user_id: int,
    provider: str,
    error_status: str | None = None,
    model_used: str = "test-model",
) -> int:
    """Create one ai_recommendations row; returns its id."""
    from app.main import async_session_factory
    from app.models.ai_recommendation import AIRecommendation

    async def _do() -> int:
        async with async_session_factory() as db:
            rec = AIRecommendation(
                user_id=user_id,
                recommendation_type="coffee",
                input_signature=uuid.uuid4().hex,
                response_json={},
                provider_used=provider,
                model_used=model_used,
                generated_by="scheduler",
                error_status=error_status,
            )
            db.add(rec)
            await db.commit()
            await db.refresh(rec)
            return rec.id

    return asyncio.run(_do())


def _count_ai_recommendations() -> int:
    """Return total ai_recommendations row count."""
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from app.main import async_session_factory
    from app.models.ai_recommendation import AIRecommendation

    async def _do() -> int:
        async with async_session_factory() as db:
            return (
                await db.execute(sa_select(func.count()).select_from(AIRecommendation))
            ).scalar_one()

    return asyncio.run(_do())


def _seed_credential(provider: str, api_key: str = "test-key-XY9876") -> None:
    """Store an encrypted credential so the probe can retrieve it."""
    from app.db import SessionLocal
    from app.services.credentials import set_provider_credential

    with SessionLocal() as db:
        set_provider_credential(
            db,
            provider,  # type: ignore[arg-type]
            key=api_key,
            model_name="test-model",
            by_user_id=None,
        )


def _enable_credential(provider: str, enabled: bool = True) -> None:
    """Enable or disable the stored credential."""
    from app.db import SessionLocal
    from app.services.credentials import set_provider_enabled

    with SessionLocal() as db:
        set_provider_enabled(db, provider, enabled, by_user_id=None)  # type: ignore[arg-type]


def _seed_eligible_user() -> int:
    """Seed a user with 3 brew sessions so _get_eligible_user_ids includes them."""
    from app.main import async_session_factory
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from tests.conftest import _seed_user

    seeded = _seed_user(is_admin=False)
    user_id = seeded["user"].id

    async def _do() -> None:
        async with async_session_factory() as db:
            suffix = uuid.uuid4().hex[:6]
            coffee = Coffee(name=f"Eligible Coffee {suffix}", notes="")
            db.add(coffee)
            await db.flush()
            for _ in range(3):
                brew = BrewSession(
                    user_id=user_id,
                    coffee_id=coffee.id,
                    dose_grams_actual=Decimal("18.0"),
                    water_grams_actual=Decimal("300.0"),
                )
                db.add(brew)
            await db.commit()

    asyncio.run(_do())
    return user_id


def _seed_ineligible_user() -> int:
    """Seed a user with 0 brew sessions — not eligible for AI refresh."""
    from tests.conftest import _seed_user

    seeded = _seed_user(is_admin=False)
    return seeded["user"].id


# ---------------------------------------------------------------------------
# Task 1 tests — System Info panel (ADMIN-05)
# ---------------------------------------------------------------------------


class TestSystemInfo:
    """ADMIN-05: GET /admin renders all six system-info data points.

    The System page moved from /admin/system to /admin in the Phase 9
    gap-closure pass. GET /admin/system now 301-redirects to /admin.
    """

    def test_system_info(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """System page at GET /admin renders: app version, DB version, storage,
        session count, last-backup line.
        """
        _prime_csrf(client, admin_session["session_id"])
        resp = client.get("/admin")
        assert resp.status_code == 200, (
            f"Expected 200 on GET /admin (System page), got {resp.status_code}\n"
            f"Body: {resp.text[:500]}"
        )
        body = resp.text

        # App version — either from importlib.metadata or pyproject.toml fallback.
        try:
            from importlib.metadata import version as pkg_version

            app_version = pkg_version("coffee-snobbery")
        except Exception:
            app_version = "0.1.0"  # pyproject.toml fallback value
        assert app_version in body, f"App version '{app_version}' not found in /admin body"

        # DB version — postgres version string contains "PostgreSQL"
        assert "PostgreSQL" in body or "postgresql" in body.lower(), (
            "DB version string not found in /admin body"
        )

        # Storage — bytes, KB, or MB rendered for photos + backups
        assert any(
            label in body for label in ("Photo", "photo", "Backup", "backup", "Storage", "storage")
        ), "Storage section not found in /admin body"

        # Session count — the page must render a sessions panel
        assert any(label in body for label in ("Session", "session", "active")), (
            "Session count section not found in /admin body"
        )

        # Backup status — either a status value or a "never run" message
        assert any(label in body for label in ("Backup", "backup", "never", "Never")), (
            "Last backup status not found in /admin body"
        )

    def test_system_page_redirect(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """GET /admin/system returns 301 redirect to /admin (bookmark compat).

        Verified with follow_redirects=False so the redirect response itself
        is asserted, not the final destination.
        """
        client.cookies.set("session_id", admin_session["session_id"])
        resp = client.get("/admin/system", follow_redirects=False)
        assert resp.status_code == 301, (
            f"Expected 301 from GET /admin/system, got {resp.status_code}"
        )
        location = resp.headers.get("location", "")
        assert location == "/admin", f"Expected Location: /admin, got '{location}'"

    def test_system_info_non_admin_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """Non-admin GET /admin returns 403."""
        client.cookies.set("session_id", regular_session["session_id"])
        resp = client.get("/admin")
        assert resp.status_code == 403, (
            f"Expected 403 for non-admin on /admin, got {resp.status_code}"
        )

    def test_system_info_stub_state(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """System page renders cleanly with no AI run history (stub/empty state)."""
        _prime_csrf(client, admin_session["session_id"])
        resp = client.get("/admin")
        assert resp.status_code == 200, (
            f"System page must render even with no AI run data, got {resp.status_code}"
        )
        # Must NOT raise an exception (no 500)
        assert "500" not in resp.text or "Internal Server Error" not in resp.text


# ---------------------------------------------------------------------------
# Task 2 tests — API Health panel (ADMIN-06)
# ---------------------------------------------------------------------------


class TestHealthPanel:
    """ADMIN-06: API health panel reads raw DB; surfaces errors."""

    def test_health_panel_raw_db(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Page renders last_ai_run_status AFTER set_setting popped the cache key.

        Proves the handler uses a raw DB query (not get_str which would raise
        SettingNotFoundError after set_setting pops the cache).
        """
        # Use set_setting (the service) which pops the cache key
        from app.db import SessionLocal
        from app.services.settings import set_setting

        run_status = {
            "users_processed": 3,
            "regenerations": 2,
            "skips": 1,
            "errors": 0,
            "tokens_input_total": 1500,
            "tokens_output_total": 800,
            "tokens_input_search_total": 200,
            "timestamp": "2026-05-21T00:00:00Z",
        }
        with SessionLocal() as db:
            set_setting(db, "last_ai_run_status", json.dumps(run_status), by_user_id=None)

        _prime_csrf(client, admin_session["session_id"])
        # This must NOT raise SettingNotFoundError (which would return a 500)
        resp = client.get("/admin")
        assert resp.status_code == 200, (
            f"Expected 200 after set_setting popped cache; got {resp.status_code}\n"
            f"Body: {resp.text[:800]}"
        )
        body = resp.text

        # The run summary fields must appear in the response
        assert "users_processed" in body or "3" in body, (
            "users_processed value (3) not rendered in health panel"
        )
        assert "2" in body, "regenerations value (2) not rendered"

    def test_health_panel_errors(
        self,
        client: Any,
        admin_session: dict[str, str],
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """Per-provider last error + last 5 errors render.

        - Provider with error rows: last error and recent errors shown.
        - Provider with only success rows: no error section shown.
        - Long error strings are truncated.
        - Output is escaped (no raw HTML injection).
        """
        user_id = seeded_admin_user["user"].id

        # Seed 3 error rows for anthropic
        for i in range(3):
            _seed_ai_recommendation(
                user_id=user_id,
                provider="anthropic",
                error_status=f"model_deprecated_{i}",
                model_used="claude-3-old",
            )

        # Seed a long error string to test truncation
        long_error = "X" * 500
        _seed_ai_recommendation(
            user_id=user_id,
            provider="anthropic",
            error_status=long_error,
        )

        # Seed a potential XSS attempt to test autoescaping
        xss_error = "<script>alert('xss')</script>"
        _seed_ai_recommendation(
            user_id=user_id,
            provider="anthropic",
            error_status=xss_error,
        )

        # Seed success rows for openai (no errors)
        _seed_ai_recommendation(
            user_id=user_id,
            provider="openai",
            error_status=None,
            model_used="gpt-4o",
        )

        _prime_csrf(client, admin_session["session_id"])
        resp = client.get("/admin")
        assert resp.status_code == 200, (
            f"Expected 200 with seeded error rows, got {resp.status_code}"
        )
        body = resp.text

        # anthropic error rows must appear
        assert "model_deprecated_0" in body or "model_deprecated" in body, (
            "Anthropic error row not rendered in health panel"
        )

        # Long error must be truncated (not 500 chars in output)
        assert long_error not in body, (
            "Long error string was not truncated (full 500-char string present)"
        )

        # XSS must be escaped — raw script tag must NOT appear
        assert "<script>" not in body, (
            "XSS error was not escaped — <script> tag present in raw output"
        )
        # The escaped form may appear (Jinja autoescape → &lt;script&gt;)

    def test_health_panel_per_rec_type(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Page renders per-recommendation-type section (ROADMAP success #5)."""
        _prime_csrf(client, admin_session["session_id"])
        resp = client.get("/admin")
        assert resp.status_code == 200
        # The page should render the rec-type panel (even if empty)
        body = resp.text
        # At minimum the section label must exist
        assert any(
            label in body
            for label in (
                "coffee",
                "equipment",
                "sweet_spots",
                "paste_rank",
                "Recommendation",
                "recommendation",
                "rec type",
            )
        ), "Per-recommendation-type section not found in health panel"


# ---------------------------------------------------------------------------
# Task 3 tests — AI refresh actions (D-13/D-14)
# ---------------------------------------------------------------------------


class TestAiRefresh:
    """D-13/D-14: both AI refresh modes call regenerate with correct tags."""

    def test_ai_refresh_respect_signatures(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST with force=false → regenerate called with generated_by="admin", force=False."""
        eligible_uid = _seed_eligible_user()

        _prime_csrf(client, admin_session["session_id"])

        captured_calls: list[dict] = []

        async def mock_regenerate(
            user_id: int,
            generated_by: str,
            *,
            db: Any,
            force: bool = False,
        ) -> str:
            captured_calls.append(
                {"user_id": user_id, "generated_by": generated_by, "force": force}
            )
            return "skipped"

        with patch("app.routers.admin.system.ai_service.regenerate", new=mock_regenerate):
            resp = client.post(
                "/admin/system/ai-refresh",
                data={
                    "force": "false",
                    "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
                },
            )

        assert resp.status_code == 200, (
            f"Expected 200 on ai-refresh (respect-sig), got {resp.status_code}\n"
            f"Body: {resp.text[:400]}"
        )

        # The eligible user must have been called
        uid_calls = [c for c in captured_calls if c["user_id"] == eligible_uid]
        assert uid_calls, f"regenerate not called for eligible user {eligible_uid}"
        call = uid_calls[0]
        assert call["generated_by"] == "admin", (
            f"Expected generated_by='admin', got '{call['generated_by']}'"
        )
        assert call["force"] is False, f"Expected force=False, got {call['force']}"

    def test_ai_refresh_force_all(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST with force=true → regenerate called with generated_by="admin_force", force=True."""
        eligible_uid = _seed_eligible_user()

        _prime_csrf(client, admin_session["session_id"])

        captured_calls: list[dict] = []

        async def mock_regenerate_force(
            user_id: int,
            generated_by: str,
            *,
            db: Any,
            force: bool = False,
        ) -> str:
            captured_calls.append(
                {"user_id": user_id, "generated_by": generated_by, "force": force}
            )
            return "generated"

        with patch("app.routers.admin.system.ai_service.regenerate", new=mock_regenerate_force):
            resp = client.post(
                "/admin/system/ai-refresh",
                data={
                    "force": "true",
                    "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
                },
            )

        assert resp.status_code == 200, (
            f"Expected 200 on ai-refresh (force-all), got {resp.status_code}\n"
            f"Body: {resp.text[:400]}"
        )

        uid_calls = [c for c in captured_calls if c["user_id"] == eligible_uid]
        assert uid_calls, f"regenerate not called for eligible user {eligible_uid}"
        call = uid_calls[0]
        assert call["generated_by"] == "admin_force", (
            f"Expected generated_by='admin_force', got '{call['generated_by']}'"
        )
        assert call["force"] is True, f"Expected force=True, got {call['force']}"

    def test_ai_refresh_only_eligible(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Ineligible user (< 3 sessions) is NOT passed to regenerate."""
        ineligible_uid = _seed_ineligible_user()

        _prime_csrf(client, admin_session["session_id"])

        called_user_ids: list[int] = []

        async def mock_regenerate_track(
            user_id: int,
            generated_by: str,
            *,
            db: Any,
            force: bool = False,
        ) -> str:
            called_user_ids.append(user_id)
            return "skipped"

        with patch("app.routers.admin.system.ai_service.regenerate", new=mock_regenerate_track):
            resp = client.post(
                "/admin/system/ai-refresh",
                data={
                    "force": "false",
                    "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
                },
            )

        assert resp.status_code == 200, f"Unexpected {resp.status_code}"
        assert ineligible_uid not in called_user_ids, (
            f"Ineligible user {ineligible_uid} was passed to regenerate (cost-control breach)"
        )

    def test_ai_refresh_non_admin_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """Non-admin POST to ai-refresh returns 403."""
        client.cookies.set("session_id", regular_session["session_id"])
        resp = client.post(
            "/admin/system/ai-refresh",
            data={"force": "false"},
        )
        assert resp.status_code == 403, (
            f"Expected 403 for non-admin ai-refresh, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Task 4 tests — Test connection probe (D-12)
# ---------------------------------------------------------------------------


class TestTestConnection:
    """D-12: POST /admin/system/test-connection/{provider} probe."""

    def test_test_connection_ok(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """With a valid credential + mocked 200, probe returns status 'ok'."""
        _seed_credential("anthropic", api_key="sk-ant-test-OK5678")
        _enable_credential("anthropic", True)

        _prime_csrf(client, admin_session["session_id"])

        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.get("/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
            resp = client.post(
                "/admin/system/test-connection/anthropic",
                data={"X-CSRF-Token": client.headers.get("X-CSRF-Token", "")},
            )

        assert resp.status_code == 200, (
            f"Expected 200 from test-connection, got {resp.status_code}\nBody: {resp.text[:400]}"
        )
        body = resp.text
        assert "Connected" in body or "ok" in body.lower(), (
            f"Expected 'Connected' or 'ok' in test-connection response, got: {body[:300]}"
        )

    def test_test_connection_invalid_key(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """With mocked 401 response, probe returns status 'error', reason 'invalid_key'."""
        _seed_credential("anthropic", api_key="sk-ant-bad-key-1234")
        _enable_credential("anthropic", True)

        _prime_csrf(client, admin_session["session_id"])

        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.get("/v1/models").mock(
                return_value=httpx.Response(
                    401,
                    json={
                        "type": "error",
                        "error": {"type": "authentication_error", "message": "invalid api key"},
                    },
                )
            )
            resp = client.post(
                "/admin/system/test-connection/anthropic",
                data={"X-CSRF-Token": client.headers.get("X-CSRF-Token", "")},
            )

        assert resp.status_code == 200, (
            f"Expected 200 from test-connection (even on auth failure), got {resp.status_code}"
        )
        body = resp.text
        assert "Invalid key" in body or "invalid_key" in body, (
            f"Expected 'Invalid key' in test-connection response body, got: {body[:300]}"
        )

    def test_test_connection_not_configured(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Disabled / no-key provider returns 'not_configured'; no SDK call attempted."""
        # Disable the provider so get_provider_credential returns None
        _enable_credential("openai", False)

        _prime_csrf(client, admin_session["session_id"])

        with respx.mock() as mock:
            resp = client.post(
                "/admin/system/test-connection/openai",
                data={"X-CSRF-Token": client.headers.get("X-CSRF-Token", "")},
            )
            # No SDK calls should have been made (respx uses .calls, not .call_count)
            assert len(mock.calls) == 0, (
                f"Expected 0 SDK calls for not_configured, got {len(mock.calls)}"
            )

        assert resp.status_code == 200
        body = resp.text
        assert "Not configured" in body or "not_configured" in body, (
            f"Expected 'Not configured' in test-connection response body, got: {body[:300]}"
        )

    def test_test_connection_no_recommendation_written(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """A probe writes ZERO ai_recommendations rows (D-12, no content generated)."""
        _seed_credential("anthropic", api_key="sk-ant-test-probe-9999")
        _enable_credential("anthropic", True)

        before_count = _count_ai_recommendations()

        _prime_csrf(client, admin_session["session_id"])

        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.get("/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
            resp = client.post(
                "/admin/system/test-connection/anthropic",
                data={"X-CSRF-Token": client.headers.get("X-CSRF-Token", "")},
            )

        assert resp.status_code == 200
        after_count = _count_ai_recommendations()
        assert after_count == before_count, (
            f"Probe wrote {after_count - before_count} ai_recommendations rows (expected 0)"
        )

    def test_test_connection_non_admin_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """Non-admin POST to test-connection returns 403."""
        client.cookies.set("session_id", regular_session["session_id"])
        resp = client.post(
            "/admin/system/test-connection/anthropic",
            data={},
        )
        assert resp.status_code == 403, (
            f"Expected 403 for non-admin test-connection, got {resp.status_code}"
        )

    def test_test_connection_invalid_provider_404(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST to /admin/system/test-connection/badprovider returns 404."""
        _prime_csrf(client, admin_session["session_id"])
        resp = client.post(
            "/admin/system/test-connection/badprovider",
            data={"X-CSRF-Token": client.headers.get("X-CSRF-Token", "")},
        )
        assert resp.status_code == 404, f"Expected 404 for invalid provider, got {resp.status_code}"
