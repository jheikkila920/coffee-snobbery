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


# --------------------------------------------------------------------------- #
# Plan 06-03 tests — aggregate-card fragment endpoints                        #
# --------------------------------------------------------------------------- #

# Routes under test
_AGGREGATE_ROUTES = [
    "/home/cards/top-coffees",
    "/home/cards/preference-profile",
    "/home/cards/flavor-descriptors",
    "/home/cards/roast-freshness",
    "/home/cards/sweet-spots",
]


def _make_authed_client_for_user(app: Any, user_id: int) -> Any:
    """Build a TestClient authed as an arbitrary seeded user (by id).

    Reuses the session-creation pattern from ``test_ai_slot_placeholder_present``.
    """
    import asyncio

    from app.main import async_session_factory
    from app.services.sessions import regenerate_session
    from app.signing import sign_session_id

    async def _make_session() -> str:
        async with async_session_factory() as db:
            session_id = await regenerate_session(db, None, user_id)
            return sign_session_id(session_id)

    signed = asyncio.run(_make_session())
    return _authed_client(app, signed)


def _seed_gate_cleared_no_sweet_spots(db: Any, *, username: str) -> int:
    """Seed a gate-cleared user whose rated sessions span different combos (< 3 per combo).

    Returns user_id.  The user has 3 rated sessions on 3 different coffees, so no
    (origin × process × brewer × recipe) combination reaches the min-3 threshold.
    The gate is open (3 sessions, 5 distinct notes).
    """
    from decimal import Decimal
    from datetime import datetime, timezone

    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.equipment import Equipment
    from app.models.flavor_note import FlavorNote
    from app.models.recipe import Recipe
    from app.models.user import User

    user = User(
        username=username,
        password_hash="x" * 16,
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.flush()
    uid = user.id

    # Create 5 flavor notes so the gate clears
    fn_ids = []
    for i in range(5):
        fn = FlavorNote(name=f"analyticstest-fn-sparse-{i}-{username}", category="fruit")
        db.add(fn)
        db.flush()
        fn_ids.append(fn.id)

    brewer = Equipment(type="brewer", brand="Hario", model="V60")
    db.add(brewer)
    db.flush()

    recipe = Recipe(
        name=f"analyticstest-Recipe-sparse-{username}",
        dose_grams=15,
        water_grams=250,
        water_temp_c=93,
        grind_setting="22",
    )
    db.add(recipe)
    db.flush()

    brew_ts = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)

    # 3 sessions on 3 different coffees (different origins) — no combo reaches min-3
    for i, origin in enumerate(["Ethiopia", "Colombia", "Kenya"]):
        coffee = Coffee(
            name=f"analyticstest-SparseCoffee{i}-{username}",
            origin=origin,
            process="washed",
            roast_level="light",
        )
        db.add(coffee)
        db.flush()

        session = BrewSession(
            user_id=uid,
            coffee_id=coffee.id,
            brewer_id=brewer.id,
            recipe_id=recipe.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=Decimal("4.0"),
            flavor_note_ids_observed=fn_ids,
            brewed_at=brew_ts,
        )
        db.add(session)
        db.flush()

    db.commit()
    return uid


# --- Fragment header tests ---------------------------------------------------


def test_top_coffees_fragment_headers(
    app: Any, seeded_regular_user: dict, clean_home_router: None
) -> None:
    """GET /home/cards/top-coffees returns 200 with no-store + Vary:HX-Request."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/top-coffees", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")


def test_preference_profile_fragment_headers(
    app: Any, seeded_regular_user: dict, clean_home_router: None
) -> None:
    """GET /home/cards/preference-profile returns 200 with cache headers."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/preference-profile", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")


def test_flavor_descriptors_fragment_headers(
    app: Any, seeded_regular_user: dict, clean_home_router: None
) -> None:
    """GET /home/cards/flavor-descriptors returns 200 with cache headers."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/flavor-descriptors", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")


def test_roast_freshness_fragment_headers(
    app: Any, seeded_regular_user: dict, clean_home_router: None
) -> None:
    """GET /home/cards/roast-freshness returns 200 with cache headers."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/roast-freshness", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")


