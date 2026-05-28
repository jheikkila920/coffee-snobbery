"""Router tests for plan 19-05 Task 2 — POST /ai/improve-brew/{session_id} + GET /ai/coach.

Covers the behavior cases from the plan's AIX-12/D-12 requirements:

* ``test_improve_brew_cross_user_404`` — session belonging to another user → 404 (IDOR)
* ``test_improve_brew_quota_exhausted_429`` — quota zero → 429
* ``test_improve_brew_sse_on_success`` — valid session → EventSourceResponse with X-Accel-Buffering
* ``test_coach_picker_lists_own_sessions`` — GET /ai/coach returns only requesting user's sessions
* ``test_improve_brew_requires_auth`` — unauthenticated → 401/redirect
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# --------------------------------------------------------------------------- #
# Skip gates                                                                  #
# --------------------------------------------------------------------------- #


def _require_improve_route() -> None:
    try:
        from app.routers.ai import router  # noqa: F401

        route_paths = [r.path for r in router.routes]
        if not any("improve" in p for p in route_paths):
            pytest.skip("plan 19-05 dependency: /ai/improve-brew route not yet added to ai router")
    except ImportError:
        pytest.skip("plan 19-05 dependency: app.routers.ai not importable")


def _require_coach_route() -> None:
    try:
        from app.routers.ai import router  # noqa: F401

        route_paths = [r.path for r in router.routes]
        if not any("coach" in p for p in route_paths):
            pytest.skip("plan 19-05 dependency: /ai/coach route not yet added to ai router")
    except ImportError:
        pytest.skip("plan 19-05 dependency: app.routers.ai not importable")


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — improve-brew router test needs the DB")


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


def test_improve_brew_cross_user_404(
    app: Any,
    seeded_regular_user: dict[str, Any],
) -> None:
    """POST /ai/improve-brew/{session_id} with a cross-user session returns 404 (IDOR).

    D-12 / T-19-12: session loaded by_user_id → existence non-leak (404, not 403).
    """
    _require_improve_route()
    _require_postgres()

    # generate_brew_improvement returns event:error with "not found" when session is None
    async def _idor_gen(*args, **kwargs):
        from sse_starlette.sse import ServerSentEvent

        # The service emits event:error when session not found, but the ROUTE
        # should return 404 before even calling the generator
        yield ServerSentEvent(data="Brew session not found.", event="error")

    with (
        patch("app.routers.ai.brew_sessions_service") as mock_sessions,
        patch("app.routers.ai.ai_quota") as mock_quota,
        patch("app.routers.ai.ai_service"),
    ):
        # Session not found for this user — simulates cross-user IDOR
        mock_sessions.get_brew_session.return_value = None
        mock_quota.remaining.return_value = 10
        mock_quota.get_quota_cap.return_value = 20

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        # Use a session_id that belongs to another user
        resp = client.post("/ai/improve-brew/99999")

    assert resp.status_code == 404, (
        f"Expected 404 for cross-user session (IDOR), got {resp.status_code}: {resp.text[:200]}"
    )


def test_improve_brew_quota_exhausted_429(
    app: Any,
    seeded_regular_user: dict[str, Any],
) -> None:
    """POST /ai/improve-brew/{session_id} with quota=0 returns 429."""
    _require_improve_route()
    _require_postgres()

    fake_session = MagicMock()
    fake_session.id = 1
    fake_session.coffee_id = 1
    fake_session.user_id = seeded_regular_user.get("id", 1)

    with (
        patch("app.routers.ai.brew_sessions_service") as mock_sessions,
        patch("app.routers.ai.ai_quota") as mock_quota,
    ):
        mock_sessions.get_brew_session.return_value = fake_session
        mock_quota.remaining.return_value = 0
        mock_quota.get_quota_reset_time.return_value = None
        mock_quota.get_quota_cap.return_value = 20

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post("/ai/improve-brew/1")

    assert resp.status_code == 429, (
        f"Expected 429 for quota-exhausted improve-brew, got {resp.status_code}: {resp.text[:200]}"
    )


def test_improve_brew_sse_on_success(
    app: Any,
    seeded_regular_user: dict[str, Any],
) -> None:
    """POST /ai/improve-brew/{session_id} with a valid session returns SSE response."""
    _require_improve_route()
    _require_postgres()

    fake_session = MagicMock()
    fake_session.id = 1
    fake_session.coffee_id = 1

    async def _improve_gen():
        from sse_starlette.sse import ServerSentEvent

        yield ServerSentEvent(data="Brew analysis complete.", event="complete")

    with (
        patch("app.routers.ai.brew_sessions_service") as mock_sessions,
        patch("app.routers.ai.ai_quota") as mock_quota,
        patch("app.routers.ai.ai_service") as mock_ai_service,
    ):
        mock_sessions.get_brew_session.return_value = fake_session
        mock_quota.remaining.return_value = 10
        mock_quota.get_quota_cap.return_value = 20
        # generate_brew_improvement is an async generator function
        mock_ai_service.generate_brew_improvement.return_value = _improve_gen()

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post("/ai/improve-brew/1")

    # Should start SSE stream successfully
    assert resp.status_code in (200, 204), (
        f"Expected 200/204 for improve-brew SSE, got {resp.status_code}: {resp.text[:200]}"
    )
    content_type = resp.headers.get("content-type", "")
    if "event-stream" in content_type:
        assert resp.headers.get("X-Accel-Buffering") == "no", (
            "SSE response must carry X-Accel-Buffering: no"
        )


def test_coach_picker_lists_own_sessions(
    app: Any,
    seeded_regular_user: dict[str, Any],
) -> None:
    """GET /ai/coach returns a fragment listing only the requesting user's sessions (D-12)."""
    _require_coach_route()
    _require_postgres()

    # Create fake sessions for the user
    fake_sessions = []
    for i in range(3):
        s = MagicMock()
        s.id = i + 1
        s.coffee_id = 1
        s.brewed_at = MagicMock()
        s.brewed_at.strftime.return_value = "2026-01-01"
        s.rating = 4.0
        # Attach a fake coffee
        s.coffee = MagicMock()
        s.coffee.name = f"Coffee {i + 1}"
        fake_sessions.append(s)

    with patch("app.routers.ai.brew_sessions_service") as mock_sessions:
        mock_sessions.list_brew_sessions.return_value = fake_sessions

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.get("/ai/coach")

    assert resp.status_code == 200, (
        f"Expected 200 from /ai/coach, got {resp.status_code}: {resp.text[:200]}"
    )
    # The coach picker should only show the requesting user's sessions
    # (by_user_id kwarg was used in list_brew_sessions call)
    call_kwargs = mock_sessions.list_brew_sessions.call_args
    assert call_kwargs is not None, "list_brew_sessions should have been called"
    # Verify by_user_id was passed (not hardcoded)
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    assert "by_user_id" in kwargs or len(call_kwargs.args) >= 2, (
        "Coach picker must call list_brew_sessions with by_user_id"
    )


def test_improve_brew_requires_auth(app: Any) -> None:
    """Unauthenticated POST /ai/improve-brew/{session_id} returns 401 or redirect."""
    _require_improve_route()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/ai/improve-brew/1", follow_redirects=False)
    assert resp.status_code in (401, 302, 303), (
        f"Expected 401/redirect for unauthed improve-brew, got {resp.status_code}"
    )
