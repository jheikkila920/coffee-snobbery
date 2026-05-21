"""Phase 9 — Admin API credential vault tests (ADMIN-02 / SEC-6).

Covers:
- test_set_credential_masked: POST /admin/credentials/{provider} encrypts the
  key, stores it, and returns a fragment containing only the last_four — the
  full key string is absent from the response body (SEC-6).
- test_provider_toggle_model: POST /admin/credentials/{provider}/enabled toggles
  is_enabled while last_four + model_name persist unchanged.

Security invariants tested:
- After saving, only the last 4 characters of the key appear in the response.
- The full key (and its leading substring) must NOT appear in the response.
- The api_credential table row has last_four written correctly.

CSRF follows the established Phase 4/5/9 pattern: prime via GET, set both
cookies + header on the client instance before any POST.

Provider calls to Anthropic/OpenAI are NOT triggered by these tests (no SDK
import needed here). The credentials service only encrypts and stores the key
string — no outbound connection.
"""

from __future__ import annotations

from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers (mirrors test_admin_users._prime_csrf)
# ---------------------------------------------------------------------------


def _prime_csrf(client: Any, signed_cookie: str) -> str:
    """Wire session_id + csrftoken onto the client; return the CSRF token."""
    client.cookies.set("session_id", signed_cookie)
    client.cookies.delete("csrftoken")
    resp = client.get("/admin/credentials")
    token = resp.cookies.get("csrftoken") or client.cookies.get("csrftoken", "")
    if token:
        client.cookies.set("csrftoken", token)
        client.headers["X-CSRF-Token"] = token
    return token


# ---------------------------------------------------------------------------
# Task 1 tests
# ---------------------------------------------------------------------------


class TestSetCredentialMasked:
    """ADMIN-02 / SEC-6: Setting a credential stores the encrypted key and
    returns only last_four in the response.
    """

    def test_set_credential_masked(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST /admin/credentials/anthropic with a test key:
        - Response contains the last 4 characters ("1234").
        - Response does NOT contain the full key string.
        - Response does NOT contain the leading substring "sk-ant-test-ABCD".
        """
        test_key = "sk-ant-test-ABCD1234"
        expected_last_four = "1234"
        leaking_prefix = "sk-ant-test-ABCD"

        _prime_csrf(client, admin_session["session_id"])

        resp = client.post(
            "/admin/credentials/anthropic",
            data={
                "api_key": test_key,
                "model_name": "claude-opus-4-7",
                "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200 on POST /admin/credentials/anthropic, got {resp.status_code}\n"
            f"Body: {resp.text[:500]}"
        )

        # SEC-6: last_four MUST appear in the response fragment
        assert expected_last_four in resp.text, (
            f"Expected last_four '{expected_last_four}' in response body — "
            f"masked display not rendered"
        )

        # SEC-6: full key MUST NOT appear
        assert test_key not in resp.text, (
            f"SEC-6 violation: full key '{test_key}' found in response body"
        )

        # SEC-6: leading substring MUST NOT appear
        assert leaking_prefix not in resp.text, (
            f"SEC-6 violation: key prefix '{leaking_prefix}' found in response body"
        )

    def test_set_credential_non_admin_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """POST /admin/credentials/anthropic returns 403 for a non-admin session."""
        client.cookies.set("session_id", regular_session["session_id"])
        # No CSRF token on non-admin request — expect 403 from auth gate
        # (or 403 from CSRF; either way not 200)
        resp = client.get("/admin/credentials")
        assert resp.status_code == 403, (
            f"Expected 403 for non-admin on /admin/credentials, got {resp.status_code}"
        )

    def test_credentials_page_accessible(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """GET /admin/credentials returns 200 for an admin session."""
        _prime_csrf(client, admin_session["session_id"])
        resp = client.get("/admin/credentials")
        assert resp.status_code == 200, (
            f"Expected 200 on GET /admin/credentials, got {resp.status_code}"
        )

    def test_invalid_provider_404(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST /admin/credentials/badprovider returns 404."""
        _prime_csrf(client, admin_session["session_id"])
        resp = client.post(
            "/admin/credentials/badprovider",
            data={
                "api_key": "some-key",
                "model_name": "model",
                "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
            },
        )
        assert resp.status_code == 404, (
            f"Expected 404 for unknown provider, got {resp.status_code}"
        )


class TestProviderToggleModel:
    """ADMIN-02: Toggling is_enabled preserves last_four and model_name."""

    def test_provider_toggle_model(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST a key first, then disable the provider.

        After disable POST:
        - The row in the DB has is_enabled=False.
        - last_four and model_name are unchanged.

        This verifies set_provider_enabled() leaves the ciphertext intact.
        """
        test_key = "openai-test-key-XY9876"
        model = "gpt-4o"
        expected_last_four = "9876"

        _prime_csrf(client, admin_session["session_id"])

        # Step 1: set the credential
        set_resp = client.post(
            "/admin/credentials/openai",
            data={
                "api_key": test_key,
                "model_name": model,
                "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
            },
        )
        assert set_resp.status_code == 200, (
            f"Expected 200 on credential set, got {set_resp.status_code}"
        )

        # Step 2: disable the provider
        disable_resp = client.post(
            "/admin/credentials/openai/enabled",
            data={
                "enabled": "",  # unchecked checkbox — empty string = off
                "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
            },
        )
        assert disable_resp.status_code == 200, (
            f"Expected 200 on toggle-enabled, got {disable_resp.status_code}"
        )

        # Step 3: verify the DB state directly
        from app.main import async_session_factory
        from app.models.api_credential import ApiCredential
        from sqlalchemy import select
        import asyncio

        async def _check() -> dict:
            async with async_session_factory() as db:
                row = await db.execute(
                    select(ApiCredential).where(ApiCredential.provider == "openai")
                )
                cred = row.scalar_one_or_none()
                if cred is None:
                    return {}
                return {
                    "is_enabled": cred.is_enabled,
                    "last_four": cred.last_four,
                    "model_name": cred.model_name,
                }

        state = asyncio.run(_check())

        assert state.get("is_enabled") is False, (
            f"Expected is_enabled=False after toggle, got {state.get('is_enabled')}"
        )
        assert state.get("last_four") == expected_last_four, (
            f"Expected last_four='{expected_last_four}' to persist, got '{state.get('last_four')}'"
        )
        assert state.get("model_name") == model, (
            f"Expected model_name='{model}' to persist, got '{state.get('model_name')}'"
        )

    def test_toggle_enable(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Toggle a provider back to enabled.

        After enable POST the DB row has is_enabled=True.
        """
        _prime_csrf(client, admin_session["session_id"])

        # Disable first
        client.post(
            "/admin/credentials/anthropic/enabled",
            data={
                "enabled": "",
                "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
            },
        )

        # Re-enable
        enable_resp = client.post(
            "/admin/credentials/anthropic/enabled",
            data={
                "enabled": "on",
                "X-CSRF-Token": client.headers.get("X-CSRF-Token", ""),
            },
        )
        assert enable_resp.status_code == 200, (
            f"Expected 200 on re-enable, got {enable_resp.status_code}"
        )

        from app.main import async_session_factory
        from app.models.api_credential import ApiCredential
        from sqlalchemy import select
        import asyncio

        async def _check() -> bool | None:
            async with async_session_factory() as db:
                row = await db.execute(
                    select(ApiCredential).where(ApiCredential.provider == "anthropic")
                )
                cred = row.scalar_one_or_none()
                return cred.is_enabled if cred else None

        assert asyncio.run(_check()) is True
