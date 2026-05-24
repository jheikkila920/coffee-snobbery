"""Focused tests for the unauthorized_redirect_handler added to app/main.py.

Covers the three 401 branches (browser full-page nav, HTMX request, JSON/API
client) plus non-regression tests for non-401 status delegation and /healthz.

GET / is used for the 401 tests because it is require_user-gated and always
raises HTTPException(401) for an unauthenticated request. The DB-touching
lifespan (SELECT 1 smoke check) means the `client` fixture skips when Postgres
is unreachable — mirror the skip-gate pattern from tests/routers/test_home.py.
"""

from __future__ import annotations

from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Skip gate                                                                    #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    """Skip the test if Postgres is not reachable (mirrors test_home.py)."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — unauthorized_redirect tests need DB lifespan")


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_full_page_browser_nav_redirects_to_login(app: Any) -> None:
    """GET / with Accept: text/html (no HX-Request) -> 303, Location: /login."""
    _require_postgres()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_htmx_request_gets_hx_redirect_header(app: Any) -> None:
    """GET / with HX-Request: true -> 401 + HX-Redirect: /login (no DOM swap)."""
    _require_postgres()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/", headers={"HX-Request": "true"}, follow_redirects=False)
    assert resp.status_code == 401
    assert resp.headers.get("hx-redirect") == "/login"


def test_json_client_still_gets_401_json(app: Any) -> None:
    """GET / with Accept: application/json -> 401 JSON (default handler preserved)."""
    _require_postgres()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/", headers={"Accept": "application/json"}, follow_redirects=False)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


def test_unknown_path_still_returns_default_404(app: Any) -> None:
    """GET /this-path-does-not-exist with Accept: text/html -> 404 (non-401 delegation).

    A browser Accept header must NOT cause a 404 to redirect — the handler only
    branches on status_code == 401.
    """
    _require_postgres()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get(
        "/this-path-does-not-exist",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


def test_healthz_unaffected(app: Any) -> None:
    """GET /healthz -> 200 (handler never fires for a successful 200 route)."""
    _require_postgres()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
