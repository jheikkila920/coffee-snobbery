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
from datetime import UTC, datetime
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


def _seed_analytics_scenario(db, *, username: str) -> tuple[int, int, int]:
    """Create a gate-cleared, rating-rich fixture for analytics tests.

    Returns (user_id, coffee3_id, archived_coffee_id).

    Seeds:
    - 1 user
    - 1 roaster
    - 4 coffees: 2 brewed+rated, 1 never brewed (unrated candidate), 1 archived+never brewed
    - bags (no roast_date — column removed in Phase 15.1 D-16)
    - 1 brewer Equipment row (V60)
    - 1 recipe
    - 6 flavor notes
    - 6 rated brew sessions satisfying all per-card floors:
      * HOME-01: >=2 rated sessions per coffee (coffee1=4, coffee2=2)
      * HOME-02: >=2 rated sessions per dimension value (origin/process/roaster/roast_level)
      * HOME-03: >=2 rated 4.0+ sessions sharing a descriptor
      * HOME-04: >=2 rated sessions in 0-3 days bucket (bag1) and 8-14 days bucket (bag2)
      * HOME-05: >=3 rated sessions on same (Ethiopia/washed/V60/recipe) combo
      * HOME-08: coffee3 never brewed; archived coffee excluded
      * cold-start gate: 6 sessions, 6 distinct observed notes (gate open)
    """
    from app.models.bag import Bag
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.coffee_origin import CoffeeOrigin
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
        origins=[CoffeeOrigin(country="Ethiopia", sort_order=0)],
        process="washed",
        roast_level="light",
    )
    db.add(coffee1)
    db.flush()

    # Coffee 2: brewed, rated (different roast_level for HOME-02 dimension variety)
    coffee2 = Coffee(
        name=f"analyticstest-Coffee2-{username}",
        roaster_id=roaster.id,
        origins=[CoffeeOrigin(country="Colombia", sort_order=0)],
        process="natural",
        roast_level="medium",
    )
    db.add(coffee2)
    db.flush()

    # Coffee 3: never brewed — should appear in get_unrated_coffees
    coffee3 = Coffee(
        name=f"analyticstest-Coffee3-{username}",
        roaster_id=roaster.id,
        origins=[CoffeeOrigin(country="Kenya", sort_order=0)],
        process="washed",
        roast_level="light",
    )
    db.add(coffee3)
    db.flush()

    # Coffee 4: archived=True, never brewed — must NOT appear in get_unrated_coffees
    coffee_archived = Coffee(
        name=f"analyticstest-CoffeeArchived-{username}",
        roaster_id=roaster.id,
        origins=[CoffeeOrigin(country="Brazil", sort_order=0)],
        process="natural",
        roast_level="dark",
        archived=True,
    )
    db.add(coffee_archived)
    db.flush()
    archived_coffee_id = coffee_archived.id

    # Bags — roast_date column removed in Phase 15.1 (D-16)
    bag1 = Bag(coffee_id=coffee1.id)
    db.add(bag1)
    db.flush()

    bag2 = Bag(coffee_id=coffee2.id)
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

    fn_ids_primary = [flavor_notes[0].id, flavor_notes[1].id, flavor_notes[2].id]
    fn_ids_all = [fn.id for fn in flavor_notes]

    brew_ts = datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC)

    # 4 rated sessions for coffee1 (Ethiopia/washed/light) via bag1 (0-3 days fresh)
    # Satisfies HOME-01 (>=2), HOME-02 origin+process+roaster+roast_level,
    # HOME-04 "0-3 days" bucket, HOME-05 (>=3 same combo)
    for _ in range(4):
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

    # 2 rated sessions for coffee2 (Colombia/natural/medium) via bag2 (8-14 days fresh)
    # Satisfies HOME-01 (>=2), HOME-02 different origin/process/roast_level,
    # HOME-04 "8-14 days" bucket
    for _ in range(2):
        session = BrewSession(
            user_id=uid,
            coffee_id=coffee2.id,
            bag_id=bag2.id,
            recipe_id=recipe.id,
            brewer_id=brewer.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=Decimal("4.0"),
            flavor_note_ids_observed=fn_ids_all,  # all 6 notes (for HOME-03 coverage)
            brewed_at=brew_ts,
        )
        db.add(session)
        db.flush()

    db.commit()
    return uid, coffee3.id, archived_coffee_id


