"""Wave 0 tests for CATALOG-04 — roast-level enum widening.

Tests the migration that adds 'ultra-light' and 'nordic-light' to the
coffees_roast_level_check constraint, plus Pydantic schema validation
and the service-layer COFFEE_ROAST_LEVELS tuple.

DB-touching tests skip when Postgres is not reachable (same pattern as
tests/services/test_analytics.py).
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
        pytest.skip("Postgres not reachable — enum test needs the DB")


# --------------------------------------------------------------------------- #
# DB-level CHECK constraint tests                                              #
# --------------------------------------------------------------------------- #


def test_check_constraint_accepts_ultra_light() -> None:
    """INSERT with roast_level='ultra-light' must succeed after migration."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        # Use raw SQL so we can check the constraint directly without Pydantic.
        result = db.execute(
            text(
                "INSERT INTO coffees (name, roast_level, notes, advertised_flavor_note_ids) "
                "VALUES (:name, :rl, '', '{}') RETURNING id"
            ),
            {"name": "__test_ultra_light__", "rl": "ultra-light"},
        )
        row_id = result.scalar_one()
        db.execute(text("DELETE FROM coffees WHERE id = :id"), {"id": row_id})
        db.commit()


def test_check_constraint_accepts_nordic_light() -> None:
    """INSERT with roast_level='nordic-light' must succeed after migration."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        result = db.execute(
            text(
                "INSERT INTO coffees (name, roast_level, notes, advertised_flavor_note_ids) "
                "VALUES (:name, :rl, '', '{}') RETURNING id"
            ),
            {"name": "__test_nordic_light__", "rl": "nordic-light"},
        )
        row_id = result.scalar_one()
        db.execute(text("DELETE FROM coffees WHERE id = :id"), {"id": row_id})
        db.commit()


def test_check_constraint_rejects_invalid() -> None:
    """INSERT with roast_level='extra-bold' must raise IntegrityError."""
    _require_postgres()
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal

    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO coffees (name, roast_level, notes, advertised_flavor_note_ids) "
                    "VALUES (:name, :rl, '', '{}') RETURNING id"
                ),
                {"name": "__test_invalid_roast__", "rl": "extra-bold"},
            )
            db.flush()


def test_existing_six_values_still_valid() -> None:
    """All six original roast_level values remain valid after the migration."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import SessionLocal

    original_values = ["light", "medium-light", "medium", "medium-dark", "dark", "unknown"]
    with SessionLocal() as db:
        inserted_ids = []
        for rl in original_values:
            result = db.execute(
                text(
                    "INSERT INTO coffees (name, roast_level, notes, advertised_flavor_note_ids) "
                    "VALUES (:name, :rl, '', '{}') RETURNING id"
                ),
                {"name": f"__test_{rl}__", "rl": rl},
            )
            inserted_ids.append(result.scalar_one())
        for row_id in inserted_ids:
            db.execute(text("DELETE FROM coffees WHERE id = :id"), {"id": row_id})
        db.commit()


# --------------------------------------------------------------------------- #
# Service-layer tuple test                                                     #
# --------------------------------------------------------------------------- #


def test_coffee_roast_levels_tuple_order() -> None:
    """COFFEE_ROAST_LEVELS must equal the 8-value CATALOG-04 sequence."""
    from app.services.coffees import COFFEE_ROAST_LEVELS

    expected = (
        "ultra-light",
        "nordic-light",
        "light",
        "medium-light",
        "medium",
        "medium-dark",
        "dark",
        "unknown",
    )
    assert COFFEE_ROAST_LEVELS == expected


# --------------------------------------------------------------------------- #
# Pydantic schema tests                                                        #
# --------------------------------------------------------------------------- #


def test_pydantic_accepts_ultra_light() -> None:
    """CoffeeCreate with roast_level='ultra-light' must validate without error."""
    from app.schemas.coffee import CoffeeCreate

    form = CoffeeCreate(name="Test Coffee", roast_level="ultra-light")
    assert form.roast_level == "ultra-light"


def test_pydantic_rejects_invalid() -> None:
    """CoffeeCreate with roast_level='extra-bold' must raise ValidationError."""
    from pydantic import ValidationError

    from app.schemas.coffee import CoffeeCreate

    with pytest.raises(ValidationError):
        CoffeeCreate(name="Test Coffee", roast_level="extra-bold")
