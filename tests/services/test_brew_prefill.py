"""Service-layer tests for plan 05-02 Task 2 — prefill resolution (D-04/05/06/08).

Covers the ``<behavior>`` cases from the plan:

* D-04 open-form default: ``resolve_prefill`` returns the last session's
  carryable fields and BLANK rating / flavor_notes / notes.
* D-04 hybrid: passing ``coffee_id`` re-sources from the last session WITH
  that coffee.
* D-05 recipe-wins: ``recipe_id`` makes dose/water/temp/grind come from the
  recipe, overriding last-session values.
* D-06 newest-open-bag: ``bag_id`` defaults to the most-recently-opened bag
  with ``finished_at IS NULL``; ``None`` when none open.
* D-08 brew-again: ``from_session_id`` sources from that session (user-scoped)
  and explicitly blanks rating / observed notes / notes; a no-longer-active bag
  drops to ``None``.

Uses the real-Postgres skip-gate + clean-fixture shape from
``tests/services/test_brew_sessions_service.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

# --------------------------------------------------------------------------- #
# Skip gates + seeding (shared shape with test_brew_sessions_service.py)      #
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


def _seed_user(db, *, username: str):
    from app.models.user import User

    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user


def _seed_coffee(db, *, name: str):
    from app.models.coffee import Coffee

    coffee = Coffee(name=name)
    db.add(coffee)
    db.flush()
    return coffee


def _seed_bag(db, *, coffee_id: int, opened_at, finished_at=None):
    from app.models.bag import Bag

    bag = Bag(coffee_id=coffee_id, opened_at=opened_at, finished_at=finished_at)
    db.add(bag)
    db.flush()
    return bag


def _seed_recipe(db, *, name: str, dose, water, temp, grind):
    from app.models.recipe import Recipe

    recipe = Recipe(
        name=name,
        dose_grams=dose,
        water_grams=water,
        water_temp_c=temp,
        grind_setting=grind,
    )
    db.add(recipe)
    db.flush()
    return recipe


@pytest.fixture
def clean_brew() -> Iterator[None]:
    """Wipe Phase-5 rows + the prefill test fixtures before AND after."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(
                text(
                    "DELETE FROM bags WHERE coffee_id IN "
                    "(SELECT id FROM coffees WHERE name LIKE 'Prefill Coffee%')"
                )
            )
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'Prefill Coffee%'"))
            conn.execute(text("DELETE FROM recipes WHERE name LIKE 'Prefill Recipe%'"))
            conn.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'prefill-%')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE username LIKE 'prefill-%'"))

    _reset()
    yield
    _reset()


def _create_session(svc, db, *, by_user_id, coffee_id, brewed_at, **over):
    base = dict(
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
        rating=Decimal("4"),
        flavor_note_ids_observed=[1, 2],
        notes="great cup",
    )
    base.update(over)
    return svc.create_brew_session(
        db, by_user_id=by_user_id, coffee_id=coffee_id, brewed_at=brewed_at, **base
    )


# --------------------------------------------------------------------------- #
# D-04 open-form default                                                       #
# --------------------------------------------------------------------------- #


def test_d04_open_form_default_carries_and_blanks(clean_brew: None) -> None:
    """Open-form prefill carries last-session fields; blanks per-attempt fields."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-d04")
        coffee = _seed_coffee(db, name="Prefill Coffee A")
        db.commit()
        uid, cid = user.id, coffee.id

    with SessionLocal() as db:
        _create_session(
            svc,
            db,
            by_user_id=uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            water_type="Spring",
            dose_grams_actual=Decimal("18"),
        )

    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=uid)

    assert pf["coffee_id"] == cid
    assert pf["water_type"] == "Spring"
    assert pf["dose_grams_actual"] == Decimal("18")
    # per-attempt fields are blanked.
    assert pf["rating"] is None
    assert pf["flavor_note_ids_observed"] == []
    assert pf["notes"] == ""


def test_d04_no_history_returns_blanks(clean_brew: None) -> None:
    """No prior session → carryable fields None, per-attempt blanked."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-empty")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=uid)
    assert pf["coffee_id"] is None
    assert pf["rating"] is None
    assert pf["flavor_note_ids_observed"] == []
    assert pf["notes"] == ""


