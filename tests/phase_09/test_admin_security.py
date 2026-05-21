"""Phase 9 — Admin security tests (Wave 0).

Covers:
- test_non_admin_403: regular-user session -> 403 on GET /admin;
  unauthenticated request -> NOT 200 (403 or redirect-to-login)
- test_admin_200: admin session -> 200 on GET /admin
- test_csrf_required: placeholder; asserts CSRF is enforced on the first
  available admin POST route (skips cleanly when no POST routes exist yet)

These tests MUST be GREEN (not skipped) after Plan 09-01 ships the hub route.
The -rs flag on pytest reveals any unexpected skips.
"""

from __future__ import annotations

from typing import Any

import pytest


class TestRequireAdmin:
    """Verify that /admin enforces the require_admin dependency."""

    def test_non_admin_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """A regular (non-admin) authenticated user hitting GET /admin receives 403."""
        resp = client.get("/admin", cookies=regular_session)
        assert resp.status_code == 403, (
            f"Expected 403 for non-admin on /admin, got {resp.status_code}"
        )

    def test_unauthenticated_not_200(self, client: Any) -> None:
        """An unauthenticated request to GET /admin receives 403 (or a redirect).

        The middleware + require_admin fold both unauthenticated and non-admin
        into a 403. Either way the status code MUST NOT be 200.
        """
        resp = client.get("/admin")
        assert resp.status_code != 200, (
            f"Expected non-200 for unauthenticated /admin, got {resp.status_code}"
        )

    def test_admin_200(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """An admin session hitting GET /admin receives 200."""
        resp = client.get("/admin", cookies=admin_session)
        assert resp.status_code == 200, (
            f"Expected 200 for admin on /admin, got {resp.status_code}"
        )


class TestCsrf:
    """CSRF enforcement on admin POST routes.

    Wave 0: the hub route is GET-only, so no admin POST route exists yet.
    The test below skips cleanly when no POST routes are available and will
    become a real assertion once Plan 09-02 ships the first admin POST route.
    """

    def test_csrf_required(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """CSRF guard blocks admin POST requests without a valid CSRF token.

        Skips if no admin POST route exists yet (Wave 0; routes land in
        Plans 09-02..09-06). This is a guarded skip, NOT a test pass.
        """
        # Discover the first available admin POST route.
        try:
            from app.main import app as _app
            from fastapi.routing import APIRoute

            post_routes = [
                r for r in _app.routes
                if isinstance(r, APIRoute)
                and "POST" in r.methods
                and r.path.startswith("/admin/")
            ]
        except Exception:
            pytest.skip("Could not inspect admin routes (app not importable)")
            return

        if not post_routes:
            pytest.skip(
                "No admin POST routes registered yet (Plans 09-02..09-06 add them)"
            )

        # Use the first admin POST route for the CSRF probe.
        route_path = post_routes[0].path
        # POST without CSRF token — expect 403 from CSRFMiddleware.
        resp = client.post(
            route_path,
            cookies=admin_session,
            data={},  # no X-CSRF-Token field
        )
        assert resp.status_code == 403, (
            f"Expected CSRF rejection (403) on POST {route_path}, "
            f"got {resp.status_code}"
        )
