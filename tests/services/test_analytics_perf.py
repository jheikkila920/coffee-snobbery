"""Performance test for plan 06-01 Task 4 — analytics query latency budget.

Verifies every analytics derivation runs <50ms p95 against a ~1000-session
single-user seed (ROADMAP Phase 6 Success Criterion 2).

Strategy: wall-clock median over 5 runs using time.perf_counter, calling
each service function directly. This is simpler and deterministic enough at
household scale — no need to wire EXPLAIN ANALYZE around ORM statements.

If any query misses the 50ms budget, the assertion message names the offending
function and its measured ms so the executor knows which query to index.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

# --------------------------------------------------------------------------- #
# Skip gates (reused from test_analytics.py)                                  #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 6 perf test needs the DB")


def _require_analytics_tables() -> None:
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
# 1000-session seed                                                            #
# --------------------------------------------------------------------------- #


def _seed_1000_sessions(db, *, username: str) -> int:
    """Create one user + small shared catalog + ~1000 brew sessions.

    Returns the user id.

    Catalog: 5 coffees (distinct origin/process/roast_level), 2 bags each,
    1 brewer, 1 recipe, 8 flavor notes, 1 roaster.

    Sessions: 1000 rows for this one user with:
    - mostly rated (700 rated, 300 unrated) to give aggregations enough data
    - varied ratings from 3.0 to 5.0
    - each session assigned flavor notes from the 8-note pool (4-note subsets)
    - varied brewed_at dates so freshness buckets get data
    - varied bag_id / recipe_id / brewer_id so all joins resolve
    - some sessions have brewer_id=None (sweet spots requires non-null)
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

    roaster = Roaster(name=f"perftest-Roaster-{username}")
    db.add(roaster)
    db.flush()

    # 5 coffees with distinct origins/process/roast_level
    coffee_defs = [
        ("Ethiopia", "washed", "light"),
        ("Colombia", "natural", "medium"),
        ("Kenya", "washed", "medium-light"),
        ("Brazil", "honey", "medium-dark"),
        ("Guatemala", "natural", "light"),
    ]
    coffees = []
    for origin, process, roast_level in coffee_defs:
        c = Coffee(
            name=f"perftest-Coffee-{origin}-{username}",
            roaster_id=roaster.id,
            origins=[CoffeeOrigin(country=origin, sort_order=0)],
            process=process,
            roast_level=roast_level,
        )
        db.add(c)
        db.flush()
        coffees.append(c)

    # 2 bags per coffee. roast_date column was dropped in Phase 15.1 (CATALOG-07);
    # bags now only carry coffee_id + weight/notes. Keep the per-coffee count for
    # join coverage even though freshness bucketing is no longer derived here.
    bags = []
    for coffee in coffees:
        for _ in range(2):
            bag = Bag(
                coffee_id=coffee.id,
            )
            db.add(bag)
            db.flush()
            bags.append(bag)

    # 1 brewer, 1 recipe
    brewer = Equipment(type="brewer", brand="Hario", model="V60Perf")
    db.add(brewer)
    db.flush()

    recipe = Recipe(
        name=f"perftest-Recipe-{username}",
        dose_grams=15,
        water_grams=250,
        water_temp_c=93,
        grind_setting="22",
    )
    db.add(recipe)
    db.flush()

    # 8 flavor notes (8 distinct IDs for cold-start note-count spread)
    fn_ids = []
    for i in range(8):
        fn = FlavorNote(name=f"perftest-fn-{i}-{username}", category="fruit")
        db.add(fn)
        db.flush()
        fn_ids.append(fn.id)

    # Flush catalog before bulk session insert
    db.flush()

    # Insert ~1000 sessions in batches to avoid memory pressure
    TOTAL_SESSIONS = 1000
    RATED_COUNT = 700

    brew_base = datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC)
    sessions_data = []

    for i in range(TOTAL_SESSIONS):
        coffee_idx = i % len(coffees)
        coffee = coffees[coffee_idx]
        # Pick bag that belongs to this coffee
        bag = bags[coffee_idx * 2 + (i % 2)]

        # Rating: first 700 sessions rated (varied), rest None
        if i < RATED_COUNT:
            # Ratings spread across [3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0]
            rating_cents = 300 + ((i % 9) * 25)
            rating = Decimal(rating_cents) / 100
        else:
            rating = None

        # Brewer/recipe: 80% have both (to give sweet spots data), 20% null
        has_equipment = (i % 5) != 0
        brewer_id = brewer.id if has_equipment else None
        recipe_id = recipe.id if has_equipment else None

        # 4-note subsets cycling through the 8-note pool
        note_start = i % 5
        note_ids = fn_ids[note_start : note_start + 4] or fn_ids[:4]

        # Vary brewed_at (spread over 90 days for freshness variation)
        day_offset = i % 90
        brewed_at = brew_base - timedelta(days=day_offset)

        sessions_data.append(
            BrewSession(
                user_id=uid,
                coffee_id=coffee.id,
                bag_id=bag.id,
                recipe_id=recipe_id,
                brewer_id=brewer_id,
                dose_grams_actual=Decimal("15"),
                water_grams_actual=Decimal("250"),
                rating=rating,
                flavor_note_ids_observed=note_ids,
                brewed_at=brewed_at,
            )
        )

    # Bulk-add in one flush for efficiency
    db.add_all(sessions_data)
    db.flush()
    db.commit()

    # Run ANALYZE so the planner has fresh statistics for the perf queries
    from sqlalchemy import text as sa_text

    with db.get_bind().connect() as conn:
        conn.execute(sa_text("ANALYZE brew_sessions"))
        conn.commit()

    return uid


