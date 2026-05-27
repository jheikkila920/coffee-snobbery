"""Wave 0 tests for CATALOG-05 — varietal m2m migration + router endpoints.

Tests the schema migration that creates varietals + coffee_varietals tables,
seeds 14 common varietals, drops coffees.varietal column, and the router
endpoints for autocomplete and create-on-the-fly.

DB-touching tests skip when Postgres is not reachable.
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# Skip gate                                                                    #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — varietal test needs the DB")


# --------------------------------------------------------------------------- #
# Schema / migration tests                                                     #
# --------------------------------------------------------------------------- #


def test_varietals_table_exists() -> None:
    """varietals table must exist after migration."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        result = db.execute(text("SELECT to_regclass('public.varietals')")).scalar()
    assert result is not None, "varietals table not found — migration not applied"


def test_coffee_varietals_join_table_exists() -> None:
    """coffee_varietals join table must exist after migration."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        result = db.execute(text("SELECT to_regclass('public.coffee_varietals')")).scalar()
    assert result is not None, "coffee_varietals table not found — migration not applied"


def test_seed_inserted_14_varietals() -> None:
    """varietals table must contain exactly 14 seeded rows."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        count = db.execute(text("SELECT COUNT(*) FROM varietals")).scalar()
    assert count == 14, f"Expected 14 varietals, got {count}"


def test_seed_includes_expected_names() -> None:
    """All 14 seeded varietal names must be present (case-insensitive match)."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    expected = {
        "Bourbon", "Typica", "Caturra", "Catuai", "Geisha", "Pacamara",
        "SL28", "SL34", "Mundo Novo", "Pacas", "Heirloom", "Maragogype",
        "Castillo", "Catimor",
    }
    with SessionLocal() as db:
        rows = db.execute(text("SELECT name FROM varietals")).scalars().all()
    actual = set(rows)
    missing = expected - actual
    assert not missing, f"Missing seeded varietals: {missing}"


def test_coffee_varietal_column_dropped() -> None:
    """coffees.varietal column must not exist after migration."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        result = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='coffees' AND column_name='varietal'"
            )
        ).scalar()
    assert result is None, "coffees.varietal column still exists — migration not applied"


def test_citext_uniqueness_collapses_case() -> None:
    """Inserting 'geisha' after 'Geisha' already exists must raise IntegrityError."""
    _require_postgres()
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal

    # Check that 'Geisha' is already seeded; if not, skip.
    with SessionLocal() as db:
        exists = db.execute(
            text("SELECT id FROM varietals WHERE name = 'Geisha'")
        ).scalar()
    if exists is None:
        pytest.skip("Geisha seed not found — migration not applied")

    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text("INSERT INTO varietals (name) VALUES (:name)"),
                {"name": "geisha"},
            )
            db.flush()


def test_coffee_with_two_varietals(client: object) -> None:
    """POST /coffees with varietal_ids=[1,2] creates a coffee with 2 varietals."""
    _require_postgres()
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("starlette not available")

    from sqlalchemy import text

    from app.db import SessionLocal

    # Get first two varietal IDs from the DB.
    with SessionLocal() as db:
        ids = db.execute(
            text("SELECT id FROM varietals ORDER BY id LIMIT 2")
        ).scalars().all()
    if len(ids) < 2:
        pytest.skip("Need at least 2 varietals in DB")

    # Use the TestClient from conftest.
    try:
        app_client = client  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        pytest.skip("client fixture unavailable")

    resp = app_client.post(
        "/coffees",
        data={
            "name": "__test_two_varietals__",
            "origins_country": "Ethiopia",
            "origins_region": "",
            "varietal_ids": [str(ids[0]), str(ids[1])],
        },
        follow_redirects=False,
    )
    # Success returns 200 (HTMX pattern)
    assert resp.status_code == 200

    # Verify in DB
    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT c.id, COUNT(cv.varietal_id) as vcnt "
                "FROM coffees c "
                "JOIN coffee_varietals cv ON cv.coffee_id = c.id "
                "WHERE c.name = '__test_two_varietals__' "
                "GROUP BY c.id"
            )
        ).first()
    assert row is not None, "Coffee not created"
    assert row.vcnt == 2, f"Expected 2 varietals, got {row.vcnt}"

    # Cleanup
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM coffees WHERE name='__test_two_varietals__'")
        )
        db.commit()


