"""Router tests for Plan 11-04 — Guided Brew Mode (app/routers/brew_guided.py).

Covers:
* GET /brew/guided?recipe_id=<with-steps>      → 200 + x-data + data-steps present
* GET /brew/guided?recipe_id=<nonexistent>     → 404
* GET /brew/guided?recipe_id=<with-steps>      (no session cookie) → 401
* GET /brew/guided?recipe_id=<stepless>        → 200 + "Recipe has no steps."
* POST /brew with brew_time_seconds=300        → persisted; 86401 → 422

Real Postgres + the brew_sessions migration are required; the skip gates mirror
tests/routers/test_brew_router.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest

_RECIPE_PREFIX = "GBMTestRecipe"


# --------------------------------------------------------------------------- #
# Skip gates                                                                    #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — GBM router test needs the DB")


def _require_brew_sessions_table() -> None:
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
        pytest.skip("brew_sessions migration not applied")


def _require_gbm_router() -> None:
    try:
        from app.routers.brew_guided import router  # noqa: F401
    except ImportError:
        pytest.skip("plan 11-04 dependency: app.routers.brew_guided not importable")


# --------------------------------------------------------------------------- #
# Seeding helpers                                                               #
# --------------------------------------------------------------------------- #

_STEP_WITH_STEPS = [
    {"label": "Bloom", "water_grams": 50, "time_seconds": 45, "notes": ""},
    {"label": "Pour", "water_grams": 200, "time_seconds": 90, "notes": ""},
]


def _seed_recipe(db: Any, *, name: str, steps: list[dict] | None = None) -> Any:
    from app.models.recipe import Recipe

    recipe = Recipe(
        name=name,
        dose_grams=18,
        water_grams=300,
        water_temp_c=93,
        grind_setting="22",
        steps=steps or [],
    )
    db.add(recipe)
    db.flush()
    return recipe


def _seed_coffee(db: Any, *, name: str) -> Any:
    from app.models.coffee import Coffee

    coffee = Coffee(name=name, advertised_flavor_note_ids=[])
    db.add(coffee)
    db.flush()
    return coffee


@pytest.fixture
def clean_gbm() -> Iterator[None]:
    """Wipe GBM-test recipes before and after each test."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM brew_sessions"))
            conn.execute(text(f"DELETE FROM brew_drafts"))
            conn.execute(text(f"DELETE FROM recipes WHERE name LIKE '{_RECIPE_PREFIX}%'"))
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'GBMCoffee%'"))

    _reset()
    yield
    _reset()


def _authed_client(app: Any, signed_cookie: str) -> Any:
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.cookies.set("session_id", signed_cookie)
    _prime_csrf(client)
    return client


def _prime_csrf(client: Any) -> str:
    client.cookies.delete("csrftoken")
    response = client.get("/")
    token = response.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #


def test_gbm_200_with_steps(app: Any, seeded_regular_user: Any, clean_gbm: Any) -> None:
    """GET /brew/guided with a recipe that has steps → 200 + Alpine component present."""
    _require_postgres()
    _require_brew_sessions_table()
    _require_gbm_router()

    from app.db import SessionLocal

    with SessionLocal() as db:
        recipe = _seed_recipe(db, name=f"{_RECIPE_PREFIX} WithSteps", steps=_STEP_WITH_STEPS)
        db.commit()
        rid = recipe.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/guided?recipe_id={rid}")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
    assert 'x-data="guidedBrewMode"' in r.text, (
        "Expected Alpine x-data=\"guidedBrewMode\" in response body"
    )
    assert "data-steps=" in r.text, "Expected data-steps attribute in response body"


def test_gbm_404_missing_recipe(app: Any, seeded_regular_user: Any) -> None:
    """GET /brew/guided with a nonexistent recipe_id → 404."""
    _require_postgres()
    _require_brew_sessions_table()
    _require_gbm_router()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/brew/guided?recipe_id=999999999")
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:300]}"


