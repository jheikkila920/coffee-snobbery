"""Real model-layer tests for plan 04-03 (replaces the Wave-0 stub).

These are **integration** tests — they require Postgres and the
``p4_shared_catalog`` migration to have run. Each test isolates itself by
cleaning the catalog tables in a ``finally`` block (mirroring the pattern
in ``tests/services/test_credentials.py``); the autouse ``fresh_db``
fixture in ``tests/conftest.py`` only touches ``users`` / ``sessions`` /
``app_settings.setup_completed``, so the Phase 4 catalog tables are left
to each test to manage.

Coverage map (12 cases):

* Roaster: round-trip, CITEXT case-insensitive unique (2 cases).
* FlavorNote: category CHECK constraint rejection (1 case).
* Coffee: ARRAY round-trip, process CHECK accepts NULL, process CHECK
  rejects unknown value (3 cases).
* Equipment: type CHECK rejection, usage_count defaults to zero (2 cases).
* Recipe: JSONB round-trip preserving step order + nested keys (1 case).
* Bag: FK RESTRICT on coffees, photo_filename optional, photo_filename
  persists (3 cases).

Defense-in-depth note: every CHECK constraint test passes a value that
would be rejected by the Pydantic schema layer in plan 04-02 too — these
tests exercise the **DB-side** defense that backstops the schema layer
if it's ever bypassed (raw SQL INSERT, bulk import, future ORM-less
code path).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


def _require_postgres() -> None:
    """Skip if Postgres is not reachable (host-only / unit-only runs)."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 4 model test needs the DB")


def _require_p4_migration_applied() -> None:
    """Skip cleanly if the Phase 4 migration hasn't been applied yet.

    The model tests assume ``alembic upgrade head`` ran first; if a
    developer runs the test suite against a partially migrated DB, skip
    rather than emit confusing ``UndefinedTable`` errors.
    """
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT to_regclass('public.coffees')")
            ).scalar()
    except Exception as exc:  # noqa: BLE001 — defensive skip on any DB error
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p4_shared_catalog migration not applied")


@pytest.fixture
def clean_catalog() -> Iterator[None]:
    """Wipe Phase 4 catalog tables before AND after each test.

    Catalog tables are NOT touched by ``fresh_db`` (that fixture is
    Phase 2-scoped: users / sessions / setup_completed only). Use a
    dedicated reset here so tests don't bleed rows into each other.

    Reset order respects FKs:
    * ``bags`` references ``coffees`` (RESTRICT) — bags first.
    * ``coffees`` references ``roasters`` (SET NULL) — coffees before
      roasters (RESTRICT doesn't apply on the SET NULL side, but the
      reset semantically wants coffees gone first).
    * Independent tables (``flavor_notes``, ``equipment``, ``recipes``)
      can go in any order.
    """
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM bags"))
            conn.execute(text("DELETE FROM coffees"))
            conn.execute(text("DELETE FROM roasters"))
            conn.execute(text("DELETE FROM flavor_notes"))
            conn.execute(text("DELETE FROM equipment"))
            conn.execute(text("DELETE FROM recipes"))

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# Roaster                                                                     #
# --------------------------------------------------------------------------- #


def test_roaster_round_trip(clean_catalog: None) -> None:
    """Insert a Roaster and read it back by id; baseline persistence test."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.roaster import Roaster

    with SessionLocal() as db:
        r = Roaster(name="Onyx", location="Bentonville, AR")
        db.add(r)
        db.commit()
        db.refresh(r)
        inserted_id = r.id

        fetched = db.execute(
            select(Roaster).where(Roaster.id == inserted_id)
        ).scalar_one()
        assert fetched.name == "Onyx"
        assert fetched.location == "Bentonville, AR"
        # archived defaults to False via server_default.
        assert fetched.archived is False
        # notes defaults to "" via server_default.
        assert fetched.notes == ""


def test_roaster_name_unique_citext(clean_catalog: None) -> None:
    """CITEXT unique: 'Onyx' and 'onyx' collide on insert (CAT-01)."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models.roaster import Roaster

    with SessionLocal() as db:
        db.add(Roaster(name="Onyx"))
        db.commit()

    # New session — the unique violation must surface here on commit.
    with SessionLocal() as db:
        db.add(Roaster(name="onyx"))
        with pytest.raises(IntegrityError):
            db.commit()


# --------------------------------------------------------------------------- #
# FlavorNote                                                                  #
# --------------------------------------------------------------------------- #


def test_flavor_note_category_check(clean_catalog: None) -> None:
    """CHECK constraint rejects categories outside the locked 9-value set."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models.flavor_note import FlavorNote

    with SessionLocal() as db:
        # 'metallic' is not in the locked vocabulary
        # (fruit/floral/sweet/chocolate/nutty/spice/savory/fermented/other).
        db.add(FlavorNote(name="rust", category="metallic"))
        with pytest.raises(IntegrityError):
            db.commit()


# --------------------------------------------------------------------------- #
# Coffee                                                                      #
# --------------------------------------------------------------------------- #


def test_coffee_advertised_flavor_note_ids_round_trip(clean_catalog: None) -> None:
    """ARRAY(BigInteger) round-trips as list[int] preserving order (CAT-03)."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.coffee import Coffee

    with SessionLocal() as db:
        c = Coffee(name="Ethiopia Yirgacheffe", advertised_flavor_note_ids=[1, 2, 3])
        db.add(c)
        db.commit()
        db.refresh(c)
        inserted_id = c.id

        fetched = db.execute(
            select(Coffee).where(Coffee.id == inserted_id)
        ).scalar_one()
        assert fetched.advertised_flavor_note_ids == [1, 2, 3]
        # List-of-ints invariant (Postgres ARRAY -> Python list).
        assert isinstance(fetched.advertised_flavor_note_ids, list)
        assert all(isinstance(x, int) for x in fetched.advertised_flavor_note_ids)