def _seed_cold_start(db, *, username: str) -> int:
    """Seed a below-gate user: 1 session, 2 distinct notes (gate requires >=3 AND >=5).

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

    coffee = Coffee(name=f"analyticstest-ColdCoffee-{username}")
    db.add(coffee)
    db.flush()

    # 2 real flavor notes (the gate JOINs flavor_notes, so dangling IDs would
    # count as 0 — seed live rows so the count is an honest 2, still below gate).
    fn_ids = []
    for i in range(2):
        fn = FlavorNote(name=f"analyticstest-fn-cold-{i}-{username}", category="fruit")
        db.add(fn)
        db.flush()
        fn_ids.append(fn.id)

    # 1 session, 2 distinct notes — below both thresholds (3 sessions AND 5 notes)
    session = BrewSession(
        user_id=uid,
        coffee_id=coffee.id,
        dose_grams_actual=Decimal("15"),
        water_grams_actual=Decimal("250"),
        rating=None,
        flavor_note_ids_observed=fn_ids,  # only 2 distinct notes
        brewed_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
    )
    db.add(session)
    db.flush()

    db.commit()
    return uid


def _seed_all_unrated(db, *, username: str) -> int:
    """Seed a user who clears the gate (>=3 sessions, >=5 notes) but has NO rated sessions.

    Returns the user id. Proves D-05: the all-unrated edge case.
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

    # 5 distinct flavor notes to clear the note-count gate
    fn_ids = []
    for i in range(5):
        fn = FlavorNote(name=f"analyticstest-fn-unrated-{i}-{username}", category="fruit")
        db.add(fn)
        db.flush()
        fn_ids.append(fn.id)

    # 3 sessions, all rating=None — gate passes on count+notes, but no rated rows
    brew_ts = datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC)
    for _ in range(3):
        session = BrewSession(
            user_id=uid,
            coffee_id=coffee.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=None,
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


def _require_cafe_logs_table() -> None:
    """Skip if the cafe_logs table is not present (Pitfall 6)."""
    from tests.conftest import _require_cafe_logs_table as _gate

    _gate()


def _seed_cafe_into_scenario(
    db,
    *,
    user_id: int,
    roaster_id: int,
    cafe_name: str,
    flavor_note_ids: list[int],
    origin_country: str | None = None,
    rating: "Decimal | None" = None,
    count: int = 1,
) -> list[int]:
    """Insert CafeLog rows into an existing analytics scenario.

    Returns a list of the inserted cafe_log IDs.
    All rows share the same field values; use multiple calls for variety.
    Unrated rows have rating=None (excluded from signature + preference dims).
    """
    from datetime import UTC, datetime
    from decimal import Decimal

    from app.models.cafe_log import CafeLog

    if rating is None:
        _rating = None
    else:
        _rating = Decimal(str(rating))

    ids = []
    for i in range(count):
        row = CafeLog(
            user_id=user_id,
            roaster_id=roaster_id,
            cafe_name=cafe_name,
            origin_country=origin_country,
            flavor_note_ids=flavor_note_ids,
            rating=_rating,
            logged_at=datetime(2026, 3, 15, 10, i, 0, tzinfo=UTC),
        )
        db.add(row)
        db.flush()
        ids.append(row.id)
    db.commit()
    return ids


@pytest.fixture
def clean_analytics() -> Iterator[None]:
    """Wipe analytics test rows before AND after each test (FK-safe order)."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            # cafe_logs references users — delete first (FK-safe)
            conn.execute(text("DELETE FROM cafe_logs"))
            # brew_sessions references users, coffees, bags, equipment, recipes
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(
                text(
                    "DELETE FROM bags WHERE coffee_id IN "
                    "(SELECT id FROM coffees WHERE name LIKE 'analyticstest-%')"
                )
            )
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'analyticstest-%'"))
            conn.execute(text("DELETE FROM equipment WHERE brand = 'Hario' AND model = 'V60'"))
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
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_top_coffees(clean_analytics: None) -> None:
    """HOME-01: top 5 coffees by avg rating, min 2 rated sessions."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-top")

    with SessionLocal() as db:
        rows = analytics.get_top_coffees(db, uid)

    assert len(rows) <= 5
    assert all(r.session_count >= 2 for r in rows)
    # Sorted avg_rating DESC
    ratings = [float(r.avg_rating) for r in rows]
    assert ratings == sorted(ratings, reverse=True)
    # coffee1 (4.5 avg) must rank above coffee2 (4.0 avg)
    assert len(rows) >= 2
    assert float(rows[0].avg_rating) >= float(rows[-1].avg_rating)