def test_coffee_with_zero_varietals(client: object) -> None:
    """POST /coffees with no varietal_ids creates a coffee with empty varietals."""
    _require_postgres()

    try:
        app_client = client  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        pytest.skip("client fixture unavailable")

    from sqlalchemy import text

    from app.db import SessionLocal

    resp = app_client.post(
        "/coffees",
        data={
            "name": "__test_zero_varietals__",
            "origins_country": "Kenya",
            "origins_region": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        coffee_id = db.execute(
            text("SELECT id FROM coffees WHERE name='__test_zero_varietals__'")
        ).scalar()
        if coffee_id is not None:
            cv_count = db.execute(
                text("SELECT COUNT(*) FROM coffee_varietals WHERE coffee_id=:cid"),
                {"cid": coffee_id},
            ).scalar()
            db.execute(text("DELETE FROM coffees WHERE id=:cid"), {"cid": coffee_id})
            db.commit()
    assert coffee_id is not None, "Coffee not created"
    assert cv_count == 0, f"Expected 0 varietals, got {cv_count}"


def test_cascade_delete_removes_join_rows() -> None:
    """Deleting a coffee must remove its coffee_varietals rows (CASCADE)."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        v_id = db.execute(
            text("SELECT id FROM varietals ORDER BY id LIMIT 1")
        ).scalar()
    if v_id is None:
        pytest.skip("No varietals in DB")

    with SessionLocal() as db:
        coffee_id = db.execute(
            text(
                "INSERT INTO coffees (name, notes, advertised_flavor_note_ids) "
                "VALUES ('__test_cascade__', '', '{}') RETURNING id"
            )
        ).scalar()
        db.execute(
            text(
                "INSERT INTO coffee_varietals (coffee_id, varietal_id) "
                "VALUES (:cid, :vid)"
            ),
            {"cid": coffee_id, "vid": v_id},
        )
        db.commit()

    with SessionLocal() as db:
        db.execute(text("DELETE FROM coffees WHERE id=:cid"), {"cid": coffee_id})
        db.commit()
        leftover = db.execute(
            text("SELECT COUNT(*) FROM coffee_varietals WHERE coffee_id=:cid"),
            {"cid": coffee_id},
        ).scalar()
    assert leftover == 0, f"Expected 0 join rows after cascade delete, got {leftover}"


def test_varietal_restrict_on_delete() -> None:
    """Deleting a varietal still referenced by coffee_varietals must raise IntegrityError."""
    _require_postgres()
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal

    # Insert a temporary varietal + a coffee that uses it.
    with SessionLocal() as db:
        v_id = db.execute(
            text(
                "INSERT INTO varietals (name) VALUES ('__test_restrict__') RETURNING id"
            )
        ).scalar()
        c_id = db.execute(
            text(
                "INSERT INTO coffees (name, notes, advertised_flavor_note_ids) "
                "VALUES ('__test_restrict_coffee__', '', '{}') RETURNING id"
            )
        ).scalar()
        db.execute(
            text(
                "INSERT INTO coffee_varietals (coffee_id, varietal_id) VALUES (:cid, :vid)"
            ),
            {"cid": c_id, "vid": v_id},
        )
        db.commit()

    # Attempt to delete the varietal while a join row references it.
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text("DELETE FROM varietals WHERE id=:vid"), {"vid": v_id}
            )
            db.flush()

    # Cleanup
    with SessionLocal() as db:
        db.execute(text("DELETE FROM coffees WHERE id=:cid"), {"cid": c_id})
        db.execute(text("DELETE FROM varietals WHERE id=:vid"), {"vid": v_id})
        db.commit()


def test_autocomplete_endpoint_returns_prefix_matches(client: object) -> None:
    """GET /coffees/varietal-autocomplete?q=Bou returns fragment containing 'Bourbon'."""
    _require_postgres()

    try:
        app_client = client  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        pytest.skip("client fixture unavailable")

    resp = app_client.get("/coffees/varietal-autocomplete?q=Bou")
    assert resp.status_code == 200
    assert "Bourbon" in resp.text


def test_create_varietal_on_the_fly(client: object) -> None:
    """POST /coffees/varietals with name='TestVar' creates and returns a new varietal."""
    _require_postgres()

    try:
        app_client = client  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        pytest.skip("client fixture unavailable")

    from sqlalchemy import text

    from app.db import SessionLocal

    resp = app_client.post(
        "/coffees/varietals",
        data={"name": "TestVarietalOnTheFly"},
        follow_redirects=False,
    )
    assert resp.status_code == 200

    # Cleanup
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM varietals WHERE name='TestVarietalOnTheFly'")
        )
        db.commit()
