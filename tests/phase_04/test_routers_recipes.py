"""Router tests for plan 04-08 — recipes CRUD + HX-Redirect duplicate.

Cases per ``.planning/phases/04-shared-catalog/04-VALIDATION.md`` row 04-08-NN.
Mirrors ``tests/phase_04/test_routers_roasters.py`` shape (per-test CSRF
prime via ``_prime_csrf`` + ``clean_recipes`` fixture).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 4 router test needs the DB")


def _require_p4_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.recipes')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p4_shared_catalog migration not applied")


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real, signed csrftoken; wire it onto the client.

    See ``tests/phase_04/test_routers_roasters.py::_prime_csrf`` for the
    full rationale — the conftest ``authed_client`` fixture pre-sets a
    literal placeholder string, but ``starlette-csrf`` validates via
    ``URLSafeSerializer.loads`` (HMAC-signed), so the placeholder fails
    every POST with 403. Drop the cookie, GET /, re-wire the freshly
    minted token onto the client default header.
    """
    client.cookies.delete("csrftoken")
    response = client.get("/")
    token = response.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


@pytest.fixture
def clean_recipes() -> Iterator[None]:
    """Wipe recipes (and dependent rows) before AND after each test."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        # brew_sessions is a Phase 5 table; try it in its OWN transaction
        # so the savepoint doesn't taint the recipes DELETE if the table
        # is absent (psycopg leaves the connection in an aborted state).
        try:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM brew_sessions"))
        except Exception:  # noqa: BLE001
            pass
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM recipes"))

    _reset()
    yield
    _reset()


def _seed_recipe(**kwargs: Any) -> int:
    """Insert a recipe via the service and return its id."""
    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    defaults = {
        "name": kwargs.pop("name", "Kasuya 4:6"),
        "dose_grams": kwargs.pop("dose_grams", 15),
        "water_grams": kwargs.pop("water_grams", 250),
        "water_temp_c": kwargs.pop("water_temp_c", 92),
        "grind_setting": kwargs.pop("grind_setting", "medium-fine"),
        "steps": kwargs.pop(
            "steps",
            [{"water_grams": 50, "time_seconds": 30, "label": "Bloom"}],
        ),
        "by_user_id": kwargs.pop("by_user_id", 0),
    }
    with SessionLocal() as db:
        r = recipes_service.create_recipe(db, **defaults)
        return r.id


# --------------------------------------------------------------------------- #
# GET /recipes — list page                                                    #
# --------------------------------------------------------------------------- #


def test_list_recipes_renders_page(authed_client: Any, clean_recipes: None) -> None:
    """Authed GET /recipes → 200 + page HTML with h1 + Add recipe button."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/recipes")
    assert resp.status_code == 200
    body = resp.text
    assert "<h1" in body
    assert "Recipes" in body
    assert "Add recipe" in body


# --------------------------------------------------------------------------- #
# POST /recipes — create                                                      #
# --------------------------------------------------------------------------- #


def test_create_recipe_valid(authed_client: Any, clean_recipes: None) -> None:
    """Valid POST → 200 + row fragment."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/recipes",
        data={
            "name": "Kasuya 4:6",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "92",
            "grind_setting": "medium-fine",
            "steps": json.dumps([{"water_grams": 50, "time_seconds": 30, "label": "Bloom"}]),
        },
    )
    assert resp.status_code == 200, resp.text
    assert 'id="recipe-' in resp.text
    # OOB form-clear swap on create.
    assert "recipe-form-mount" in resp.text


def test_create_recipe_rejects_water_temp_over_100(authed_client: Any, clean_recipes: None) -> None:
    """temp=101 → 200 + form re-render with the water_temp_c error.

    Locks ROADMAP Phase 4 success criterion #5 ("temp 0-100°C").
    """
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/recipes",
        data={
            "name": "Hot brew",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "101",
            "grind_setting": "",
            "steps": "[]",
        },
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


def test_create_recipe_rejects_negative_dose(authed_client: Any, clean_recipes: None) -> None:
    """dose=0 → 200 + form re-render with dose_grams error."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/recipes",
        data={
            "name": "Zero dose",
            "dose_grams": "0",
            "water_grams": "250",
            "water_temp_c": "92",
            "grind_setting": "",
            "steps": "[]",
        },
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


def test_create_recipe_steps_jsonb_round_trip_via_post(
    authed_client: Any, clean_recipes: None
) -> None:
    """POST multi-step steps → get_recipe returns the same array in order."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    steps = [
        {"water_grams": 50, "time_seconds": 30, "label": "Bloom"},
        {"water_grams": 200, "time_seconds": 90, "label": "Main"},
        {"water_grams": 250, "time_seconds": 150, "label": "Finish"},
    ]
    resp = authed_client.post(
        "/recipes",
        data={
            "name": "Round-trip",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "92",
            "grind_setting": "",
            "steps": json.dumps(steps),
        },
    )
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    with SessionLocal() as db:
        rows = recipes_service.list_recipes(db)
    match = next((r for r in rows if r.name == "Round-trip"), None)
    assert match is not None
    assert match.steps == steps


def test_create_recipe_invalid_steps_json_re_renders_form(
    authed_client: Any, clean_recipes: None
) -> None:
    """steps="not-valid-json" → 200 + form re-render with _steps banner."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/recipes",
        data={
            "name": "Bad JSON",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "92",
            "grind_setting": "",
            "steps": "not-valid-json",
        },
    )
    assert resp.status_code == 200
    # The _steps banner copy from the router renders into the form.
    assert "Invalid step data" in resp.text