def test_preference_profile(clean_analytics: None) -> None:
    """HOME-02: preference profile by origin/process/roaster/roast_level, min 2 sessions."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-profile")

    with SessionLocal() as db:
        profile = analytics.get_preference_profile(db, uid)

    assert isinstance(profile, dict)
    assert set(profile.keys()) == {"origin", "process", "roaster", "roast_level"}

    for dim, rows in profile.items():
        for row in rows:
            assert row.session_count >= 2, (
                f"Dimension '{dim}' has row with session_count={row.session_count} < 2"
            )

    # Roaster entries must carry the roaster name (label not None or empty)
    roaster_rows = profile["roaster"]
    assert len(roaster_rows) >= 1
    for row in roaster_rows:
        assert row.label is not None
        assert len(row.label) > 0


def test_flavor_descriptors(clean_analytics: None) -> None:
    """HOME-03: top-10 descriptors from 4.0+ rated sessions (observed array), min 2."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-flavors")

    with SessionLocal() as db:
        rows = analytics.get_flavor_descriptors(db, uid)

    assert len(rows) <= 10
    # All returned descriptors must meet the HAVING count>=2 floor (D-07)
    assert all(r.session_count >= 2 for r in rows)
    # We seeded primary notes (blueberry/jasmine/chocolate) in 4 coffee1 sessions rated 4.5
    # and all 6 notes in 2 coffee2 sessions rated 4.0. All qualify at 4.0+ and count>=2.
    assert len(rows) >= 3  # at least the 3 primary notes appear in >=4 sessions each


def test_sweet_spots(clean_analytics: None) -> None:
    """HOME-05: top 3 (origin x process x brewer x recipe), min 3 sessions."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-sweet")

    with SessionLocal() as db:
        rows = analytics.get_sweet_spots(db, uid)

    assert len(rows) <= 3
    assert all(r.session_count >= 3 for r in rows)
    # Results ordered avg_rating DESC
    if len(rows) > 1:
        ratings = [float(r.avg_rating) for r in rows]
        assert ratings == sorted(ratings, reverse=True)
    # We seeded 4 Ethiopia/washed/V60/recipe sessions (avg 4.5) → must appear
    assert len(rows) >= 1
    assert rows[0].origin == "Ethiopia"
    assert rows[0].process == "washed"


def test_recent_brews(clean_analytics: None) -> None:
    """HOME-07: last 10 sessions ordered brewed_at DESC; includes any rating state."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-recent")

    with SessionLocal() as db:
        rows = analytics.get_recent_brews(db, uid)

    assert len(rows) <= 10
    assert len(rows) >= 1
    # All rows must have coffee_name (join to coffees is required)
    assert all(r.coffee_name is not None for r in rows)
    # Rows must be ordered brewed_at DESC (all seeded at same ts, so stable)
    brew_times = [r.brewed_at for r in rows]
    assert brew_times == sorted(brew_times, reverse=True)


def test_unrated_coffees(clean_analytics: None) -> None:
    """HOME-08: non-archived coffees the user never brewed; archived coffee EXCLUDED."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, coffee3_id, archived_coffee_id = _seed_analytics_scenario(
            db, username="analyticstest-unrated"
        )

    with SessionLocal() as db:
        rows = analytics.get_unrated_coffees(db, uid)

    result_ids = {r.id for r in rows}

    # coffee3 (never brewed, not archived) MUST appear
    assert coffee3_id in result_ids, "coffee3 (unbrewed, active) must be in unrated coffees"

    # The archived coffee must NOT appear — proves Coffee.archived==False branch (HOME-08)
    assert archived_coffee_id not in result_ids, (
        "archived coffee must be excluded from get_unrated_coffees (HOME-08)"
    )

    # Coffees that WERE brewed (coffee1, coffee2) must NOT appear
    for row in rows:
        assert "Coffee1" not in row.name, f"Brewed coffee1 appeared in unrated_coffees: {row.name}"
        assert "Coffee2" not in row.name, f"Brewed coffee2 appeared in unrated_coffees: {row.name}"


def test_cold_start_counts(clean_analytics: None) -> None:
    """Gate counts: sessions + distinct_notes + gate_open + needed fields."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    # Below-gate scenario
    with SessionLocal() as db:
        cold_uid = _seed_cold_start(db, username="analyticstest-cold")

    with SessionLocal() as db:
        counts = analytics.get_cold_start_counts(db, cold_uid)

    assert set(counts.keys()) >= {
        "sessions",
        "distinct_notes",
        "gate_open",
        "sessions_needed",
        "notes_needed",
    }
    assert counts["gate_open"] is False
    assert counts["sessions"] == 1
    assert counts["sessions_needed"] == 2  # needs 2 more to reach the 3 threshold

    # Gate-cleared scenario
    with SessionLocal() as db:
        gate_uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-gate")

    with SessionLocal() as db:
        gate_counts = analytics.get_cold_start_counts(db, gate_uid)

    assert gate_counts["gate_open"] is True
    assert gate_counts["sessions"] >= 3  # 6 sessions seeded
    assert gate_counts["distinct_notes"] >= 5  # 6 distinct notes seeded
    assert gate_counts["sessions_needed"] == 0
    assert gate_counts["notes_needed"] == 0

    # Confirm the cold-start count INCLUDES unrated sessions (D-09 note)
    # cold_uid's 1 session had rating=None and was still counted as sessions==1
    # This is already verified above (counts["sessions"] == 1 for an unrated session)


