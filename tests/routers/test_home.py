"""Router smoke tests for plan 06-02 — the analytics home router (app/routers/home.py).

Covers:
- GET / returns 200 for an authenticated user (shell render)
- GET / returns 401 for an unauthenticated request (require_user gate)
- GET /home/cards/recent-brews returns correct cache headers for HTMX requests
- GET /home/cards/unrated-coffees returns correct cache headers for HTMX requests
- GET /home/cards/unrated-coffees returns 401 for unauthenticated request
- Cold-start gate branch: below-gate user sees progress meter
- Phase 7 AI-slot placeholder present and no live AI trigger

Real Postgres + brew_sessions table required; skip gates mirror
tests/services/test_analytics.py and tests/routers/test_brew_router.py.
An authed TestClient is built from the parent-conftest ``seeded_regular_user``
fixture (session cookie + CSRF pair via _prime_csrf). Seed helpers reuse the
``_seed_analytics_scenario`` helper from tests/services/test_analytics.py.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# Skip gates                                                                   #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 6 router test needs the DB")


def _require_analytics_tables() -> None:
    """Skip if the brew_sessions table is not present."""
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.brew_sessions')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("brew_sessions table not present — migration not applied")


# --------------------------------------------------------------------------- #
# Auth helpers                                                                 #
# --------------------------------------------------------------------------- #


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real signed csrftoken; wire it onto the client.

    The home route requires auth; the session cookie must be set BEFORE calling
    this. Returns the minted token string.
    """
    from fastapi.testclient import TestClient  # noqa: F401 — import for type clarity

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
# Seeding helpers + clean fixture                                              #
# --------------------------------------------------------------------------- #

_ANALYTICS_PREFIX = "hometest"


def _seed_cold_start_user(db: Any, *, username: str) -> int:
    """Seed a below-gate user: 0 sessions (well below threshold of 3 + 5).

    Returns the user_id.
    """
    from app.models.user import User

    user = User(
        username=username,
        password_hash="x" * 16,
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.commit()
    return user.id


@pytest.fixture
def clean_home_router() -> Iterator[None]:
    """Wipe test rows seeded by this module before AND after each test."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM bags WHERE coffee_id IN (SELECT id FROM coffees WHERE name LIKE 'analyticstest-%')"))
            conn.execute(text("DELETE FROM flavor_notes WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM roasters WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM recipes WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM equipment WHERE model = 'V60'"))
            conn.execute(text("DELETE FROM users WHERE username LIKE 'hometest-%'"))
            conn.execute(text("DELETE FROM users WHERE username LIKE 'analyticstest-%'"))

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_home_shell_authenticated(app: Any, seeded_regular_user: dict, clean_home_router: None) -> None:
    """GET / with a valid session returns 200 and the home page shell."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/")
    assert resp.status_code == 200
    # Both "Home" (h1) and "Snobbery" (from base.html title/nav) should be present
    assert "Home" in resp.text
    assert "Snobbery" in resp.text


def test_home_unauthenticated_returns_401(app: Any, clean_home_router: None) -> None:
    """GET / without a session returns 401 (require_user gate — T-06-04)."""
    _require_postgres()
    _require_analytics_tables()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 401


def test_recent_brews_fragment_headers(app: Any, seeded_regular_user: dict, clean_home_router: None) -> None:
    """GET /home/cards/recent-brews with HX-Request returns cache control headers."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/recent-brews", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")


def test_unrated_coffees_fragment_headers(app: Any, seeded_regular_user: dict, clean_home_router: None) -> None:
    """GET /home/cards/unrated-coffees with HX-Request returns cache control headers."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/unrated-coffees", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")


def test_unrated_coffees_fragment_requires_auth(app: Any, clean_home_router: None) -> None:
    """GET /home/cards/unrated-coffees without session returns 401 (T-06-04)."""
    _require_postgres()
    _require_analytics_tables()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/home/cards/unrated-coffees", follow_redirects=False)
    assert resp.status_code == 401


def test_cold_start_branch_renders_meter(app: Any, seeded_regular_user: dict, clean_home_router: None) -> None:
    """A user with 0 sessions sees the cold-start progress meter (gate-closed branch)."""
    _require_postgres()
    _require_analytics_tables()

    # seeded_regular_user has no brew sessions; cold-start gate is not cleared.
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Build your taste profile." in resp.text
    assert 'role="progressbar"' in resp.text


def test_ai_slot_placeholder_present(app: Any, seeded_regular_user: dict, clean_home_router: None) -> None:
    """Gate-open user renders the aggregate slots; no live AI trigger (T-06-12).

    Jinja2 comments ({# ... #}) are stripped at render time, so we verify the
    Phase 7 slot comment in the TEMPLATE SOURCE FILE (which the Task 2 probe
    already verifies). Here we assert two things via the HTTP response:
    1. The gate-open branch renders (aggregate slot headings visible).
    2. No live hx-get="/home/cards/ai-recommendation" hx-trigger="revealed" div
       was emitted in the rendered HTML (the endpoint does not exist in Phase 6).
    """
    _require_postgres()
    _require_analytics_tables()

    # Import and reuse the gate-cleared fixture from Plan 06-01 tests
    from tests.services.test_analytics import _seed_analytics_scenario
    from app.db import SessionLocal

    uid: int
    with SessionLocal() as db:
        uid, _coffee3_id, _archived_id = _seed_analytics_scenario(
            db, username="analyticstest-hometest-gate"
        )

    # Build an authed client for this seeded user (not seeded_regular_user)
    from app.services.sessions import regenerate_session
    from app.signing import sign_session_id
    import asyncio
    from app.main import async_session_factory

    async def _make_session() -> str:
        async with async_session_factory() as db:
            session_id = await regenerate_session(db, None, uid)
            return sign_session_id(session_id)

    signed = asyncio.run(_make_session())

    client = _authed_client(app, signed)
    resp = client.get("/")
    assert resp.status_code == 200

    body = resp.text

    # Gate-open branch: at least one aggregate card heading should appear
    assert "Top Coffees" in body

    # No live AI trigger in rendered HTML (Jinja comment is stripped at render time;
    # the slot exists only as a {# ... #} comment in the template source)
    assert 'hx-get="/home/cards/ai-recommendation" hx-trigger="revealed"' not in body

    # Verify the Phase 7 slot comment exists in the template source file
    import pathlib
    template_path = pathlib.Path("app/templates/pages/home.html")
    assert template_path.exists(), "home.html template not found"
    source = template_path.read_text(encoding="utf-8")
    assert "Phase 7: AI recommendation card slot" in source, (
        "Phase 7 AI slot placeholder comment missing from home.html"
    )
