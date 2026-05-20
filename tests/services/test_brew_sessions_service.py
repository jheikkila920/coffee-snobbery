"""Service-layer tests for plan 05-02 Task 1 — brew_sessions CRUD.

Covers the ``<behavior>`` cases from the plan:

* ``create_brew_session`` writes a per-user row scoped by ``by_user_id`` and
  increments ``equipment.usage_count`` by +1 for each non-null equipment FK.
* ``update_brew_session`` diffs the three equipment FKs old-vs-new and
  adjusts ``usage_count`` (-1 on each removed/changed-away, +1 on each
  added/changed-to); unchanged FKs stay put.
* ``delete_brew_session`` decrements ``usage_count`` for each non-null FK.
* ``get`` / ``list`` are scoped by ``user_id`` — a second user's session is
  invisible / returns ``None`` (IDOR defense, T-05-05).
* ``update`` / ``delete`` of a non-owned session return ``None`` / ``False``.

Mirrors the structural shape of ``tests/phase_04/test_services_recipes.py``:
real Postgres via the ``_require_postgres`` + ``_require_p5_migration_applied``
skip gates, the ``SessionLocal`` context-manager pattern, and a ``clean_brew``
fixture that wipes Phase-5 rows before and after each test.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest


# --------------------------------------------------------------------------- #
# Skip gates (mirror tests/phase_04/test_services_recipes.py)                 #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 5 service test needs the DB")


def _require_p5_migration_applied() -> None:
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
        pytest.skip("p5_brew_sessions migration not applied")


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture                                             #
# --------------------------------------------------------------------------- #


def _seed_user(db, *, username: str):
    """Insert a minimal User row (RESTRICT FK target for brew_sessions)."""
    from app.models.user import User

    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user


def _seed_coffee(db, *, name: str = "Test Coffee"):
    from app.models.coffee import Coffee

    coffee = Coffee(name=name)
    db.add(coffee)
    db.flush()
    return coffee


def _seed_equipment(db, *, type_: str, brand: str):
    from app.models.equipment import Equipment

    eq = Equipment(type=type_, brand=brand, model="M")
    db.add(eq)
    db.flush()
    return eq


@pytest.fixture
def clean_brew() -> Iterator[None]:
    """Wipe Phase-5 rows + the test users/coffees/equipment before AND after.

    brew_sessions FKs to users (RESTRICT), coffees (RESTRICT), and equipment
    (SET NULL), so delete sessions first, then the seeded catalog/users rows.
    Other Phase-4 tests own their own catalog rows via their own fixtures; we
    only remove rows the brew tests create (identifiable test usernames).
    """
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(text("DELETE FROM equipment WHERE model = 'M'"))
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'Test Coffee%'"))
            conn.execute(text("DELETE FROM sessions WHERE user_id IN "
                              "(SELECT id FROM users WHERE username LIKE 'brewtest-%')"))
            conn.execute(text("DELETE FROM users WHERE username LIKE 'brewtest-%'"))

    _reset()
    yield
    _reset()


def _usage_count(db, equipment_id: int) -> int:
    from sqlalchemy import select

    from app.models.equipment import Equipment

    return db.execute(
        select(Equipment.usage_count).where(Equipment.id == equipment_id)
    ).scalar_one()


# --------------------------------------------------------------------------- #
# create + usage_count                                                        #
# --------------------------------------------------------------------------- #


def test_create_writes_user_scoped_row(clean_brew: None) -> None:
    """create_brew_session persists a row with user_id == by_user_id."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="brewtest-create")
        coffee = _seed_coffee(db)
        db.commit()
        uid, cid = user.id, coffee.id

    with SessionLocal() as db:
        row = svc.create_brew_session(
            db,
            by_user_id=uid,
            coffee_id=cid,
            bag_id=None,
            recipe_id=None,
            brewer_id=None,
            grinder_id=None,
            kettle_id=None,
            water_type="Filtered",
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=None,
            tds_pct=None,
            water_temp_c_actual=Decimal("93"),
            grind_setting_actual="22",
            rating=Decimal("4.25"),
            flavor_note_ids_observed=[],
            notes="",
            brewed_at=None,
        )
        sid = row.id

    with SessionLocal() as db:
        fetched = svc.get_brew_session(db, session_id=sid, by_user_id=uid)
    assert fetched is not None
    assert fetched.user_id == uid
    assert fetched.coffee_id == cid
    assert fetched.rating == Decimal("4.25")
    assert fetched.brewed_at is not None  # server default applied