def test_all_unrated_returns_empty(clean_analytics: None) -> None:
    """D-05: user past gate but all sessions unrated → rating-dependent cards empty."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid = _seed_all_unrated(db, username="analyticstest-allunrated")

    with SessionLocal() as db:
        gate_counts = analytics.get_cold_start_counts(db, uid)
        top_coffees = analytics.get_top_coffees(db, uid)
        profile = analytics.get_preference_profile(db, uid)
        descriptors = analytics.get_flavor_descriptors(db, uid)
        sweet_spots = analytics.get_sweet_spots(db, uid)

    # Gate is OPEN (3 sessions, 5 notes) — but all unrated
    assert gate_counts["gate_open"] is True
    assert gate_counts["sessions"] == 3

    # Rating-dependent cards return empty (all WHERE rating IS NOT NULL → no rows)
    assert top_coffees == []
    assert profile["origin"] == []
    assert profile["process"] == []
    assert profile["roaster"] == []
    assert profile["roast_level"] == []
    assert descriptors == []
    assert sweet_spots == []


def test_signature_determinism(clean_analytics: None) -> None:
    """compute_input_signature returns identical hash on two separate calls."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-sigdet")

    with SessionLocal() as db:
        sig1 = analytics.compute_input_signature(db, uid)

    with SessionLocal() as db:
        sig2 = analytics.compute_input_signature(db, uid)

    assert sig1 == sig2, "Signature must be deterministic across calls on identical DB state"
    assert len(sig1) == 64  # SHA256 hex digest


def test_signature_excludes_unrated_sessions(clean_analytics: None) -> None:
    """D-09: only RATED sessions feed compute_input_signature.

    Adding an UNRATED (rating=None) session must NOT change the signature — it is
    invisible to the canonical payload. Once that same session is given a rating,
    it MUST change the signature, because rating it makes it an AI-input row.

    Within-user determinism / "order-independence" is covered separately by
    ``test_signature_determinism``: the signature is intentionally id-ordered
    (``ORDER BY BrewSession.id``), not a cross-user order-independent property.
    """
    _require_postgres()
    _require_analytics_tables()

    from sqlalchemy import select, update

    from app.db import SessionLocal
    from app.models.bag import Bag
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.equipment import Equipment
    from app.models.recipe import Recipe
    from app.services import analytics

    username = "analyticstest-sigunrated"

    # 1. Seed a gate-open user with a rating-rich scenario.
    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username=username)

    # 2. Baseline signature over only the rated sessions.
    with SessionLocal() as db:
        sig_baseline = analytics.compute_input_signature(db, uid)

    # 3. Add ONE new UNRATED session, reusing scenario catalog rows so the row is
    #    valid (coffee1 + its bag + the seeded recipe + the V60 brewer).
    with SessionLocal() as db:
        coffee_id = db.scalar(
            select(Coffee.id).where(Coffee.name == f"analyticstest-Coffee1-{username}")
        )
        bag_id = db.scalar(select(Bag.id).where(Bag.coffee_id == coffee_id))
        recipe_id = db.scalar(
            select(Recipe.id).where(Recipe.name == f"analyticstest-Recipe-{username}")
        )
        brewer_id = db.scalar(
            select(Equipment.id).where(Equipment.brand == "Hario", Equipment.model == "V60")
        )

        unrated = BrewSession(
            user_id=uid,
            coffee_id=coffee_id,
            bag_id=bag_id,
            recipe_id=recipe_id,
            brewer_id=brewer_id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=None,  # D-09: unrated → excluded from the signature
            flavor_note_ids_observed=[],
            brewed_at=datetime(2026, 3, 11, 10, 0, 0, tzinfo=UTC),
        )
        db.add(unrated)
        db.flush()
        unrated_id = unrated.id
        db.commit()

    # 4. Unrated session must be invisible to the signature (D-09).
    with SessionLocal() as db:
        sig_after_unrated = analytics.compute_input_signature(db, uid)

    assert sig_after_unrated == sig_baseline, (
        "Adding an UNRATED session must NOT change the signature (D-09: rated sessions only)"
    )

    # 5. Rate that same session.
    with SessionLocal() as db:
        db.execute(
            update(BrewSession).where(BrewSession.id == unrated_id).values(rating=Decimal("4.0"))
        )
        db.commit()

    # 6. Now-rated session MUST change the signature vs baseline (D-09).
    with SessionLocal() as db:
        sig_after_rating = analytics.compute_input_signature(db, uid)

    assert sig_after_rating != sig_baseline, (
        "Rating a previously-unrated session MUST change the signature "
        "(D-09: it is now an AI-input row)"
    )


