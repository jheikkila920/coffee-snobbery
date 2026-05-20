"""Service-layer tests for plan 06-01 — analytics.py (the home page brain).

Covers all HOME-01..05, HOME-07, HOME-08 derivations, the cold-start gate
counts, signature determinism, and the all-unrated edge case (D-05).

Mirrors the structural shape of tests/services/test_brew_sessions_service.py:
real Postgres via the ``_require_postgres`` + ``_require_analytics_tables``
skip gates, the ``SessionLocal`` context-manager pattern, and a ``clean_analytics``
fixture that wipes test rows before and after each test.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

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
        pytest.skip("Postgres not reachable — Phase 6 service test needs the DB")


def _require_analytics_tables() -> None:
    """Skip if the brew_sessions table (analytics reads from) is not present."""
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
# Seeding helpers                                                              #
# --------------------------------------------------------------------------- #


def _seed_analytics_scenario(db, *, username: str) -> int:
    """Create a gate-cleared, rating-rich fixture for analytics tests.

    Returns the user id.

    Seeds:
    - 1 user
    - 1 roaster
    - 3 coffees with distinct (origin, process, roast_level), one archived=True left UNBREWED
    - bags with roast_date (varied dates)
    - 1 brewer Equipment row
    - 1 recipe
    - 6 flavor notes
    - Enough brew sessions to satisfy all per-card floors:
      * HOME-01: >=2 rated sessions per coffee (coffee1 + coffee2)
      * HOME-02: >=2 rated sessions per dimension value (origin/process/roaster/roast_level)
      * HOME-03: >=2 rated 4.0+ sessions sharing a descriptor
      * HOME-04: >=2 rated sessions in a freshness bucket (brewed within 0-3 days of roast)
      * HOME-05: >=3 rated sessions on the same (origin x process x brewer x recipe)
      * HOME-08: 1 coffee never brewed + archived coffee excluded
      * cold-start gate: >=3 sessions, >=5 distinct observed flavor notes
    """
    from app.models.bag import Bag
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.equipment import Equipment
    from app.models.flavor_note import FlavorNote
    from app.models.recipe import Recipe
    from app.models.roaster import Roaster
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

    roaster = Roaster(name=f"analyticstest-Roaster-{username}")
    db.add(roaster)
    db.flush()

    # Coffee 1: brewed, rated, used for sweet spots
    coffee1 = Coffee(
        name=f"analyticstest-Coffee1-{username}",
        roaster_id=roaster.id,
        origin="Ethiopia",
        process="washed",
        roast_level="light",
    )
    db.add(coffee1)
    db.flush()

    # Coffee 2: brewed, rated (different roast_level for HOME-02 dimension variety)
    coffee2 = Coffee(
        name=f"analyticstest-Coffee2-{username}",
        roaster_id=roaster.id,
        origin="Colombia",
        process="natural",
        roast_level="medium",
    )
    db.add(coffee2)
    db.flush()

    # Coffee 3: never brewed — should appear in get_unrated_coffees
    coffee3 = Coffee(
        name=f"analyticstest-Coffee3-{username}",
        roaster_id=roaster.id,
        origin="Kenya",
        process="washed",
        roast_level="light",
    )
    db.add(coffee3)
    db.flush()

    # Coffee 4: archived=True, never brewed — must NOT appear in get_unrated_coffees
    coffee_archived = Coffee(
        name=f"analyticstest-CoffeeArchived-{username}",
        roaster_id=roaster.id,
        origin="Brazil",
        process="natural",
        roast_level="dark",
        archived=True,
    )
    db.add(coffee_archived)
    db.flush()

    # Bags with roast_date for HOME-04 freshness buckets
    # bag1: roast_date 3 days before brew → "0-3 days" bucket
    brew_date = date(2026, 3, 10)
    bag1 = Bag(coffee_id=coffee1.id, roast_date=date(2026, 3, 8))  # 2 days fresh
    db.add(bag1)
    db.flush()

    bag2 = Bag(coffee_id=coffee2.id, roast_date=date(2026, 3, 1))  # 9 days fresh
    db.add(bag2)
    db.flush()

    # Brewer + recipe for HOME-05 sweet spots
    brewer = Equipment(type="brewer", brand="Hario", model="V60")
    db.add(brewer)
    db.flush()

    recipe = Recipe(
        name=f"analyticstest-Recipe-{username}",
        dose_grams=15,
        water_grams=250,
        water_temp_c=93,
        grind_setting="22",
    )
    db.add(recipe)
    db.flush()

    # Flavor notes (6 distinct for HOME-03 + cold-start gate)
    fn_names = [
        f"analyticstest-fn-blueberry-{username}",
        f"analyticstest-fn-jasmine-{username}",
        f"analyticstest-fn-chocolate-{username}",
        f"analyticstest-fn-caramel-{username}",
        f"analyticstest-fn-citrus-{username}",
        f"analyticstest-fn-vanilla-{username}",
    ]
    flavor_notes = []
    for fn_name in fn_names:
        fn = FlavorNote(name=fn_name, category="fruit")
        db.add(fn)
        db.flush()
        flavor_notes.append(fn)

    fn_ids_primary = [flavor_notes[0].id, flavor_notes[1].id, flavor_notes[2].id]  # 3 shared notes
    fn_ids_secondary = [flavor_notes[3].id, flavor_notes[4].id]
    fn_ids_all = [fn.id for fn in flavor_notes]

    brew_ts = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)

    # Sessions for coffee1 (Ethiopia/washed/light):
    # 4 rated sessions → satisfies HOME-01 (>=2), HOME-02 (same origin/process/roast/roaster),
    # HOME-05 (>=3 same combo), HOME-04 (bag1 = 0-3 days fresh)
    for i in range(4):
        session = BrewSession(
            user_id=uid,
            coffee_id=coffee1.id,
            bag_id=bag1.id,
            recipe_id=recipe.id,
            brewer_id=brewer.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=Decimal("4.5"),
            flavor_note_ids_observed=fn_ids_primary,
            brewed_at=brew_ts,
        )
        db.add(session)
        db.flush()

    # Sessions for coffee2 (Colombia/natural/medium):
    # 2 rated sessions → satisfies HOME-01 (>=2), HOME-02 different dimension values
    for i in range(2):
        session = BrewSession(
            user_id=uid,
            coffee_id=coffee2.id,
            bag_id=bag2.id,
            recipe_id=recipe.id,
            brewer_id=brewer.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=Decimal("4.0"),
            flavor_note_ids_observed=fn_ids_all,  # includes all 6 flavor notes
            brewed_at=brew_ts,
        )
        db.add(session)
        db.flush()

    db.commit()
    return uid


def _seed_cold_start(db, *, username: str) -> int:
    """Seed a below-gate user: <3 sessions OR <5 distinct flavor notes.

    Returns the user id.
    """
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
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

    coffee = Coffee(name=f"analyticstest-ColdCoffee-{username}")
    db.add(coffee)
    db.flush()

    # Only 2 sessions with 2 distinct notes — gate requires >=3 AND >=5
    session = BrewSession(
        user_id=uid,
        coffee_id=coffee.id,
        dose_grams_actual=Decimal("15"),
        water_grams_actual=Decimal("250"),
        rating=None,
        flavor_note_ids_observed=[1, 2],  # only 2 distinct notes
        brewed_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.add(session)
    db.flush()

    db.commit()
    return uid


def _seed_all_unrated(db, *, username: str) -> int:
    """Seed a user who clears the gate (>=3 sessions, >=5 notes) but has NO rated sessions.

    Returns the user id.
    """
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.flavor_note import FlavorNote
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

    coffee = Coffee(name=f"analyticstest-UnratedCoffee-{username}")
    db.add(coffee)
    db.flush()

    # Create 5 distinct flavor notes
    fn_ids = []
    for i in range(5):
        fn = FlavorNote(name=f"analyticstest-fn-unrated-{i}-{username}", category="fruit")
        db.add(fn)
        db.flush()
        fn_ids.append(fn.id)

    # 3 sessions, all unrated — gate passes on count+notes but all rating=None
    brew_ts = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    for i in range(3):
        session = BrewSession(
            user_id=uid,
            coffee_id=coffee.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=None,  # explicitly unrated
            flavor_note_ids_observed=fn_ids,
            brewed_at=brew_ts,
        )
        db.add(session)
        db.flush()

    db.commit()
    return uid


# --------------------------------------------------------------------------- #
# Clean fixture                                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture
def clean_analytics() -> Iterator[None]:
    """Wipe analytics test rows before AND after each test (FK-safe order)."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            # brew_sessions references users, coffees, bags, equipment, recipes
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(text("DELETE FROM bags WHERE coffee_id IN (SELECT id FROM coffees WHERE name LIKE 'analyticstest-%')"))
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM equipment WHERE brand IN ('Hario') AND model = 'V60'"))
            conn.execute(text("DELETE FROM recipes WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM flavor_notes WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM roasters WHERE name LIKE 'analyticstest-%'"))
            conn.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'analyticstest-%')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE username LIKE 'analyticstest-%'"))

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# Test stubs — assertions filled in by Task 3                                 #
# --------------------------------------------------------------------------- #