def test_usage_count(clean_brew: None) -> None:
    """+1 per non-null FK on create; diff on edit; -1 per non-null FK on delete."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="brewtest-usage")
        coffee = _seed_coffee(db)
        brewer = _seed_equipment(db, type_="brewer", brand="V60")
        grinder_a = _seed_equipment(db, type_="grinder", brand="A")
        grinder_b = _seed_equipment(db, type_="grinder", brand="B")
        kettle = _seed_equipment(db, type_="kettle", brand="K")
        db.commit()
        uid, cid = user.id, coffee.id
        b_id, ga_id, gb_id, k_id = brewer.id, grinder_a.id, grinder_b.id, kettle.id

    # create with brewer + grinder_a + kettle → each +1, grinder_b untouched.
    with SessionLocal() as db:
        row = svc.create_brew_session(
            db,
            by_user_id=uid,
            coffee_id=cid,
            bag_id=None,
            recipe_id=None,
            brewer_id=b_id,
            grinder_id=ga_id,
            kettle_id=k_id,
            water_type="",
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=None,
            tds_pct=None,
            water_temp_c_actual=None,
            grind_setting_actual="",
            rating=None,
            flavor_note_ids_observed=[],
            notes="",
            brewed_at=None,
        )
        sid = row.id

    with SessionLocal() as db:
        assert _usage_count(db, b_id) == 1
        assert _usage_count(db, ga_id) == 1
        assert _usage_count(db, k_id) == 1
        assert _usage_count(db, gb_id) == 0

    # edit: change grinder A → B. A -1, B +1; brewer/kettle unchanged.
    with SessionLocal() as db:
        svc.update_brew_session(
            db,
            session_id=sid,
            by_user_id=uid,
            grinder_id=gb_id,
        )

    with SessionLocal() as db:
        assert _usage_count(db, ga_id) == 0
        assert _usage_count(db, gb_id) == 1
        assert _usage_count(db, b_id) == 1
        assert _usage_count(db, k_id) == 1

    # delete: each non-null FK (brewer, grinder_b, kettle) -1.
    with SessionLocal() as db:
        assert svc.delete_brew_session(db, session_id=sid, by_user_id=uid) is True

    with SessionLocal() as db:
        assert _usage_count(db, b_id) == 0
        assert _usage_count(db, gb_id) == 0
        assert _usage_count(db, k_id) == 0


def test_usage_count_null_to_value_and_value_to_null(clean_brew: None) -> None:
    """Setting a previously-null FK to a value +1; clearing a FK to null -1."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="brewtest-nullflip")
        coffee = _seed_coffee(db)
        brewer = _seed_equipment(db, type_="brewer", brand="V60")
        db.commit()
        uid, cid, b_id = user.id, coffee.id, brewer.id

    # create with no equipment.
    with SessionLocal() as db:
        row = svc.create_brew_session(
            db,
            by_user_id=uid,
            coffee_id=cid,
            bag_id=None,
            recipe_id=None,
            brewer_id=None,
            grinder_id=None,
            kettle_id=None,
            water_type="",
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=None,
            tds_pct=None,
            water_temp_c_actual=None,
            grind_setting_actual="",
            rating=None,
            flavor_note_ids_observed=[],
            notes="",
            brewed_at=None,
        )
        sid = row.id

    with SessionLocal() as db:
        assert _usage_count(db, b_id) == 0

    # null → value: brewer +1.
    with SessionLocal() as db:
        svc.update_brew_session(db, session_id=sid, by_user_id=uid, brewer_id=b_id)
    with SessionLocal() as db:
        assert _usage_count(db, b_id) == 1

    # value → null: brewer -1.
    with SessionLocal() as db:
        svc.update_brew_session(db, session_id=sid, by_user_id=uid, brewer_id=None)
    with SessionLocal() as db:
        assert _usage_count(db, b_id) == 0