def test_signature_excludes_free_text(clean_analytics: None) -> None:
    """Signature unchanged by notes-text edit; changes when rating changes (D-08)."""
    _require_postgres()
    _require_analytics_tables()
    from sqlalchemy import update

    from app.db import SessionLocal
    from app.models.brew_session import BrewSession
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-sigtext")

    with SessionLocal() as db:
        sig_baseline = analytics.compute_input_signature(db, uid)

    # Change notes text (excluded from signature per D-08)
    with SessionLocal() as db:
        db.execute(
            update(BrewSession)
            .where(BrewSession.user_id == uid)
            .values(notes="Changed notes — excluded from signature")
        )
        db.commit()

    with SessionLocal() as db:
        sig_after_notes = analytics.compute_input_signature(db, uid)

    assert sig_baseline == sig_after_notes, (
        "Changing notes text must NOT change the signature (D-08 free-text exclusion)"
    )

    # Change rating (included in signature per D-08)
    with SessionLocal() as db:
        db.execute(
            update(BrewSession).where(BrewSession.user_id == uid).values(rating=Decimal("3.0"))
        )
        db.commit()

    with SessionLocal() as db:
        sig_after_rating = analytics.compute_input_signature(db, uid)

    assert sig_baseline != sig_after_rating, (
        "Changing rating MUST change the signature (D-08: rating is an AI-input field)"
    )


def test_signature_zero_rated_sentinel(clean_analytics: None) -> None:
    """User with zero RATED sessions → signature == analytics._EMPTY_SIGNATURE."""
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid = _seed_all_unrated(db, username="analyticstest-sentinel")

    with SessionLocal() as db:
        sig = analytics.compute_input_signature(db, uid)

    assert sig == analytics._EMPTY_SIGNATURE, (
        f"User with zero rated sessions must return _EMPTY_SIGNATURE; got {sig!r}"
    )


# --------------------------------------------------------------------------- #
# NEW CAFE-AWARE TESTS (Plan 16-05: D-12 / D-13 / D-14 / D-15 / D-16)        #
# --------------------------------------------------------------------------- #


def test_signature_includes_cafe_logs(clean_analytics: None) -> None:
    """D-12: adding a rated CafeLog mutates compute_input_signature."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-siginc")
        sig_before = analytics.compute_input_signature(db, uid)

    # Insert a rated CafeLog for the same user — must mutate the signature.
    with SessionLocal() as db:
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Signature-Change Cafe",
            flavor_note_ids=[],
            origin_country="Panama",
            rating=Decimal("4.0"),
        )

    with SessionLocal() as db:
        sig_after = analytics.compute_input_signature(db, uid)

    assert sig_after != sig_before, (
        "Adding a rated CafeLog MUST change the signature (D-12: cafe rows in payload)"
    )


def test_signature_excludes_unrated_cafe(clean_analytics: None) -> None:
    """D-12: adding an UNRATED CafeLog must NOT change compute_input_signature."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-signorating")
        sig_before = analytics.compute_input_signature(db, uid)

    # Insert an UNRATED CafeLog — must NOT mutate the signature.
    with SessionLocal() as db:
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Unrated Cafe",
            flavor_note_ids=[],
            origin_country=None,
            rating=None,  # unrated → excluded from signature payload
        )

    with SessionLocal() as db:
        sig_after = analytics.compute_input_signature(db, uid)

    assert sig_after == sig_before, (
        "Adding an UNRATED CafeLog must NOT change the signature "
        "(D-12: CafeLog.rating.is_not(None) filter required)"
    )


