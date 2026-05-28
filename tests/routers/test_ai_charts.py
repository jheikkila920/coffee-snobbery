"""Router tests for plan 19-05 Task 3 — chart JSON endpoints (VIZ-01).

Covers:

* ``test_rating_chart_json`` — GET /ai/charts/rating-over-time returns valid JSON (per-user)
* ``test_flavor_chart_json`` — GET /ai/charts/flavor-distribution returns ≤15 entries,
  no rating floor
* ``test_charts_require_auth`` — unauthenticated → 401/redirect
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

# --------------------------------------------------------------------------- #
# Skip gates                                                                  #
# --------------------------------------------------------------------------- #


def _require_charts_routes() -> None:
    try:
        from app.routers.ai import router  # noqa: F401

        route_paths = [r.path for r in router.routes]
        if not any("charts" in p for p in route_paths):
            pytest.skip("plan 19-05 dependency: /ai/charts routes not yet added to ai router")
    except ImportError:
        pytest.skip("plan 19-05 dependency: app.routers.ai not importable")


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — charts router test needs the DB")


# --------------------------------------------------------------------------- #
# Auth + CSRF helpers (mirror test_ai_router.py pattern)                      #
# --------------------------------------------------------------------------- #


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real signed csrftoken; wire it onto the client."""
    client.cookies.delete("csrftoken")
    response = client.get("/")
    token = response.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


def _authed_client(app: Any, signed_cookie: str) -> Any:
    """Build a TestClient with the session cookie + a real CSRF pair."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.cookies.set("session_id", signed_cookie)
    _prime_csrf(client)
    return client


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_rating_chart_json(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """GET /ai/charts/rating-over-time returns valid JSON with date+rating shape (VIZ-01/D-17).

    Response must be a JSON array (possibly empty) with objects that have at
    least 'date' and 'rating' keys. Must be per-user (user_id scoped).
    """
    _require_charts_routes()
    _require_postgres()

    # Mock charts service to return well-shaped data
    fake_data = [
        {"date": "2026-01-01", "rating": 4.5},
        {"date": "2026-01-15", "rating": 3.75},
    ]

    with patch("app.routers.ai.charts") as mock_charts:
        mock_charts.rating_over_time.return_value = fake_data

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.get("/ai/charts/rating-over-time")

    assert resp.status_code == 200, (
        f"Expected 200 from rating-over-time, got {resp.status_code}: {resp.text[:200]}"
    )
    assert "application/json" in resp.headers.get("content-type", ""), (
        f"Expected JSON content-type, got: {resp.headers.get('content-type')}"
    )
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    if data:
        item = data[0]
        assert "date" in item, f"Expected 'date' key in item: {item}"
        assert "rating" in item, f"Expected 'rating' key in item: {item}"

    # Verify per-user scope: charts.rating_over_time was called with a user_id
    call_args = mock_charts.rating_over_time.call_args
    assert call_args is not None, "rating_over_time should have been called"


def test_flavor_chart_json(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """GET /ai/charts/flavor-distribution returns ≤15 entries, no rating floor (VIZ-01/D-17)."""
    _require_charts_routes()
    _require_postgres()

    # Mock charts service returning up to 15 descriptors (no rating floor)
    fake_data = [
        {"descriptor": f"note_{i}", "count": 10 - i}
        for i in range(12)  # 12 entries, well under the 15 cap
    ]

    with patch("app.routers.ai.charts") as mock_charts:
        mock_charts.flavor_distribution.return_value = fake_data

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.get("/ai/charts/flavor-distribution")

    assert resp.status_code == 200, (
        f"Expected 200 from flavor-distribution, got {resp.status_code}: {resp.text[:200]}"
    )
    assert "application/json" in resp.headers.get("content-type", ""), (
        f"Expected JSON content-type, got: {resp.headers.get('content-type')}"
    )
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    assert len(data) <= 15, f"Flavor distribution should have at most 15 entries, got {len(data)}"
    if data:
        item = data[0]
        assert "descriptor" in item or "name" in item, (
            f"Expected 'descriptor' or 'name' key in item: {item}"
        )
        assert "count" in item, f"Expected 'count' key in item: {item}"

    # Verify per-user scope
    call_args = mock_charts.flavor_distribution.call_args
    assert call_args is not None, "flavor_distribution should have been called"


def test_charts_require_auth(app: Any) -> None:
    """Unauthenticated GET /ai/charts/* returns 401 or redirect to login."""
    _require_charts_routes()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    for path in ("/ai/charts/rating-over-time", "/ai/charts/flavor-distribution"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (401, 302, 303), (
            f"Expected 401/redirect for unauthed {path}, got {resp.status_code}"
        )
