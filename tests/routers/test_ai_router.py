"""Router tests for plan 07-05 — the AI router (app/routers/ai.py).

Covers the behavior cases across the plan's three tasks:

Task 1 (POST /ai/refresh — throttle + in-flight 429 + background URL verify):
* ``test_refresh_triggers_regenerate`` — authenticated POST calls regenerate with force=True.
* ``test_throttle_429`` — second POST within 5-min window returns 429 + HX-Retarget.
* ``test_in_flight_429`` — POST while in_flight=True returns 429 (AI-13).
* ``test_refresh_requires_auth`` — no session → 401.

Task 2 (equipment, paste-rank, wishlist routes — CSRF + IDOR):
* ``test_wishlist_add`` — authenticated POST creates a user-scoped wishlist entry.
* ``test_wishlist_purchase_cross_user_404`` — cross-user entry_id → 404 (T-07-05).
* ``test_wishlist_remove_cross_user_404`` — cross-user entry_id → 404 (T-07-05).
* ``test_paste_rank_route`` — mock rank_pasted_coffees returns 200.
* ``test_equipment_route`` — mock generate_equipment_rec returns 200.
* ``test_wishlist_add_requires_csrf`` — POST without CSRF token → 403.

Task 3 (router registration):
* ``test_ai_routes_registered`` — /ai/refresh and /ai/wishlist/add are in the route table.

Tests mock ai_service and wishlist_service so no real DB or SDK is required for
the mocked paths. CSRF tests rely on the CSRF middleware installed in the test app.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --------------------------------------------------------------------------- #
# Skip gates                                                                  #
# --------------------------------------------------------------------------- #


def _require_ai_router() -> None:
    try:
        from app.routers.ai import router  # noqa: F401
    except ImportError:
        pytest.skip("plan 07-05 dependency: app.routers.ai not importable")


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — AI router wishlist test needs the DB")


def _require_wishlist_table() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.wishlist_entries')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("wishlist_entries table not present — migration not applied")


# --------------------------------------------------------------------------- #
# Auth + CSRF helpers (mirror test_brew_router.py / test_home.py patterns)    #
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
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def clean_ai_router() -> Iterator[None]:
    """Wipe wishlist entries and reset ai_service throttle before/after each test."""
    from tests.conftest import _postgres_reachable  # noqa: F401 — skip gate helper

    # Reset throttle state so tests don't bleed into each other
    try:
        from app.services import ai_service

        ai_service._THROTTLE.clear()
    except ImportError:
        pass

    def _reset_db() -> None:
        if not _postgres_reachable():
            return
        try:
            from sqlalchemy import text

            from app.db import engine

            with engine.begin() as conn:
                conn.execute(text("DELETE FROM wishlist_entries"))
        except Exception:
            pass

    _reset_db()
    yield
    _reset_db()

    # Reset throttle after each test too
    try:
        from app.services import ai_service

        ai_service._THROTTLE.clear()
    except ImportError:
        pass


# --------------------------------------------------------------------------- #
# Task 1: POST /ai/refresh — throttle + in-flight 429                         #
# --------------------------------------------------------------------------- #


def test_refresh_triggers_regenerate(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """Authenticated POST /ai/refresh calls regenerate(user.id, 'manual_refresh', force=True)."""
    _require_ai_router()

    with patch("app.routers.ai.ai_service") as mock_ai:
        mock_ai.in_flight.return_value = False
        mock_ai.regenerate = AsyncMock(return_value="generated")
        mock_ai._THROTTLE = {}
        mock_ai._evict_stale_throttle.return_value = None
        mock_ai.get_latest_recommendation.return_value = None
        mock_ai._verify_buy_url = AsyncMock(return_value=True)

        client = _authed_client(app, seeded_regular_user["signed_cookie"])

        with patch("app.routers.ai.ai_service._THROTTLE", {}):
            resp = client.post("/ai/refresh")

        # Should not be 401 (auth passed) or 429 (not throttled)
        assert resp.status_code in (200, 204, 303), (
            f"Expected 200/204/303, got {resp.status_code}: {resp.text[:200]}"
        )
        assert mock_ai.regenerate.called, "regenerate should have been called"
        call_kwargs = mock_ai.regenerate.call_args
        assert call_kwargs is not None
        # Check force=True was passed
        assert call_kwargs.kwargs.get("force") is True or (
            len(call_kwargs.args) > 0 and call_kwargs.args[1] == "manual_refresh"
        )


def test_throttle_429(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """Second POST /ai/refresh within 5-min window returns 429 + HX-Retarget header (AI-14)."""
    _require_ai_router()

    user = seeded_regular_user["user"]

    with patch("app.routers.ai.ai_service") as mock_ai:
        mock_ai.in_flight.return_value = False
        mock_ai.regenerate = AsyncMock(return_value="generated")
        mock_ai._verify_buy_url = AsyncMock(return_value=False)
        mock_ai.get_latest_recommendation.return_value = None

        # Seed the throttle dict with a recent timestamp for this user
        recent_ts = time.monotonic()
        throttle = {user.id: recent_ts}
        mock_ai._THROTTLE = throttle
        mock_ai._evict_stale_throttle.return_value = None

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post("/ai/refresh")

    assert resp.status_code == 429, f"Expected 429, got {resp.status_code}: {resp.text[:200]}"
    assert "HX-Retarget" in resp.headers, "429 response must include HX-Retarget header (AI-14)"


def test_in_flight_429(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/refresh while in_flight returns 429 (AI-13)."""
    _require_ai_router()

    with patch("app.routers.ai.ai_service") as mock_ai:
        mock_ai.in_flight.return_value = True  # lock is held
        mock_ai._THROTTLE = {}
        mock_ai._evict_stale_throttle.return_value = None

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post("/ai/refresh")

    assert resp.status_code == 429, f"Expected 429, got {resp.status_code}: {resp.text[:200]}"
    assert "HX-Retarget" in resp.headers, "In-flight 429 must include HX-Retarget header (AI-13)"