def test_coffee_process_check_allows_null(clean_catalog: None) -> None:
    """process CHECK is IS NULL OR ... — NULL accepted (CAT-03)."""
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.models.coffee import Coffee

    with SessionLocal() as db:
        db.add(Coffee(name="Process-Unknown", process=None))
        db.commit()  # must NOT raise


def test_coffee_process_check_rejects_unknown(clean_catalog: None) -> None:
    """process CHECK rejects values outside the locked 6-value set."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models.coffee import Coffee

    with SessionLocal() as db:
        db.add(Coffee(name="Weird", process="cold_brewed"))
        with pytest.raises(IntegrityError):
            db.commit()


# --------------------------------------------------------------------------- #
# Equipment                                                                   #
# --------------------------------------------------------------------------- #


def test_equipment_type_check(clean_catalog: None) -> None:
    """type CHECK rejects values outside the 6-value set (CAT-05)."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models.equipment import Equipment

    with SessionLocal() as db:
        db.add(Equipment(type="grinder_v2", brand="Niche", model="Zero"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_equipment_usage_count_defaults_zero(clean_catalog: None) -> None:
    """usage_count has server_default=0; new rows ship with count=0."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.equipment import Equipment

    with SessionLocal() as db:
        e = Equipment(type="grinder", brand="Comandante", model="C40")
        db.add(e)
        db.commit()
        db.refresh(e)
        inserted_id = e.id

        fetched = db.execute(
            select(Equipment).where(Equipment.id == inserted_id)
        ).scalar_one()
        assert fetched.usage_count == 0


# --------------------------------------------------------------------------- #
# Recipe                                                                      #
# --------------------------------------------------------------------------- #


def test_recipe_steps_jsonb_round_trip(clean_catalog: None) -> None:
    """JSONB steps round-trip preserves order + nested keys (CAT-06)."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.recipe import Recipe

    steps = [
        {"water_grams": 50, "time_seconds": 30, "label": "Bloom"},
        {"water_grams": 150, "time_seconds": 30, "label": "First Pour"},
        {"water_grams": 100, "time_seconds": 30, "label": "Second Pour"},
    ]
    with SessionLocal() as db:
        r = Recipe(
            name="4:6 Method",
            dose_grams=20,
            water_grams=300,
            water_temp_c=92,
            steps=steps,
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        inserted_id = r.id

        fetched = db.execute(
            select(Recipe).where(Recipe.id == inserted_id)
        ).scalar_one()
        # JSONB does NOT preserve key order within an object, but DOES preserve
        # array order — that's the contract the recipe relies on.
        assert len(fetched.steps) == 3
        assert fetched.steps[0]["water_grams"] == 50
        assert fetched.steps[0]["label"] == "Bloom"
        assert fetched.steps[2]["label"] == "Second Pour"


# --------------------------------------------------------------------------- #
# Bag — FK + photo_filename                                                   #
# --------------------------------------------------------------------------- #


def test_bag_coffee_fk_restrict(clean_catalog: None) -> None:
    """Deleting a coffee referenced by a bag fails (RESTRICT, CAT-04 + CAT-08)."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import delete
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models.bag import Bag
    from app.models.coffee import Coffee

    # Setup: insert a coffee and a bag referencing it.
    with SessionLocal() as db:
        c = Coffee(name="Restricted Brew")
        db.add(c)
        db.commit()
        db.refresh(c)
        coffee_id = c.id

        b = Bag(coffee_id=coffee_id)
        db.add(b)
        db.commit()

    # Attempt to hard-delete the coffee — RESTRICT must reject.
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(delete(Coffee).where(Coffee.id == coffee_id))
            db.commit()


def test_bag_photo_filename_optional(clean_catalog: None) -> None:
    """photo_filename is NULLABLE — a bag may not have a photo."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.bag import Bag
    from app.models.coffee import Coffee

    with SessionLocal() as db:
        c = Coffee(name="No-Photo Coffee")
        db.add(c)
        db.commit()
        db.refresh(c)

        b = Bag(coffee_id=c.id, photo_filename=None)
        db.add(b)
        db.commit()
        db.refresh(b)

        fetched = db.execute(select(Bag).where(Bag.id == b.id)).scalar_one()
        assert fetched.photo_filename is None


def test_bag_photo_filename_persists(clean_catalog: None) -> None:
    """photo_filename round-trips when set (UUID-shaped basename)."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.bag import Bag
    from app.models.coffee import Coffee

    with SessionLocal() as db:
        c = Coffee(name="Photo Coffee")
        db.add(c)
        db.commit()
        db.refresh(c)

        b = Bag(
            coffee_id=c.id,
            photo_filename="8f0a1d2c-3b4e-4f5a-9c8d-1234567890ab.jpg",
        )
        db.add(b)
        db.commit()
        db.refresh(b)

        fetched = db.execute(select(Bag).where(Bag.id == b.id)).scalar_one()
        assert fetched.photo_filename == "8f0a1d2c-3b4e-4f5a-9c8d-1234567890ab.jpg"