def test_preference_profile_origin_unions_cafe(clean_analytics: None) -> None:
    """D-13: get_preference_profile['origin'] includes cafe origin_country rows."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-proforigin")
        # Seed 2 rated CafeLogs with origin_country='Costa Rica' — absent from brew side.
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="CR Cafe",
            flavor_note_ids=[],
            origin_country="Costa Rica",
            rating=Decimal("4.0"),
            count=2,
        )

    with SessionLocal() as db:
        profile = analytics.get_preference_profile(db, uid)

    origin_labels = [r.label for r in profile["origin"]]
    assert "Costa Rica" in origin_labels, (
        "get_preference_profile['origin'] must include 'Costa Rica' from cafe logs (D-13)"
    )
    cr_row = next(r for r in profile["origin"] if r.label == "Costa Rica")
    assert cr_row.session_count == 2, (
        f"Costa Rica session_count should be 2 (both cafe rows); got {cr_row.session_count}"
    )


def test_preference_profile_roaster_unions_cafe(clean_analytics: None) -> None:
    """D-13: get_preference_profile['roaster'] count increases when cafe logs share roaster."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.roaster import Roaster
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-profroaster")
        # Get the seeded roaster id (analyticstest-Roaster-<username>)
        roaster_id = db.scalar(
            select(Roaster.id).where(
                Roaster.name == "analyticstest-Roaster-analyticstest-profroaster"
            )
        )
        # Brew-only baseline count for this roaster
        profile_before = analytics.get_preference_profile(db, uid)
        brew_roaster_rows = profile_before["roaster"]
        brew_count = next(
            (r.session_count for r in brew_roaster_rows if r.label is not None),
            0,
        )

        # Seed 2 rated CafeLogs pointing at the same roaster.
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=roaster_id,
            cafe_name="Roaster Union Cafe",
            flavor_note_ids=[],
            origin_country=None,
            rating=Decimal("4.5"),
            count=2,
        )

    with SessionLocal() as db:
        profile_after = analytics.get_preference_profile(db, uid)

    roaster_row = next(
        (r for r in profile_after["roaster"] if r.label is not None), None
    )
    assert roaster_row is not None, "Roaster row must exist in profile after cafe logs added"
    assert roaster_row.session_count > brew_count, (
        f"Roaster session_count must increase after cafe log union; "
        f"brew_only={brew_count}, after_union={roaster_row.session_count}"
    )


def test_preference_profile_process_brew_only(clean_analytics: None) -> None:
    """D-13: process + roast_level dims are UNCHANGED when a rated CafeLog is added."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-processonly")
        # Baseline before cafe insertion
        profile_before = analytics.get_preference_profile(db, uid)
        process_before = [(r.label, r.session_count) for r in profile_before["process"]]
        roast_before = [(r.label, r.session_count) for r in profile_before["roast_level"]]

        # Insert a rated CafeLog — should not affect process or roast_level.
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Process-Neutral Cafe",
            flavor_note_ids=[],
            origin_country="Ethiopia",
            rating=Decimal("4.0"),
        )

    with SessionLocal() as db:
        profile_after = analytics.get_preference_profile(db, uid)
        process_after = [(r.label, r.session_count) for r in profile_after["process"]]
        roast_after = [(r.label, r.session_count) for r in profile_after["roast_level"]]

    assert process_after == process_before, (
        "process dim must be UNCHANGED after adding a CafeLog (D-13: process stays brew-only)"
    )
    assert roast_after == roast_before, (
        "roast_level dim must be UNCHANGED after adding a CafeLog "
        "(D-13: roast_level stays brew-only)"
    )


def test_flavor_descriptors_unions_cafe(clean_analytics: None) -> None:
    """D-13: get_flavor_descriptors includes notes from rated-4+ cafe logs."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.flavor_note import FlavorNote
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-flavorcafe")
        # Create a NEW flavor note not in the brew scenario.
        new_fn = FlavorNote(name="analyticstest-fn-cafe-mango", category="fruit")
        db.add(new_fn)
        db.flush()
        new_fn_id = new_fn.id

        # Get one existing brew-side note id to test that it accumulates counts.
        existing_fn_id = db.scalar(
            select(FlavorNote.id).where(
                FlavorNote.name == "analyticstest-fn-blueberry-analyticstest-flavorcafe"
            )
        )

        # Seed 2 rated-4.5 CafeLogs: one with the new note, one with an existing note.
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Cafe Mango",
            flavor_note_ids=[new_fn_id],
            rating=Decimal("4.5"),
            count=2,  # >=2 appearances to clear the HAVING count>=2 floor
        )
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Cafe Blueberry",
            flavor_note_ids=[existing_fn_id],
            rating=Decimal("4.5"),
            count=2,
        )
        db.commit()

    with SessionLocal() as db:
        rows = analytics.get_flavor_descriptors(db, uid)

    note_ids = {r.id for r in rows}
    assert new_fn_id in note_ids, (
        "A flavor note appearing only in cafe logs (rated 4+) must surface in "
        "get_flavor_descriptors (D-13: UNION ALL of brew + cafe unnest blocks)"
    )
    assert existing_fn_id in note_ids, (
        "An existing brew-side note must still appear after cafe UNION"
    )


