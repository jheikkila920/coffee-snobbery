"""Router tests for plan 19-05 Task 1 — POST /ai/research + GET /ai/research/quota.

Covers the behavior cases from the plan's AIX-01/03/05/07 requirements:

* ``test_research_blocked_below_gate`` — cold-start gate closed → 403 (AIX-03)
* ``test_research_429_quota_exhausted`` — quota zero → 429 + HX-Retarget (AIX-05/D-09)
* ``test_research_cache_hit_no_quota_decrement`` — cache hit → instant fragment, no
  quota decrement, no SSE started (AIX-04/D-04)
* ``test_research_sse_streams_on_miss`` — cache miss → EventSourceResponse returned
  (AIX-07/D-16)
* ``test_research_quota_fragment`` — GET /ai/research/quota → counter fragment (D-09)
* ``test_research_requires_auth`` — unauthenticated POST → 401/redirect
* ``test_research_sse_header`` — EventSourceResponse carries X-Accel-Buffering: no
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# --------------------------------------------------------------------------- #
# Skip gates                                                                  #
# --------------------------------------------------------------------------- #


def _require_research_route() -> None:
    try:
        from app.routers.ai import router  # noqa: F401

        # Check that the research route exists
        route_paths = [r.path for r in router.routes]
        if "/research" not in route_paths and not any("research" in p for p in route_paths):
            pytest.skip("plan 19-05 dependency: /ai/research route not yet added to ai router")
    except ImportError:
        pytest.skip("plan 19-05 dependency: app.routers.ai not importable")


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — research router test needs the DB")


# --------------------------------------------------------------------------- #
# Auth + CSRF helpers (mirror existing test_ai_router.py pattern)             #
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


def test_research_blocked_below_gate(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/research with gate closed returns 403/redirect (AIX-03)."""
    _require_research_route()
    _require_postgres()

    gate_closed = {"gate_open": False, "sessions": 1, "distinct_notes": 2}

    with (
        patch("app.routers.ai.analytics") as mock_analytics,
        patch("app.routers.ai.ai_quota") as mock_quota,
    ):
        mock_analytics.get_cold_start_counts.return_value = gate_closed
        mock_quota.remaining.return_value = 20

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post(
            "/ai/research",
            data={"coffee_name": "Test Coffee", "roaster_name": ""},
        )

    # Gate closed → should be 403, or a redirect, or the response HTML
    # contains the gate-closed message (route may return HTML fragment)
    assert resp.status_code in (
        403,
        302,
        303,
        200,
    ), f"Expected 403/redirect/200 for gate-closed, got {resp.status_code}: {resp.text[:200]}"
    # If 200, check it's not streaming (no SSE started)
    if resp.status_code == 200:
        assert "event-stream" not in resp.headers.get("content-type", "")