def test_create_recipe_step_water_over_2000_rejected(
    authed_client: Any, clean_recipes: None
) -> None:
    """Per-step water_grams=2001 → 200 + form re-render with steps-error banner."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/recipes",
        data={
            "name": "Too much water",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "92",
            "grind_setting": "",
            "steps": json.dumps([{"water_grams": 2001, "time_seconds": 30, "label": ""}]),
        },
    )
    assert resp.status_code == 200
    # The per-step error is folded into the _steps banner (UI-SPEC ring
    # highlighting is plan 04-11). Probe for the banner-copy substring.
    assert "steps" in resp.text.lower()
    assert "text-red-700" in resp.text


def test_create_recipe_extra_field_rejected(authed_client: Any, clean_recipes: None) -> None:
    """Extra form field → 200 + form re-render (T-04-MASS via extra='forbid')."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/recipes",
        data={
            "name": "Probe",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "92",
            "grind_setting": "",
            "steps": "[]",
            "is_admin": "true",  # not in RecipeCreate — must be rejected.
        },
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


# --------------------------------------------------------------------------- #
# GET /recipes/{id}/edit + POST update                                        #
# --------------------------------------------------------------------------- #


def test_edit_pre_populates_steps_json(authed_client: Any, clean_recipes: None) -> None:
    """GET /{id}/edit → body contains data-initial-steps with the recipe's steps."""
    _require_postgres()
    _require_p4_migration_applied()
    steps = [
        {"water_grams": 60, "time_seconds": 40, "label": "Bloom"},
        {"water_grams": 200, "time_seconds": 120, "label": "Pour"},
    ]
    rid = _seed_recipe(name="Editable", steps=steps)
    resp = authed_client.get(f"/recipes/{rid}/edit")
    assert resp.status_code == 200
    body = resp.text
    assert "data-initial-steps=" in body
    # Steps content is present as JSON. Probe for distinctive substrings
    # rather than full JSON match (Jinja's autoescape will HTML-encode
    # quotes inside an attribute).
    assert "Bloom" in body
    assert "Pour" in body


def test_update_persists_steps_change(authed_client: Any, clean_recipes: None) -> None:
    """POST /{id} with new steps → fetch reflects."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_recipe(name="Before")
    _prime_csrf(authed_client)
    new_steps = [
        {"water_grams": 70, "time_seconds": 45, "label": "Updated bloom"},
        {"water_grams": 300, "time_seconds": 180, "label": "Updated pour"},
    ]
    resp = authed_client.post(
        f"/recipes/{rid}",
        data={
            "name": "After",
            "dose_grams": "18",
            "water_grams": "300",
            "water_temp_c": "94",
            "grind_setting": "coarser",
            "steps": json.dumps(new_steps),
        },
    )
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    with SessionLocal() as db:
        fetched = recipes_service.get_recipe(db, recipe_id=rid)
    assert fetched is not None
    assert fetched.name == "After"
    assert fetched.dose_grams == 18
    assert fetched.steps == new_steps


# --------------------------------------------------------------------------- #
# POST /recipes/{id}/duplicate — D-12 HX-Redirect                             #
# --------------------------------------------------------------------------- #


def test_duplicate_emits_hx_redirect(authed_client: Any, clean_recipes: None) -> None:
    """POST /{id}/duplicate → 200 + HX-Redirect: /recipes/{new_id}/edit."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_recipe(name="Source")
    _prime_csrf(authed_client)
    resp = authed_client.post(f"/recipes/{rid}/duplicate")
    assert resp.status_code == 200, resp.text
    assert "HX-Redirect" in resp.headers
    redirect = resp.headers["HX-Redirect"]
    # Format: /recipes/<int>/edit; the new id differs from the source.
    assert redirect.startswith("/recipes/")
    assert redirect.endswith("/edit")
    # Parse the middle id out and assert it's an int != rid.
    middle = redirect.removeprefix("/recipes/").removesuffix("/edit")
    new_id = int(middle)
    assert new_id != rid


def test_duplicate_404_unknown_id(authed_client: Any, clean_recipes: None) -> None:
    """POST /99999/duplicate → 404."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post("/recipes/999999/duplicate")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST /recipes/{id}/archive                                                  #
# --------------------------------------------------------------------------- #


def test_archive_recipe_marks_archived(authed_client: Any, clean_recipes: None) -> None:
    """POST /{id}/archive → DB row.archived=True."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_recipe(name="ToArchive")
    _prime_csrf(authed_client)
    resp = authed_client.post(f"/recipes/{rid}/archive")
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    with SessionLocal() as db:
        fetched = recipes_service.get_recipe(db, recipe_id=rid)
    assert fetched is not None
    assert fetched.archived is True


# --------------------------------------------------------------------------- #
# CSRF                                                                        #
# --------------------------------------------------------------------------- #


def test_csrf_missing_returns_403(csrf_client: Any, clean_recipes: None) -> None:
    """POST /recipes with mismatched CSRF → 403 from CSRFMiddleware."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = csrf_client.post("/recipes", data={"name": "X"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# UI-SPEC lock: duplicate button visible on the list row                      #
# --------------------------------------------------------------------------- #


def test_recipe_list_shows_duplicate_button(authed_client: Any, clean_recipes: None) -> None:
    """List row HTML contains hx-post="/recipes/<id>/duplicate" — UI-SPEC lock."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_recipe(name="Shown")
    resp = authed_client.get("/recipes")
    assert resp.status_code == 200
    body = resp.text
    assert f'hx-post="/recipes/{rid}/duplicate"' in body