def test_sweet_spots_fragment_headers(
    app: Any, seeded_regular_user: dict, clean_home_router: None
) -> None:
    """GET /home/cards/sweet-spots returns 200 with cache headers."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/sweet-spots", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "HX-Request" in resp.headers.get("vary", "")


# --- Auth gate tests ---------------------------------------------------------


def test_top_coffees_requires_auth(app: Any, clean_home_router: None) -> None:
    """GET /home/cards/top-coffees without session returns 401 (T-06-08)."""
    _require_postgres()
    _require_analytics_tables()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/home/cards/top-coffees", follow_redirects=False)
    assert resp.status_code == 401


def test_sweet_spots_requires_auth(app: Any, clean_home_router: None) -> None:
    """GET /home/cards/sweet-spots without session returns 401 (T-06-08)."""
    _require_postgres()
    _require_analytics_tables()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/home/cards/sweet-spots", follow_redirects=False)
    assert resp.status_code == 401


# --- Sparse hint test --------------------------------------------------------


def test_sweet_spots_sparse_hint(app: Any, clean_home_router: None) -> None:
    """Gate-cleared user with no qualifying combo sees the sparse hint text (D-04)."""
    _require_postgres()
    _require_analytics_tables()

    from app.db import SessionLocal

    with SessionLocal() as db:
        uid = _seed_gate_cleared_no_sweet_spots(
            db, username="hometest-sparse-sweet-spots"
        )

    client = _make_authed_client_for_user(app, uid)
    resp = client.get("/home/cards/sweet-spots", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "Not enough sessions per combination yet (need 3 per match)." in resp.text


# --- All-unrated nudge test (D-05) ------------------------------------------


def test_top_coffees_all_unrated_nudge(app: Any, clean_home_router: None) -> None:
    """Gate-cleared user with zero rated sessions sees the D-05 nudge (T-06-08)."""
    _require_postgres()
    _require_analytics_tables()

    from tests.services.test_analytics import _seed_all_unrated
    from app.db import SessionLocal

    with SessionLocal() as db:
        uid = _seed_all_unrated(db, username="hometest-all-unrated-top")

    client = _make_authed_client_for_user(app, uid)
    resp = client.get("/home/cards/top-coffees", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "Rate some brews to see your top coffees." in resp.text


# --- AI placeholder scope guard (HOME-06) ------------------------------------


def test_sweet_spots_no_ai_placeholder(
    app: Any, seeded_regular_user: dict, clean_home_router: None
) -> None:
    """GET /home/cards/sweet-spots contains no AI coming-soon placeholder (T-06-11)."""
    _require_postgres()
    _require_analytics_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    resp = client.get("/home/cards/sweet-spots", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    body = resp.text
    # The sweet-spots card must not render any AI prose placeholder
    assert "coming soon" not in body.lower()
    assert "ai insight" not in body.lower()
    assert "recommendation" not in body.lower()


# --- HOME-09 staggered lazy-load regression (GAP fill) ----------------------


def test_home_shell_staggered_lazy_load(app: Any, clean_home_router: None) -> None:
    """Gate-open home shell renders >=5 staggered hx-trigger delays, distinct and ascending.

    Requirement HOME-09: the five aggregate cards use staggered hx-trigger="load delay:Nms"
    to spread fragment requests across 500ms.  A future edit that collapses the delays to a
    single value or drops slots would silently break this requirement without this test.

    The test seeds a GATE-OPEN user (reuses _seed_analytics_scenario from Plan 06-01),
    GETs /, and asserts that the rendered HTML contains at least 5 occurrences of
    hx-trigger="load delay:Nms" whose millisecond values are distinct and strictly
    ascending (100 < 200 < 300 < 400 < 500).
    """
    _require_postgres()
    _require_analytics_tables()

    from tests.services.test_analytics import _seed_analytics_scenario
    from app.db import SessionLocal

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(
            db, username="analyticstest-hometest-stagger"
        )

    client = _make_authed_client_for_user(app, uid)
    resp = client.get("/")
    assert resp.status_code == 200

    body = resp.text

    # Extract all hx-trigger="load delay:Nms" delay values from the rendered HTML.
    # The gate-open branch must contain at least 5 such slots (one per aggregate card).
    # The unrated-coffees slot (150ms) also appears, so total >= 6 -- but we only
    # require the five aggregate-card delays which must be distinct and ascending.
    delay_matches = re.findall(r'hx-trigger="load delay:(\d+)ms"', body)
    delay_values = [int(m) for m in delay_matches]

    assert len(delay_values) >= 5, (
        f"Expected >=5 hx-trigger='load delay:Nms' slots in gate-open home shell, "
        f"got {len(delay_values)}: {delay_values}"
    )

    # The five aggregate card delays must be distinct (no two slots share a delay value
    # among the five smallest after removing the 150ms unrated-coffees slot).
    # Strategy: sort all delay values and verify the five aggregate-card slots
    # (100/200/300/400/500ms per spec) are all present.
    expected_aggregate_delays = {100, 200, 300, 400, 500}
    actual_delay_set = set(delay_values)
    assert expected_aggregate_delays <= actual_delay_set, (
        f"Expected aggregate card delays {expected_aggregate_delays} to be present; "
        f"found delay values: {sorted(actual_delay_set)}"
    )

    # The aggregate delays must be strictly ascending (100 < 200 < 300 < 400 < 500),
    # proving they are staggered in DOM order as the spec requires.
    aggregate_delays_in_order = [v for v in delay_values if v in expected_aggregate_delays]
    assert aggregate_delays_in_order == sorted(aggregate_delays_in_order), (
        f"Aggregate card delays must appear in ascending order in the DOM; "
        f"found: {aggregate_delays_in_order}"
    )