def test_top_coffees(clean_analytics: None) -> None:
    """HOME-01: top 5 coffees by avg rating, min 2 sessions."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_preference_profile(clean_analytics: None) -> None:
    """HOME-02: preference profile by origin/process/roaster/roast_level, min 2 sessions."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_flavor_descriptors(clean_analytics: None) -> None:
    """HOME-03: top-10 flavor descriptors from 4.0+ rated sessions, min 2."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_roast_freshness_buckets(clean_analytics: None) -> None:
    """HOME-04: roast freshness buckets using bags.roast_date, min 2 rated sessions."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_sweet_spots(clean_analytics: None) -> None:
    """HOME-05: top 3 (origin x process x brewer x recipe), min 3 sessions."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_recent_brews(clean_analytics: None) -> None:
    """HOME-07: last 10 sessions ordered brewed_at DESC."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_unrated_coffees(clean_analytics: None) -> None:
    """HOME-08: non-archived coffees this user has never brewed; excludes archived."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_cold_start_counts(clean_analytics: None) -> None:
    """Gate counts: sessions + distinct_notes + gate_open + needed fields."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_signature_determinism(clean_analytics: None) -> None:
    """compute_input_signature returns identical hash across two calls on identical state."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_signature_excludes_free_text(clean_analytics: None) -> None:
    """Signature changes on rating change; does NOT change on notes text change (D-08)."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_signature_order_independent(clean_analytics: None) -> None:
    """Signature is stable: two consecutive calls on same state produce same hash (Pitfall 5)."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_signature_zero_rated_sentinel(clean_analytics: None) -> None:
    """User with zero RATED sessions → signature == analytics._EMPTY_SIGNATURE."""
    _require_postgres()
    _require_analytics_tables()
    pass


def test_all_unrated_returns_empty(clean_analytics: None) -> None:
    """D-05: user past gate but all sessions unrated → aggregate cards empty."""
    _require_postgres()
    _require_analytics_tables()
    pass
