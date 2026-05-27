"""Service-layer unit tests for app/services/varietals.py (CATALOG-05).

Mirrors the structural shape of tests/services/test_analytics.py:
real Postgres via the _require_postgres skip gate, SessionLocal pattern.
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
        pytest.skip("Postgres not reachable — varietals service test needs the DB")


# --------------------------------------------------------------------------- #
# Service-layer tests                                                          #
# --------------------------------------------------------------------------- #


def test_create_varietal_basic() -> None:
    """create_varietal returns a Varietal with the given name."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal
    from app.services.varietals import create_varietal

    with SessionLocal() as db:
        varietal = create_varietal(db, name="TestCreateBasic9x7", by_user_id=1)
        varietal_id = varietal.id
        assert varietal.name == "TestCreateBasic9x7"
        assert varietal_id is not None

    # Cleanup
    with SessionLocal() as db:
        db.execute(text("DELETE FROM varietals WHERE id=:vid"), {"vid": varietal_id})
        db.commit()


def test_create_varietal_duplicate_raises_DuplicateNameError() -> None:
    """Creating the same varietal name twice raises DuplicateNameError."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal
    from app.services.form_validation import DuplicateNameError
    from app.services.varietals import create_varietal

    with SessionLocal() as db:
        v = create_varietal(db, name="TestDupeName8q5", by_user_id=1)
        v_id = v.id

    try:
        with SessionLocal() as db:
            with pytest.raises(DuplicateNameError):
                create_varietal(db, name="testdupename8q5", by_user_id=1)
    finally:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM varietals WHERE id=:vid"), {"vid": v_id})
            db.commit()


def test_search_by_prefix_returns_matches() -> None:
    """search_by_prefix(query='Bou') returns Bourbon from the seeded data."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal
    from app.services.varietals import search_by_prefix

    # Ensure Bourbon is seeded (from migration).
    with SessionLocal() as db:
        bourbon_exists = db.execute(text("SELECT id FROM varietals WHERE name='Bourbon'")).scalar()
    if bourbon_exists is None:
        pytest.skip("Bourbon not seeded — migration not applied")

    with SessionLocal() as db:
        results = search_by_prefix(db, query="Bou")
    names = [v.name for v in results]
    assert "Bourbon" in names, f"Bourbon not found in {names}"