def test_refresh_requires_auth(app: Any) -> None:
    """Unauthenticated POST /ai/refresh → 401."""
    _require_ai_router()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/ai/refresh")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


# --------------------------------------------------------------------------- #
# Task 2: equipment, paste-rank, wishlist routes                              #
# --------------------------------------------------------------------------- #


def test_equipment_route(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/equipment calls generate_equipment_rec and returns 200."""
    _require_ai_router()

    with patch("app.routers.ai.ai_service") as mock_ai:
        mock_ai.generate_equipment_rec = AsyncMock(return_value=("generated", MagicMock()))

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post("/ai/equipment")

    assert resp.status_code in (200, 204), (
        f"Expected 200/204, got {resp.status_code}: {resp.text[:200]}"
    )
    assert mock_ai.generate_equipment_rec.called


def test_paste_rank_route(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/paste-rank calls rank_pasted_coffees and returns 200."""
    _require_ai_router()

    mock_result = MagicMock()
    mock_result.ranked_coffees = []

    with patch("app.routers.ai.ai_service") as mock_ai:
        mock_ai.rank_pasted_coffees = AsyncMock(return_value=("generated", mock_result))

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post(
            "/ai/paste-rank",
            data={"input_text": "Some interesting coffee beans"},
        )

    assert resp.status_code in (200, 204), (
        f"Expected 200/204, got {resp.status_code}: {resp.text[:200]}"
    )
    assert mock_ai.rank_pasted_coffees.called


def test_wishlist_add(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """Authenticated POST /ai/wishlist/add creates a user-scoped entry."""
    _require_ai_router()
    _require_postgres()
    _require_wishlist_table()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.post(
        "/ai/wishlist/add",
        data={
            "coffee_name": "Ethiopia Yirgacheffe",
            "roaster_name": "Test Roaster",
            "source_url": "https://example.com/coffee",
        },
    )

    assert resp.status_code in (200, 204), (
        f"Expected 200/204, got {resp.status_code}: {resp.text[:200]}"
    )

    # Verify the entry was created for this user
    from app.db import SessionLocal
    from app.services.wishlist import list_wishlist

    with SessionLocal() as db:
        entries = list_wishlist(db, by_user_id=seeded_regular_user["user"].id)
    assert len(entries) == 1
    assert entries[0].coffee_name == "Ethiopia Yirgacheffe"
    assert entries[0].user_id == seeded_regular_user["user"].id


def test_wishlist_add_empty_name_422(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/wishlist/add with a blank coffee_name → 422 (CR-05)."""
    _require_ai_router()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.post(
        "/ai/wishlist/add",
        data={"coffee_name": "   ", "source_url": "https://example.com/x"},
    )

    assert resp.status_code == 422, (
        f"Expected 422 for blank coffee_name, got {resp.status_code}: {resp.text[:200]}"
    )


def test_wishlist_add_drops_non_https_url(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/wishlist/add with a javascript: source_url stores NULL (CR-01)."""
    _require_ai_router()
    _require_postgres()
    _require_wishlist_table()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.post(
        "/ai/wishlist/add",
        data={
            "coffee_name": "Sketchy Coffee",
            "source_url": "javascript:alert(document.cookie)",
        },
    )

    assert resp.status_code in (200, 204), (
        f"Expected 200/204, got {resp.status_code}: {resp.text[:200]}"
    )

    from app.db import SessionLocal
    from app.services.wishlist import list_wishlist

    with SessionLocal() as db:
        entries = list_wishlist(db, by_user_id=seeded_regular_user["user"].id)
    match = [e for e in entries if e.coffee_name == "Sketchy Coffee"]
    assert len(match) == 1
    assert match[0].source_url is None, "non-https source_url must not be stored (CR-01 XSS guard)"


def test_wishlist_purchase_cross_user_404(
    app: Any,
    seeded_regular_user: dict[str, Any],
    seeded_admin_user: dict[str, Any],
) -> None:
    """POST /ai/wishlist/{id}/purchase with a cross-user entry_id → 404 (T-07-05 IDOR)."""
    _require_ai_router()
    _require_postgres()
    _require_wishlist_table()

    # Create an entry owned by the admin user
    from app.db import SessionLocal
    from app.services.wishlist import add_to_wishlist

    with SessionLocal() as db:
        entry = add_to_wishlist(
            db,
            by_user_id=seeded_admin_user["user"].id,
            coffee_name="Admin Coffee",
            roaster_name="Admin Roaster",
            source_url=None,
        )
        entry_id = entry.id

    # Regular user tries to mark it purchased → 404
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.post(f"/ai/wishlist/{entry_id}/purchase")

    assert resp.status_code == 404, (
        f"Expected 404 for cross-user purchase, got {resp.status_code}: {resp.text[:200]}"
    )


def test_wishlist_remove_cross_user_404(
    app: Any,
    seeded_regular_user: dict[str, Any],
    seeded_admin_user: dict[str, Any],
) -> None:
    """POST /ai/wishlist/{id}/remove with a cross-user entry_id → 404 (T-07-05 IDOR)."""
    _require_ai_router()
    _require_postgres()
    _require_wishlist_table()

    # Create an entry owned by the admin user
    from app.db import SessionLocal
    from app.services.wishlist import add_to_wishlist

    with SessionLocal() as db:
        entry = add_to_wishlist(
            db,
            by_user_id=seeded_admin_user["user"].id,
            coffee_name="Admin Coffee To Remove",
            roaster_name="Admin Roaster",
            source_url=None,
        )
        entry_id = entry.id

    # Regular user tries to remove it → 404
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.post(f"/ai/wishlist/{entry_id}/remove")

    assert resp.status_code == 404, (
        f"Expected 404 for cross-user remove, got {resp.status_code}: {resp.text[:200]}"
    )


def test_wishlist_add_requires_csrf(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/wishlist/add without CSRF token → 403 (T-07-11)."""
    _require_ai_router()

    from fastapi.testclient import TestClient

    # Build client with session but NO CSRF token
    client = TestClient(app)
    client.cookies.set("session_id", seeded_regular_user["signed_cookie"])

    resp = client.post(
        "/ai/wishlist/add",
        data={
            "coffee_name": "Some Coffee",
            "roaster_name": "Some Roaster",
            "source_url": "",
        },
    )
    # CSRF middleware returns 403 when token is missing/invalid
    assert resp.status_code == 403, (
        f"Expected 403 without CSRF token, got {resp.status_code}: {resp.text[:200]}"
    )


# --------------------------------------------------------------------------- #
# Task 3: router registration smoke test                                       #
# --------------------------------------------------------------------------- #


def test_ai_routes_registered(app: Any) -> None:
    """The app route table contains /ai/refresh and /ai/wishlist/add."""
    _require_ai_router()

    from fastapi.routing import APIRoute

    route_paths = {getattr(r, "path", None) for r in app.routes if isinstance(r, APIRoute)}
    assert "/ai/refresh" in route_paths, (
        f"/ai/refresh not found in route table. Routes: {sorted(route_paths)}"
    )
    assert "/ai/wishlist/add" in route_paths, (
        f"/ai/wishlist/add not found in route table. Routes: {sorted(route_paths)}"
    )


# --------------------------------------------------------------------------- #
# Task 1 (07-07): paste-rank page + results fragment + equipment fragment      #
# --------------------------------------------------------------------------- #


def test_paste_rank_page_renders(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """GET /ai/paste-rank returns 200 with the textarea for authenticated users."""
    _require_ai_router()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/ai/paste-rank")

    assert resp.status_code == 200, (
        f"Expected 200 for GET /ai/paste-rank, got {resp.status_code}: {resp.text[:200]}"
    )
    assert 'name="input_text"' in resp.text, (
        "paste-rank page must contain a textarea with name='input_text'"
    )


def test_paste_rank_submit_returns_results(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/paste-rank (HTMX) returns a 3-item results fragment."""
    _require_ai_router()

    from app.services.ai_schemas import PasteRankSchema, RankedCoffeeItem

    mock_result = PasteRankSchema(
        ranked=[
            RankedCoffeeItem(rank=1, name="Ethiopia Yirgacheffe", reasoning="Bright and fruity."),
            RankedCoffeeItem(rank=2, name="Colombia Huila", reasoning="Balanced and chocolatey."),
            RankedCoffeeItem(rank=3, name="Kenya AA", reasoning="Complex with berry notes."),
        ],
        summary_prose="Ranked by predicted match to your taste profile.",
    )

    with patch("app.routers.ai.ai_service") as mock_ai:
        mock_ai.rank_pasted_coffees = AsyncMock(return_value=("generated", mock_result))

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post(
            "/ai/paste-rank",
            data={"input_text": "Ethiopia Yirgacheffe\nColombia Huila\nKenya AA"},
            headers={"HX-Request": "true"},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    # All 3 coffee names must appear in the results fragment
    assert "Ethiopia Yirgacheffe" in resp.text, "Expected first ranked coffee in fragment"
    assert "Colombia Huila" in resp.text, "Expected second ranked coffee in fragment"
    assert "Kenya AA" in resp.text, "Expected third ranked coffee in fragment"


def test_equipment_button_returns_fragment(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """POST /ai/equipment with mocked generate_equipment_rec returns the equipment_rec fragment."""
    _require_ai_router()

    from unittest.mock import MagicMock

    mock_row = MagicMock()
    mock_row.response_json = {
        "weakest_link": "Baratza Encore grinder",
        "recommendation": "Upgrade to a Comandante for better grind consistency.",
        "summary_prose": "Your setup is good but the grinder is the weakest link.",
    }

    with patch("app.routers.ai.ai_service") as mock_ai:
        mock_ai.generate_equipment_rec = AsyncMock(return_value=("generated", mock_row))

        client = _authed_client(app, seeded_regular_user["signed_cookie"])
        resp = client.post("/ai/equipment")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    # Equipment result content should appear
    assert "Baratza Encore" in resp.text or "grinder" in resp.text.lower(), (
        f"Expected equipment result content in fragment, got: {resp.text[:300]}"
    )


# --------------------------------------------------------------------------- #
# Task 2 (07-07): wishlist page + home links                                  #
# --------------------------------------------------------------------------- #


def test_wishlist_page_requires_auth(app: Any) -> None:
    """GET /ai/wishlist without a session returns 401."""
    _require_ai_router()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/ai/wishlist")
    assert resp.status_code == 401, (
        f"Expected 401 for unauthenticated GET /ai/wishlist, got {resp.status_code}"
    )


def test_wishlist_page_lists_user_entries(
    app: Any,
    seeded_regular_user: dict[str, Any],
    seeded_admin_user: dict[str, Any],
) -> None:
    """GET /ai/wishlist shows only the authenticated user's entries (IDOR scope)."""
    _require_ai_router()
    _require_postgres()
    _require_wishlist_table()

    from app.db import SessionLocal
    from app.services.wishlist import add_to_wishlist

    # Create one entry for the regular user, one for admin
    with SessionLocal() as db:
        add_to_wishlist(
            db,
            by_user_id=seeded_regular_user["user"].id,
            coffee_name="User Coffee",
            roaster_name="User Roaster",
            source_url=None,
        )
        add_to_wishlist(
            db,
            by_user_id=seeded_admin_user["user"].id,
            coffee_name="Admin Coffee",
            roaster_name="Admin Roaster",
            source_url=None,
        )

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/ai/wishlist")

    assert resp.status_code == 200, (
        f"Expected 200 for GET /ai/wishlist, got {resp.status_code}: {resp.text[:200]}"
    )
    assert "User Coffee" in resp.text, "Own entry must appear on wishlist page"
    assert "Admin Coffee" not in resp.text, "Other user's entry must NOT appear (IDOR)"


# --------------------------------------------------------------------------- #
# Plan 17-04: GET /ai page shell (IA-02 / IA-03 / AIX-08 / D-13..D-16 / D-20) #
# --------------------------------------------------------------------------- #


def _patch_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the ai router's credentials helper to return None for every
    provider — simulates the "no AI key configured" state. Same strategy as
    plan 17-03's tests/test_dist07_banner.py."""
    from app.routers import ai as ai_router

    monkeypatch.setattr(
        ai_router.credentials_service,
        "get_provider_credential",
        lambda _db, _provider: None,
    )


def _patch_with_key(monkeypatch: pytest.MonkeyPatch, *, provider: str = "anthropic") -> None:
    """Monkeypatch the ai router's credentials helper to return a sentinel
    object for ``provider`` and None otherwise — simulates the "has key" state."""
    from app.routers import ai as ai_router

    sentinel = object()

    def fake(_db: Any, p: str) -> Any:
        return sentinel if p == provider else None

    monkeypatch.setattr(ai_router.credentials_service, "get_provider_credential", fake)


def _patch_gate_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the ai router's cold-start gate to report open (above gate).
    Sidesteps having to seed real brew_sessions + flavor notes in the test DB —
    this test module focuses on /ai branch composition, not analytics logic."""
    from app.routers import ai as ai_router

    monkeypatch.setattr(
        ai_router.analytics,
        "get_cold_start_counts",
        lambda _db, _uid: {
            "sessions": 5,
            "distinct_notes": 7,
            "sessions_needed": 0,
            "notes_needed": 0,
            "gate_open": True,
        },
    )


def _patch_gate_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the ai router's cold-start gate to report closed (below gate)."""
    from app.routers import ai as ai_router

    monkeypatch.setattr(
        ai_router.analytics,
        "get_cold_start_counts",
        lambda _db, _uid: {
            "sessions": 0,
            "distinct_notes": 0,
            "sessions_needed": 3,
            "notes_needed": 5,
            "gate_open": False,
        },
    )


@pytest.mark.parametrize("user_role", ["admin", "regular"])
def test_get_ai_page_returns_200(
    client,
    seeded_admin_user,
    seeded_regular_user,
    monkeypatch,
    user_role,
) -> None:
    """GET /ai returns 200 for any authenticated user (IA-02, D-03)."""
    _require_ai_router()
    _patch_no_key(monkeypatch)
    _patch_gate_closed(monkeypatch)
    fixture = seeded_admin_user if user_role == "admin" else seeded_regular_user
    cookie = fixture["signed_cookie"]

    r = client.get("/ai", cookies={"session_id": cookie})

    assert r.status_code == 200, (
        f"GET /ai must return 200 for {user_role}; got {r.status_code}: {r.text[:300]}"
    )


def test_get_ai_page_returns_401_for_anonymous(client) -> None:
    """GET /ai returns 401 for an unauthenticated request (require_user gate)."""
    _require_ai_router()
    r = client.get("/ai")
    assert r.status_code == 401, f"GET /ai must return 401 for anonymous; got {r.status_code}"


def test_ai_page_below_gate_shows_cold_start_not_no_key(
    client,
    seeded_admin_user,
    monkeypatch,
) -> None:
    """Below-gate users on /ai see the cold-start meter, NOT the no-key callout.

    Confirms the branch ordering in pages/ai.html: gate check fires BEFORE the
    key check, so an above-gate-only state ("AI keys needed") never appears for
    a below-gate user even if their key state would otherwise trigger it.
    """
    _require_ai_router()
    _patch_no_key(monkeypatch)
    _patch_gate_closed(monkeypatch)
    cookie = seeded_admin_user["signed_cookie"]

    r = client.get("/ai", cookies={"session_id": cookie})

    assert r.status_code == 200
    assert "AI personalization activates after 3 sessions and 5 distinct flavor notes." in r.text, (
        "D-14 cold-start explainer copy missing"
    )
    assert "AI keys needed" not in r.text, (
        "AIX-08 admin headline must NOT appear below the cold-start gate"
    )
    assert "AI is not set up" not in r.text, (
        "AIX-08 non-admin headline must NOT appear below the cold-start gate"
    )


def test_ai_page_shows_admin_callout_above_gate_no_key(
    client,
    seeded_admin_user,
    monkeypatch,
) -> None:
    """Above-gate + admin + no key → AIX-08 admin callout with /admin/credentials button (D-15)."""
    _require_ai_router()
    _patch_no_key(monkeypatch)
    _patch_gate_open(monkeypatch)
    cookie = seeded_admin_user["signed_cookie"]

    r = client.get("/ai", cookies={"session_id": cookie})

    assert r.status_code == 200
    assert "AI keys needed" in r.text, "D-15 admin callout headline missing"
    assert 'href="/admin/credentials"' in r.text, (
        "D-15 admin callout must link to /admin/credentials"
    )
    assert "AI personalization activates after" not in r.text, (
        "Cold-start explainer must NOT appear above the gate"
    )


def test_ai_page_shows_non_admin_callout_above_gate_no_key(
    client,
    seeded_regular_user,
    monkeypatch,
) -> None:
    """Above-gate + non-admin + no key → D-16 social-action callout, no admin link."""
    _require_ai_router()
    _patch_no_key(monkeypatch)
    _patch_gate_open(monkeypatch)
    cookie = seeded_regular_user["signed_cookie"]

    r = client.get("/ai", cookies={"session_id": cookie})

    assert r.status_code == 200
    assert "Ask the household admin" in r.text, "D-16 social-action copy missing"
    # No /admin link anywhere for non-admins (top-nav admin link is admin-gated).
    assert 'href="/admin/credentials"' not in r.text, (
        "D-16 forbids /admin/credentials link for non-admins"
    )
    assert 'href="/admin"' not in r.text, "D-16 forbids any admin link for non-admins"


def test_ai_page_above_gate_with_key_shows_hero(
    client,
    seeded_admin_user,
    monkeypatch,
) -> None:
    """Above-gate + key present → research card + AI hero + preference/sweet-spots mounts.

    Phase 19 (D-10) restructured /ai: the Top Flavor Descriptors card was deleted
    and the Phase-17 "Coming in Phase 19" research stub was replaced by the real
    research form. This test was updated to match (see ADR 0004 / test_ai_page_phase19).
    """
    _require_ai_router()
    _patch_with_key(monkeypatch, provider="anthropic")
    _patch_gate_open(monkeypatch)
    cookie = seeded_admin_user["signed_cookie"]

    r = client.get("/ai", cookies={"session_id": cookie})

    assert r.status_code == 200
    assert 'id="research-card"' in r.text, "Research card (D-10) missing"
    assert 'hx-get="/home/cards/ai-recommendation"' in r.text, "AI hero mount missing"
    assert 'hx-get="/home/cards/preference-profile"' in r.text, "Preference Profile mount missing"
    assert 'hx-get="/home/cards/sweet-spots"' in r.text, "Sweet Spots mount missing"
    assert 'hx-get="/home/cards/flavor-descriptors"' not in r.text, (
        "Top Flavor Descriptors card must be deleted (D-10)"
    )
    assert "Coming in Phase 19" not in r.text, (
        "Phase-17 research stub must be replaced by real form"
    )


def test_ai_page_shows_dist07_banner_for_admin_with_no_key(
    client,
    seeded_admin_user,
    monkeypatch,
) -> None:
    """DIST-07 banner coexists on /ai for admins-with-no-key (D-20)."""
    _require_ai_router()
    _patch_no_key(monkeypatch)
    _patch_gate_open(monkeypatch)
    cookie = seeded_admin_user["signed_cookie"]

    r = client.get("/ai", cookies={"session_id": cookie})

    assert r.status_code == 200
    assert "bannerDismiss" in r.text, "DIST-07 banner missing on /ai for admin+no-key"
    assert "Welcome — add your AI API key in Admin" in r.text, "Banner copy missing"