def test_cold_start_brew_only(clean_analytics: None) -> None:
    """D-15: 3 brews + 5 notes + 0 cafe logs → gate_open == True, sessions == 3."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal
    from datetime import UTC, datetime

    from app.db import SessionLocal
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.flavor_note import FlavorNote
    from app.models.user import User
    from app.services import analytics

    username = "analyticstest-csbrewonly"
    with SessionLocal() as db:
        user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
        db.add(user)
        db.flush()
        uid = user.id

        coffee = Coffee(name=f"analyticstest-ColdBrew-{username}")
        db.add(coffee)
        db.flush()

        fn_ids = []
        for i in range(5):
            fn = FlavorNote(name=f"analyticstest-fn-csb-{i}-{username}", category="fruit")
            db.add(fn)
            db.flush()
            fn_ids.append(fn.id)

        brew_ts = datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC)
        for _ in range(3):
            session = BrewSession(
                user_id=uid,
                coffee_id=coffee.id,
                dose_grams_actual=Decimal("15"),
                water_grams_actual=Decimal("250"),
                rating=None,
                flavor_note_ids_observed=fn_ids,
                brewed_at=brew_ts,
            )
            db.add(session)
            db.flush()
        db.commit()

    with SessionLocal() as db:
        counts = analytics.get_cold_start_counts(db, uid)

    assert counts["gate_open"] is True, (
        f"Gate must be open for 3 brews + 5 notes; got {counts}"
    )
    assert counts["sessions"] == 3, (
        f"sessions must be 3 (brew_count=3, cafe_count=0); got {counts['sessions']}"
    )
    assert counts["distinct_notes"] >= 5


def test_cold_start_cafe_only(clean_analytics: None) -> None:
    """D-15: 0 brews + 3 rated cafe logs covering 5 distinct notes → gate_open == True."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from app.db import SessionLocal
    from app.models.flavor_note import FlavorNote
    from app.models.user import User
    from app.services import analytics

    username = "analyticstest-cscafeonly"
    with SessionLocal() as db:
        user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
        db.add(user)
        db.flush()
        uid = user.id

        fn_ids = []
        for i in range(5):
            fn = FlavorNote(name=f"analyticstest-fn-csc-{i}-{username}", category="fruit")
            db.add(fn)
            db.flush()
            fn_ids.append(fn.id)
        db.commit()

        # 3 rated cafe logs, each covering all 5 notes.
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Cafe Only Log",
            flavor_note_ids=fn_ids,
            rating=Decimal("4.0"),
            count=3,
        )

    with SessionLocal() as db:
        counts = analytics.get_cold_start_counts(db, uid)

    assert counts["gate_open"] is True, (
        f"Gate must be open for 3 rated cafe logs + 5 notes; got {counts}"
    )
    assert counts["sessions"] == 3, (
        f"sessions must be 3 (brew_count=0, cafe_count=3); got {counts['sessions']}"
    )
    assert counts["distinct_notes"] >= 5