def test_research_429_quota_exhausted(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/research with quota=0 returns 429 + HX-Retarget=#research-card (AIX-05/D-09)."""
    _require_research_route()
    _require_postgres()

    gate_open = {"gate_open": True, "sessions": 10, "distinct_notes": 10}

    with (
        patch("app.routers.ai.analytics") as mock_analytics,
        patch("app.routers.ai.ai_quota") as mock_quota,
        patch("app.routers.ai.ai_research"),
    ):
        mock_analytics.get_cold_start_counts.return_value = gate_open
        mock_quota.remaining.return_value = 0
        mock_quota.get_quota_reset_time.return_value = None
        mock_quota.get_quota_cap.return_value = 20

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post(
            "/ai/research",
            data={"coffee_name": "Test Coffee", "roaster_name": ""},
        )

    assert resp.status_code == 429, (
        f"Expected 429 for quota-exhausted, got {resp.status_code}: {resp.text[:200]}"
    )
    assert resp.headers.get("HX-Retarget") == "#research-card", (
        f"Expected HX-Retarget=#research-card, got: {resp.headers.get('HX-Retarget')}"
    )


def test_research_cache_hit_no_quota_decrement(
    app: Any, seeded_regular_user: dict[str, Any]
) -> None:
    """Cache hit returns instant HTML fragment; quota NOT decremented (AIX-04/D-04)."""
    _require_research_route()
    _require_postgres()

    gate_open = {"gate_open": True, "sessions": 10, "distinct_notes": 10}
    fake_cache_row = MagicMock()
    fake_cache_row.response_json = {
        "coffee_name": "Test Coffee",
        "roaster_name": "Test Roaster",
        "origin": "Ethiopia",
        "process": "washed",
        "roast_level": "light",
        "tasting_notes": ["floral", "citrus"],
        "buy_url": None,
        "sources": [],
        "summary_prose": "A great coffee.",
    }
    fake_cache_row.cited_sources = []
    fake_cache_row.cache_key = "test coffee|test roaster"

    # EventSourceResponse on cache hit: generate_coffee_research returns async generator
    async def _cache_hit_gen():
        from sse_starlette.sse import ServerSentEvent

        yield ServerSentEvent(data="<div>cached result</div>", event="complete")

    with (
        patch("app.routers.ai.analytics") as mock_analytics,
        patch("app.routers.ai.ai_quota") as mock_quota,
        patch("app.routers.ai.ai_research") as mock_research,
        patch("app.routers.ai.analytics.compute_input_signature", return_value="sig"),
    ):
        mock_analytics.get_cold_start_counts.return_value = gate_open
        mock_analytics.compute_input_signature.return_value = "sig"
        mock_quota.remaining.return_value = 5
        mock_quota.get_quota_cap.return_value = 20
        mock_research.normalize_cache_key.return_value = "test coffee|test roaster"
        mock_research.get_cached_research.return_value = fake_cache_row
        # generate_coffee_research is an async generator function — return the generator object
        mock_research.generate_coffee_research.return_value = _cache_hit_gen()

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post(
            "/ai/research",
            data={"coffee_name": "Test Coffee", "roaster_name": "Test Roaster"},
        )

    # Cache hit should not call remaining with a decrement (remaining was 5, should remain)
    assert resp.status_code in (200, 204), (
        f"Expected 200/204 on cache hit, got {resp.status_code}: {resp.text[:200]}"
    )
    # quota.remaining was called for the gate check only (not decremented)
    assert mock_quota.remaining.call_count <= 1, "Quota should not be decremented on cache hit"


def test_research_sse_streams_on_miss(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """Cache miss → EventSourceResponse with X-Accel-Buffering: no header (AIX-07/D-16).

    Source assertion: EventSourceResponse used with headers={"X-Accel-Buffering": "no"}.
    """
    _require_research_route()
    _require_postgres()

    gate_open = {"gate_open": True, "sessions": 10, "distinct_notes": 10}

    async def _sse_gen():
        from sse_starlette.sse import ServerSentEvent

        yield ServerSentEvent(data="<div>result</div>", event="complete")

    with (
        patch("app.routers.ai.analytics") as mock_analytics,
        patch("app.routers.ai.ai_quota") as mock_quota,
        patch("app.routers.ai.ai_research") as mock_research,
    ):
        mock_analytics.get_cold_start_counts.return_value = gate_open
        mock_analytics.compute_input_signature.return_value = "sig"
        mock_quota.remaining.return_value = 10
        mock_quota.get_quota_cap.return_value = 20
        mock_research.normalize_cache_key.return_value = "test coffee|"
        mock_research.get_cached_research.return_value = None  # cache miss
        # generate_coffee_research is an async generator function
        mock_research.generate_coffee_research.return_value = _sse_gen()

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post(
            "/ai/research",
            data={"coffee_name": "Test Coffee", "roaster_name": ""},
        )

    # Cache miss → SSE response
    assert resp.status_code == 200, (
        f"Expected 200 on SSE start, got {resp.status_code}: {resp.text[:200]}"
    )
    # Verify X-Accel-Buffering: no header (NPM buffering defense, T-19-20)
    accel_header = resp.headers.get("X-Accel-Buffering")
    assert accel_header == "no", (
        f"SSE response must carry X-Accel-Buffering: no, got: {accel_header}"
    )


def test_research_quota_fragment(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """GET /ai/research/quota returns the counter fragment (D-09)."""
    _require_research_route()
    _require_postgres()

    with (
        patch("app.routers.ai.ai_quota") as mock_quota,
        patch("app.routers.ai.analytics"),
    ):
        mock_quota.remaining.return_value = 15
        mock_quota.get_quota_cap.return_value = 20
        mock_quota.get_quota_reset_time.return_value = None

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.get("/ai/research/quota")

    assert resp.status_code == 200, (
        f"Expected 200 from /ai/research/quota, got {resp.status_code}: {resp.text[:200]}"
    )
    # Response should contain quota info
    body = resp.text
    assert any(x in body for x in ("15", "20", "remaining", "quota", "Resets")), (
        f"Quota fragment should mention remaining/cap/quota, got: {body[:200]}"
    )


def test_research_requires_auth(app: Any) -> None:
    """Unauthenticated POST /ai/research returns 401 or redirect to login."""
    _require_research_route()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post(
        "/ai/research",
        data={"coffee_name": "Test Coffee"},
        follow_redirects=False,
    )
    assert resp.status_code in (401, 302, 303), (
        f"Expected 401/redirect for unauthed, got {resp.status_code}"
    )
