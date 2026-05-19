"""Service-layer tests for plan 04-08 — recipes CRUD + JSONB round-trip + duplicate.

Cases per ``.planning/phases/04-shared-catalog/04-VALIDATION.md`` row 04-08-NN.
Mirrors the structural shape of ``tests/phase_04/test_routers_roasters.py``
service-layer probes — uses the real Postgres engine via the
``_require_postgres`` + ``_require_p4_migration_applied`` skip gates.

Covered cases:

* JSONB ``steps`` survives DB round-trip with order preserved.
* Empty ``steps`` list is allowed and round-trips as ``[]``.
* :func:`duplicate_recipe` deep-copies every field, names the new row
  ``"<source> (copy)"``, and produces a fresh ``id``.
* The deep copy is independent of the source — mutating source steps
  via :func:`update_recipe` does NOT mutate the copy's steps.
* :func:`duplicate_recipe` raises :class:`RecipeNotFound` on an
  unknown id.
* :func:`archive_recipe` flips ``archived=True``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 4 service test needs the DB")


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


@pytest.fixture
def clean_recipes() -> Iterator[None]:
    """Wipe recipes (and dependent rows) before AND after each test."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        # brew_sessions is a Phase 5 table; try it in its OWN transaction
        # so a missing table doesn't taint the recipes DELETE.
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


# --------------------------------------------------------------------------- #
# JSONB round-trip                                                            #
# --------------------------------------------------------------------------- #


def test_create_recipe_steps_jsonb_round_trip(clean_recipes: None) -> None:
    """Multi-step steps survive DB round-trip with order preserved."""
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    steps = [
        {"water_grams": 50, "time_seconds": 30, "label": "Bloom"},
        {"water_grams": 200, "time_seconds": 90, "label": "Main"},
        {"water_grams": 250, "time_seconds": 150, "label": "Finish"},
    ]
    with SessionLocal() as db:
        created = recipes_service.create_recipe(
            db,
            name="Kasuya 4:6",
            dose_grams=15,
            water_grams=250,
            water_temp_c=92,
            grind_setting="medium-fine",
            steps=steps,
            by_user_id=0,
        )
        rid = created.id

    with SessionLocal() as db:
        fetched = recipes_service.get_recipe(db, recipe_id=rid)
    assert fetched is not None
    assert fetched.steps == steps  # exact list-of-dict round-trip
    # Order preserved.
    assert [s["label"] for s in fetched.steps] == ["Bloom", "Main", "Finish"]


def test_create_recipe_empty_steps_allowed(clean_recipes: None) -> None:
    """Empty steps list is allowed and round-trips as []."""
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    with SessionLocal() as db:
        created = recipes_service.create_recipe(
            db,
            name="No-steps recipe",
            dose_grams=15,
            water_grams=250,
            water_temp_c=92,
            grind_setting="",
            steps=[],
            by_user_id=0,
        )
        rid = created.id

    with SessionLocal() as db:
        fetched = recipes_service.get_recipe(db, recipe_id=rid)
    assert fetched is not None
    assert fetched.steps == []


# --------------------------------------------------------------------------- #
# duplicate_recipe (D-12)                                                     #
# --------------------------------------------------------------------------- #


def test_duplicate_recipe_clones_fields(clean_recipes: None) -> None:
    """duplicate_recipe deep-copies every field and produces a fresh id."""
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    steps = [{"water_grams": 50, "time_seconds": 30, "label": "Bloom"}]
    with SessionLocal() as db:
        src = recipes_service.create_recipe(
            db,
            name="Kasuya 4:6",
            dose_grams=15,
            water_grams=250,
            water_temp_c=92,
            grind_setting="medium-fine",
            steps=steps,
            by_user_id=0,
        )
        src_id = src.id

    with SessionLocal() as db:
        copy = recipes_service.duplicate_recipe(
            db, source_id=src_id, by_user_id=0
        )
        copy_id = copy.id
        copy_name = copy.name
        copy_dose = copy.dose_grams
        copy_water = copy.water_grams
        copy_temp = copy.water_temp_c
        copy_grind = copy.grind_setting
        copy_steps = copy.steps
        copy_archived = copy.archived

    assert copy_id != src_id
    assert copy_name == "Kasuya 4:6 (copy)"
    assert copy_dose == 15
    assert copy_water == 250
    assert copy_temp == 92
    assert copy_grind == "medium-fine"
    assert copy_steps == steps
    assert copy_archived is False


def test_duplicate_recipe_steps_independent(clean_recipes: None) -> None:
    """Mutating source's steps via update_recipe does NOT mutate the copy."""
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    src_steps = [{"water_grams": 50, "time_seconds": 30, "label": "Bloom"}]
    with SessionLocal() as db:
        src = recipes_service.create_recipe(
            db,
            name="A",
            dose_grams=15,
            water_grams=250,
            water_temp_c=92,
            grind_setting="",
            steps=src_steps,
            by_user_id=0,
        )
        src_id = src.id

    with SessionLocal() as db:
        copy = recipes_service.duplicate_recipe(
            db, source_id=src_id, by_user_id=0
        )
        copy_id = copy.id

    # Now mutate source's steps via update_recipe.
    new_src_steps = [
        {"water_grams": 100, "time_seconds": 60, "label": "Different"},
        {"water_grams": 200, "time_seconds": 120, "label": "Pour 2"},
    ]
    with SessionLocal() as db:
        recipes_service.update_recipe(
            db,
            recipe_id=src_id,
            name="A modified",
            dose_grams=20,
            water_grams=300,
            water_temp_c=94,
            grind_setting="finer",
            steps=new_src_steps,
            by_user_id=0,
        )

    # The copy's steps must be unchanged from when it was duplicated.
    with SessionLocal() as db:
        fetched_copy = recipes_service.get_recipe(db, recipe_id=copy_id)
    assert fetched_copy is not None
    assert fetched_copy.steps == src_steps
    assert fetched_copy.name == "A (copy)"


def test_duplicate_recipe_unknown_id_raises(clean_recipes: None) -> None:
    """duplicate_recipe(unknown_id) raises RecipeNotFound."""
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.services import recipes as recipes_service
    from app.services.recipes import RecipeNotFound

    with SessionLocal() as db, pytest.raises(RecipeNotFound):
        recipes_service.duplicate_recipe(db, source_id=999999, by_user_id=0)


# --------------------------------------------------------------------------- #
# archive                                                                     #
# --------------------------------------------------------------------------- #


def test_archive_recipe_sets_archived(clean_recipes: None) -> None:
    """archive_recipe flips archived to True."""
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.services import recipes as recipes_service

    with SessionLocal() as db:
        r = recipes_service.create_recipe(
            db,
            name="X",
            dose_grams=15,
            water_grams=250,
            water_temp_c=92,
            grind_setting="",
            steps=[],
            by_user_id=0,
        )
        rid = r.id

    with SessionLocal() as db:
        recipes_service.archive_recipe(db, recipe_id=rid, by_user_id=0)

    with SessionLocal() as db:
        fetched = recipes_service.get_recipe(db, recipe_id=rid)
    assert fetched is not None
    assert fetched.archived is True