def test_d04_hybrid_resources_from_last_session_with_coffee(clean_brew: None) -> None:
    """Passing coffee_id re-sources from the last session WITH that coffee."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-hybrid")
        coffee_a = _seed_coffee(db, name="Prefill Coffee A")
        coffee_b = _seed_coffee(db, name="Prefill Coffee B")
        db.commit()
        uid, ca, cb = user.id, coffee_a.id, coffee_b.id

    now = datetime.now(UTC)
    with SessionLocal() as db:
        # Older session with coffee A; newer (most recent) with coffee B.
        _create_session(
            svc,
            db,
            by_user_id=uid,
            coffee_id=ca,
            brewed_at=now - timedelta(days=2),
            grind_setting_actual="A-grind",
        )
        _create_session(
            svc,
            db,
            by_user_id=uid,
            coffee_id=cb,
            brewed_at=now,
            grind_setting_actual="B-grind",
        )

    # Open-form default → most recent (coffee B).
    with SessionLocal() as db:
        default_pf = svc.resolve_prefill(db, by_user_id=uid)
    assert default_pf["coffee_id"] == cb
    assert default_pf["grind_setting_actual"] == "B-grind"

    # User switches to coffee A → re-source from last session with A.
    with SessionLocal() as db:
        a_pf = svc.resolve_prefill(db, by_user_id=uid, coffee_id=ca)
    assert a_pf["coffee_id"] == ca
    assert a_pf["grind_setting_actual"] == "A-grind"


# --------------------------------------------------------------------------- #
# D-05 recipe-wins                                                            #
# --------------------------------------------------------------------------- #


def test_d05_recipe_wins_over_last_session(clean_brew: None) -> None:
    """recipe_id overrides dose/water/temp/grind; other fields from last session."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-d05")
        coffee = _seed_coffee(db, name="Prefill Coffee A")
        recipe = _seed_recipe(
            db,
            name="Prefill Recipe Kasuya",
            dose=20,
            water=300,
            temp=88,
            grind="recipe-grind",
        )
        db.commit()
        uid, cid, rid = user.id, coffee.id, recipe.id

    with SessionLocal() as db:
        _create_session(
            svc,
            db,
            by_user_id=uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            water_type="Spring",
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            water_temp_c_actual=Decimal("93"),
            grind_setting_actual="session-grind",
        )

    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=uid, recipe_id=rid)

    # The four template fields come from the recipe.
    assert pf["recipe_id"] == rid
    assert pf["dose_grams_actual"] == 20
    assert pf["water_grams_actual"] == 300
    assert pf["water_temp_c_actual"] == 88
    assert pf["grind_setting_actual"] == "recipe-grind"
    # Non-template fields still come from last session.
    assert pf["water_type"] == "Spring"
    assert pf["coffee_id"] == cid


def test_d05_unknown_recipe_keeps_last_session(clean_brew: None) -> None:
    """A missing recipe_id leaves the four template fields from last session."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-d05-miss")
        coffee = _seed_coffee(db, name="Prefill Coffee A")
        db.commit()
        uid, cid = user.id, coffee.id

    with SessionLocal() as db:
        _create_session(
            svc,
            db,
            by_user_id=uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            grind_setting_actual="session-grind",
        )

    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=uid, recipe_id=999999)
    # recipe_id is echoed but targets are None → last-session grind stands.
    assert pf["grind_setting_actual"] == "session-grind"


# --------------------------------------------------------------------------- #
# D-06 newest open bag                                                        #
# --------------------------------------------------------------------------- #


def test_d06_newest_open_bag_defaults(clean_brew: None) -> None:
    """bag_id defaults to the most-recently-opened bag with finished_at NULL."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-d06")
        coffee = _seed_coffee(db, name="Prefill Coffee A")
        db.flush()
        # older open bag, newer open bag, and a finished bag (newest opened).
        _seed_bag(db, coffee_id=coffee.id, opened_at=now - timedelta(days=5))
        newer = _seed_bag(db, coffee_id=coffee.id, opened_at=now - timedelta(days=1))
        _seed_bag(
            db,
            coffee_id=coffee.id,
            opened_at=now,
            finished_at=now,
        )
        db.commit()
        uid, cid, newer_id = user.id, coffee.id, newer.id

    # newest_open_bag_id directly.
    with SessionLocal() as db:
        assert svc.newest_open_bag_id(db, coffee_id=cid) == newer_id

    # resolve_prefill applies D-06 when a coffee is resolved and bag unset.
    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=uid, coffee_id=cid)
    assert pf["bag_id"] == newer_id