def test_cold_start_mixed(clean_analytics: None) -> None:
    """D-15: 1 brew + 2 cafe logs spanning 5 distinct notes → sessions == 3, gate_open."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal
    from datetime import UTC, datetime

    from app.db import SessionLocal
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.flavor_note import FlavorNote
    from app.models.user import User
    from app.services import analytics

    username = "analyticstest-csmixed"
    with SessionLocal() as db:
        user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
        db.add(user)
        db.flush()
        uid = user.id

        coffee = Coffee(name=f"analyticstest-ColdMix-{username}")
        db.add(coffee)
        db.flush()

        # 5 distinct flavor notes — split between brew and cafe to test UNION.
        fn_ids = []
        for i in range(5):
            fn = FlavorNote(name=f"analyticstest-fn-csm-{i}-{username}", category="fruit")
            db.add(fn)
            db.flush()
            fn_ids.append(fn.id)

        # 1 brew session with the first 3 notes.
        session = BrewSession(
            user_id=uid,
            coffee_id=coffee.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=None,
            flavor_note_ids_observed=fn_ids[:3],
            brewed_at=datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC),
        )
        db.add(session)
        db.flush()
        db.commit()

        # 2 rated cafe logs with the last 2 notes (new notes only, total=5 distinct).
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Mixed Cafe",
            flavor_note_ids=fn_ids[3:],  # last 2 notes
            rating=Decimal("4.0"),
            count=2,
        )

    with SessionLocal() as db:
        counts = analytics.get_cold_start_counts(db, uid)

    assert counts["sessions"] == 3, (
        f"sessions must be 3 (1 brew + 2 cafe); got {counts['sessions']}"
    )
    assert counts["gate_open"] is True, (
        f"Gate must be open for 1 brew + 2 cafe + 5 distinct notes; got {counts}"
    )
    assert counts["distinct_notes"] >= 5


def test_sweet_spots_excludes_cafe(clean_analytics: None) -> None:
    """D-16: inserting a CafeLog does NOT affect get_sweet_spots output (body unchanged)."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-sweetcafe")
        # Baseline sweet spots from brew sessions only.
        sweet_before = analytics.get_sweet_spots(db, uid)
        # Insert a CafeLog whose origin/roaster would affect sweet_spots IF UNIONed.
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Sweet Spot Intruder",
            flavor_note_ids=[],
            origin_country="Ethiopia",  # same origin as the top sweet spot
            rating=Decimal("4.5"),
            count=3,  # would cross the >=3 floor if accidentally UNIONed
        )

    with SessionLocal() as db:
        sweet_after = analytics.get_sweet_spots(db, uid)

    # Results must be bit-identical.
    assert len(sweet_before) == len(sweet_after), (
        "get_sweet_spots row count must not change after inserting a CafeLog (D-16)"
    )
    for before, after in zip(sweet_before, sweet_after):
        assert before.session_count == after.session_count, (
            "get_sweet_spots session_count must be UNCHANGED (D-16: cafe excluded)"
        )
        assert float(before.avg_rating) == float(after.avg_rating), (
            "get_sweet_spots avg_rating must be UNCHANGED (D-16: cafe excluded)"
        )


def test_top_coffees_excludes_cafe(clean_analytics: None) -> None:
    """D-14: inserting a high-rated CafeLog does NOT affect get_top_coffees output."""
    _require_postgres()
    _require_analytics_tables()
    _require_cafe_logs_table()
    from decimal import Decimal

    from app.db import SessionLocal
    from app.services import analytics

    with SessionLocal() as db:
        uid, _c3, _ca = _seed_analytics_scenario(db, username="analyticstest-topcafe")
        top_before = analytics.get_top_coffees(db, uid)
        top_before_ids = [r.id for r in top_before]

        # Insert a high-rated CafeLog — its cafe_name has no coffees.id, so the
        # JOIN to coffees table naturally excludes it. This test verifies that.
        _seed_cafe_into_scenario(
            db,
            user_id=uid,
            roaster_id=None,
            cafe_name="Top Coffee Intruder",
            flavor_note_ids=[],
            rating=Decimal("5.0"),  # maximum rating
            count=4,  # would rank #1 if accidentally UNIONed
        )

    with SessionLocal() as db:
        top_after = analytics.get_top_coffees(db, uid)
        top_after_ids = [r.id for r in top_after]

    assert top_before_ids == top_after_ids, (
        "get_top_coffees must return IDENTICAL coffee IDs after inserting a CafeLog "
        "(D-14: cafe coffees have no coffees.id row)"
    )