def test_gbm_401_anonymous(app: Any) -> None:
    """GET /brew/guided without a session cookie → 401."""
    _require_postgres()
    _require_brew_sessions_table()
    _require_gbm_router()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/brew/guided?recipe_id=1", follow_redirects=False)
    # The auth gate returns 401 (or redirects to /login — either is acceptable).
    assert r.status_code in (401, 302, 303), (
        f"expected 401/302/303 for anonymous, got {r.status_code}: {r.text[:300]}"
    )


def test_gbm_200_stepless_recipe(app: Any, seeded_regular_user: Any, clean_gbm: Any) -> None:
    """GET /brew/guided with a recipe with no steps → 200 + disabled-state copy."""
    _require_postgres()
    _require_brew_sessions_table()
    _require_gbm_router()

    from app.db import SessionLocal

    with SessionLocal() as db:
        recipe = _seed_recipe(db, name=f"{_RECIPE_PREFIX} NoSteps", steps=[])
        db.commit()
        rid = recipe.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/guided?recipe_id={rid}")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
    assert "Recipe has no steps" in r.text, (
        "Expected 'Recipe has no steps' in disabled-state response body"
    )


def test_brew_time_seconds_persisted(
    app: Any, seeded_regular_user: Any, clean_gbm: Any
) -> None:
    """POST /brew with brew_time_seconds=300 → the persisted session has brew_time_seconds=300."""
    _require_postgres()
    _require_brew_sessions_table()
    _require_gbm_router()

    from app.db import SessionLocal

    with SessionLocal() as db:
        coffee = _seed_coffee(db, name="GBMCoffee Round-trip")
        db.commit()
        cid = coffee.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/brew",
        data={
            "coffee_id": str(cid),
            "dose_grams_actual": "18",
            "water_grams_actual": "300",
            "water_temp_c_actual": "93",
            "grind_setting_actual": "22",
            "rating": "4",
            "notes": "",
            "brew_time_seconds": "300",
        },
    )
    # Successful create: HTMX path returns 204 + HX-Redirect header; fallback is 302/303.
    assert r.status_code in (200, 204, 302, 303), (
        f"expected 200/204/302/303, got {r.status_code}: {r.text[:300]}"
    )

    from app.services import brew_sessions as svc

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        sessions = svc.list_brew_sessions(db, by_user_id=uid)
    assert len(sessions) == 1, f"expected 1 persisted brew session, got {len(sessions)}"
    assert sessions[0].brew_time_seconds == 300, (
        f"expected brew_time_seconds=300, got {sessions[0].brew_time_seconds}"
    )


def test_brew_time_seconds_validation_rejects_86401(
    app: Any, seeded_regular_user: Any, clean_gbm: Any
) -> None:
    """POST /brew with brew_time_seconds=86401 → rejected (422 or 200 re-render with error)."""
    _require_postgres()
    _require_brew_sessions_table()
    _require_gbm_router()

    from app.db import SessionLocal

    with SessionLocal() as db:
        coffee = _seed_coffee(db, name="GBMCoffee Validation")
        db.commit()
        cid = coffee.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/brew",
        data={
            "coffee_id": str(cid),
            "dose_grams_actual": "18",
            "water_grams_actual": "300",
            "water_temp_c_actual": "93",
            "grind_setting_actual": "22",
            "rating": "4",
            "notes": "",
            "brew_time_seconds": "86401",
        },
    )
    # The brew router re-renders the form (200) or returns 422 for out-of-range values.
    assert r.status_code in (200, 422), (
        f"expected 200 re-render or 422, got {r.status_code}: {r.text[:300]}"
    )

    # No row should be inserted.
    from app.services import brew_sessions as svc

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        sessions = svc.list_brew_sessions(db, by_user_id=uid)
    assert sessions == [], (
        f"expected no persisted brew session after invalid brew_time_seconds, "
        f"got {len(sessions)} rows"
    )