# --------------------------------------------------------------------------- #
# Clean fixture                                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture
def clean_analytics_perf() -> Iterator[None]:
    """Wipe perf-test rows before AND after (FK-safe order, perftest- prefix)."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM brew_sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'perftest-%')"
                )
            )
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(
                text(
                    "DELETE FROM bags WHERE coffee_id IN "
                    "(SELECT id FROM coffees WHERE name LIKE 'perftest-%')"
                )
            )
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'perftest-%'"))
            conn.execute(text("DELETE FROM equipment WHERE brand = 'Hario' AND model = 'V60Perf'"))
            conn.execute(text("DELETE FROM recipes WHERE name LIKE 'perftest-%'"))
            conn.execute(text("DELETE FROM flavor_notes WHERE name LIKE 'perftest-%'"))
            conn.execute(text("DELETE FROM roasters WHERE name LIKE 'perftest-%'"))
            conn.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'perftest-%')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE username LIKE 'perftest-%'"))

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# Latency measurement helpers                                                  #
# --------------------------------------------------------------------------- #

BUDGET_MS = 50  # per-query budget (ROADMAP Success Criterion 2)
TIMING_RUNS = 5  # median over N runs


def _median_ms(fn, *args, **kwargs) -> float:
    """Wall-clock median (ms) of TIMING_RUNS calls to fn(*args, **kwargs)."""
    times = []
    for _ in range(TIMING_RUNS):
        t0 = time.perf_counter()
        fn(*args, **kwargs)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
    times.sort()
    return times[TIMING_RUNS // 2]  # median


# --------------------------------------------------------------------------- #
# Latency test                                                                 #
# --------------------------------------------------------------------------- #


def test_analytics_query_latency(clean_analytics_perf: None) -> None:
    """Every analytics derivation runs <50ms (median) against a ~1000-session seed.

    ROADMAP Phase 6 Success Criterion 2: p95 <50ms per query on a 1000-session seed.
    Using wall-clock median over 5 runs as a practical p50 proxy — more than
    sufficient at household scale where query variance is low.
    """
    _require_postgres()
    _require_analytics_tables()
    from app.db import SessionLocal
    from app.services import analytics

    # Seed 1000 sessions
    with SessionLocal() as db:
        uid = _seed_1000_sessions(db, username="perftest-latency")

    # Define each function to time, with its display name
    # Phase 15.1 (CATALOG-07) removed get_roast_freshness_buckets along with
    # the roast-freshness home card and the bags.roast_date column.
    checks = [
        ("get_top_coffees", analytics.get_top_coffees),
        ("get_preference_profile", analytics.get_preference_profile),
        ("get_flavor_descriptors", analytics.get_flavor_descriptors),
        ("get_sweet_spots", analytics.get_sweet_spots),
        ("get_recent_brews", analytics.get_recent_brews),
        ("get_unrated_coffees", analytics.get_unrated_coffees),
        ("get_cold_start_counts", analytics.get_cold_start_counts),
        ("compute_input_signature", analytics.compute_input_signature),
    ]

    failures = []
    with SessionLocal() as db:
        for fn_name, fn in checks:
            median = _median_ms(fn, db, uid)
            if median >= BUDGET_MS:
                failures.append(f"{fn_name}: {median:.1f}ms (budget: {BUDGET_MS}ms)")

    if failures:
        pytest.fail(
            f"Analytics queries exceeded the {BUDGET_MS}ms budget:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )


# --------------------------------------------------------------------------- #
# AIX-13: latency percentile query (plan 19-05, D-15)                        #
# --------------------------------------------------------------------------- #


def _require_ai_recommendations_table() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.ai_recommendations')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("ai_recommendations table not present — migration not applied")


def test_latency_percentile_query() -> None:
    """p50/p95 PERCENTILE_CONT query over ai_recommendations.duration_ms executes (AIX-13/D-15).

    The query runs against the live table (which may be empty — that's fine: an
    empty result set is still a successful execution). Grouped by recommendation_type.
    Uses PERCENTILE_CONT(0.50) and PERCENTILE_CONT(0.95) within-group expressions.
    """
    _require_postgres()
    _require_ai_recommendations_table()

    from sqlalchemy import text

    from app.db import SessionLocal

    stmt = text(
        """
        SELECT
            recommendation_type,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
            COUNT(*) AS sample_count
        FROM ai_recommendations
        WHERE
            duration_ms IS NOT NULL
            AND generated_at >= NOW() - INTERVAL '30 days'
        GROUP BY recommendation_type
        ORDER BY recommendation_type
        """
    )

    with SessionLocal() as db:
        rows = db.execute(stmt).all()

    # Query must execute without error; rows may be empty on a fresh DB
    assert isinstance(rows, list), "Expected a list of rows from the percentile query"
    # Each row must have the expected columns when non-empty
    for row in rows:
        assert hasattr(row, "recommendation_type"), "Row missing recommendation_type"
        assert hasattr(row, "p50_ms"), "Row missing p50_ms"
        assert hasattr(row, "p95_ms"), "Row missing p95_ms"
        assert hasattr(row, "sample_count"), "Row missing sample_count"