def test_d06_no_open_bag_is_none(clean_brew: None) -> None:
    """A coffee with no open bag → bag_id None."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-d06-none")
        coffee = _seed_coffee(db, name="Prefill Coffee A")
        db.flush()
        _seed_bag(db, coffee_id=coffee.id, opened_at=now, finished_at=now)
        db.commit()
        uid, cid = user.id, coffee.id

    with SessionLocal() as db:
        assert svc.newest_open_bag_id(db, coffee_id=cid) is None
    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=uid, coffee_id=cid)
    assert pf["bag_id"] is None


# --------------------------------------------------------------------------- #
# D-08 brew-again                                                             #
# --------------------------------------------------------------------------- #


def test_brew_again_blanks_per_attempt(clean_brew: None) -> None:
    """from_session_id sources that session and blanks rating/observed/notes."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-d08")
        coffee_old = _seed_coffee(db, name="Prefill Coffee A")
        coffee_src = _seed_coffee(db, name="Prefill Coffee B")
        db.commit()
        uid, c_old, c_src = user.id, coffee_old.id, coffee_src.id

    with SessionLocal() as db:
        # A more-recent session (would win D-04) on a different coffee.
        _create_session(svc, db, by_user_id=uid, coffee_id=c_old, brewed_at=now)
        # The source session (older) we will brew-again from.
        src = _create_session(
            svc,
            db,
            by_user_id=uid,
            coffee_id=c_src,
            brewed_at=now - timedelta(days=3),
            water_type="Distilled",
            dose_grams_actual=Decimal("16"),
            rating=Decimal("5"),
            flavor_note_ids_observed=[3, 4],
            notes="source notes",
        )
        src_id = src.id

    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=uid, from_session_id=src_id)

    # D-08 overrides D-04: source is the named session, not the most recent.
    assert pf["coffee_id"] == c_src
    assert pf["water_type"] == "Distilled"
    assert pf["dose_grams_actual"] == Decimal("16")
    # per-attempt fields explicitly blanked.
    assert pf["rating"] is None
    assert pf["flavor_note_ids_observed"] == []
    assert pf["notes"] == ""


def test_brew_again_is_user_scoped(clean_brew: None) -> None:
    """from_session_id for another user's session yields no carry (IDOR)."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        user_a = _seed_user(db, username="prefill-d08-a")
        user_b = _seed_user(db, username="prefill-d08-b")
        coffee = _seed_coffee(db, name="Prefill Coffee A")
        db.commit()
        a_id, b_id, cid = user_a.id, user_b.id, coffee.id

    with SessionLocal() as db:
        a_src = _create_session(
            svc,
            db,
            by_user_id=a_id,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            water_type="Spring",
        )
        a_src_id = a_src.id

    # User B brews-again from A's session id → not found → no coffee carried.
    with SessionLocal() as db:
        pf = svc.resolve_prefill(db, by_user_id=b_id, from_session_id=a_src_id)
    assert pf["coffee_id"] is None
    assert pf["water_type"] is None


def test_brew_again_drops_finished_bag(clean_brew: None) -> None:
    """A source bag that is no longer active drops to None on brew-again."""
    _require_postgres()
    _require_p5_migration_applied()
    from sqlalchemy import text

    from app.db import SessionLocal, engine
    from app.services import brew_sessions as svc

    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = _seed_user(db, username="prefill-d08-bag")
        coffee = _seed_coffee(db, name="Prefill Coffee A")
        db.flush()
        bag = _seed_bag(db, coffee_id=coffee.id, opened_at=now)
        db.commit()
        uid, cid, bag_id = user.id, coffee.id, bag.id

    with SessionLocal() as db:
        src = _create_session(svc, db, by_user_id=uid, coffee_id=cid, brewed_at=now, bag_id=bag_id)
        src_id = src.id

    # While the bag is open, brew-again keeps it.
    with SessionLocal() as db:
        pf_open = svc.resolve_prefill(db, by_user_id=uid, from_session_id=src_id)
    assert pf_open["bag_id"] == bag_id

    # Finish the bag → brew-again drops it (and D-06 finds no other open bag).
    with engine.begin() as conn:
        conn.execute(text("UPDATE bags SET finished_at = now() WHERE id = :i"), {"i": bag_id})

    with SessionLocal() as db:
        pf_finished = svc.resolve_prefill(db, by_user_id=uid, from_session_id=src_id)
    assert pf_finished["bag_id"] is None