# --------------------------------------------------------------------------- #
# user scoping / IDOR (T-05-05)                                               #
# --------------------------------------------------------------------------- #


def test_list_user_scoped(clean_brew: None) -> None:
    """A second user's session is invisible to the first user's list/get."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user_a = _seed_user(db, username="brewtest-scope-a")
        user_b = _seed_user(db, username="brewtest-scope-b")
        coffee = _seed_coffee(db)
        db.commit()
        a_id, b_id, cid = user_a.id, user_b.id, coffee.id

    common = dict(
        coffee_id=cid,
        bag_id=None,
        recipe_id=None,
        brewer_id=None,
        grinder_id=None,
        kettle_id=None,
        water_type="",
        dose_grams_actual=Decimal("15"),
        water_grams_actual=Decimal("250"),
        yield_grams_actual=None,
        tds_pct=None,
        water_temp_c_actual=None,
        grind_setting_actual="",
        rating=None,
        flavor_note_ids_observed=[],
        notes="",
        brewed_at=None,
    )
    with SessionLocal() as db:
        a_row = svc.create_brew_session(db, by_user_id=a_id, **common)
        svc.create_brew_session(db, by_user_id=b_id, **common)
        a_sid = a_row.id

    with SessionLocal() as db:
        a_list = svc.list_brew_sessions(db, by_user_id=a_id)
        b_list = svc.list_brew_sessions(db, by_user_id=b_id)
    assert len(a_list) == 1
    assert len(b_list) == 1
    assert a_list[0].user_id == a_id

    # B cannot get / update / delete A's session.
    with SessionLocal() as db:
        assert svc.get_brew_session(db, session_id=a_sid, by_user_id=b_id) is None
    with SessionLocal() as db:
        assert (
            svc.update_brew_session(db, session_id=a_sid, by_user_id=b_id, notes="hax") is None
        )
    with SessionLocal() as db:
        assert svc.delete_brew_session(db, session_id=a_sid, by_user_id=b_id) is False

    # A's row is unchanged.
    with SessionLocal() as db:
        still = svc.get_brew_session(db, session_id=a_sid, by_user_id=a_id)
    assert still is not None
    assert still.notes == ""


def test_list_filters(clean_brew: None) -> None:
    """list_brew_sessions applies optional coffee_id / rating filters."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="brewtest-filters")
        coffee1 = _seed_coffee(db, name="Test Coffee One")
        coffee2 = _seed_coffee(db, name="Test Coffee Two")
        db.commit()
        uid, c1, c2 = user.id, coffee1.id, coffee2.id

    base = dict(
        bag_id=None,
        recipe_id=None,
        brewer_id=None,
        grinder_id=None,
        kettle_id=None,
        water_type="",
        dose_grams_actual=Decimal("15"),
        water_grams_actual=Decimal("250"),
        yield_grams_actual=None,
        tds_pct=None,
        water_temp_c_actual=None,
        grind_setting_actual="",
        flavor_note_ids_observed=[],
        notes="",
        brewed_at=None,
    )
    with SessionLocal() as db:
        svc.create_brew_session(db, by_user_id=uid, coffee_id=c1, rating=Decimal("5"), **base)
        svc.create_brew_session(db, by_user_id=uid, coffee_id=c2, rating=Decimal("2"), **base)

    with SessionLocal() as db:
        only_c1 = svc.list_brew_sessions(db, by_user_id=uid, coffee_id=c1)
        high = svc.list_brew_sessions(db, by_user_id=uid, rating_min=Decimal("4"))
    assert len(only_c1) == 1
    assert only_c1[0].coffee_id == c1
    assert len(high) == 1
    assert high[0].rating == Decimal("5")
