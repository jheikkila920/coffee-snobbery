"""Phase 5 Wave 0 schema tests for ``brew_sessions`` + brew Pydantic schemas.

Covers the Per-Task Verification Map rows from
``.planning/phases/05-brew-sessions/05-VALIDATION.md``:

- BREW-01 — ``extraction_yield_pct`` is GENERATED: insert dose/yield/tds → DB
  read-back returns the computed whole-percent EY → ``test_extraction_yield_generated``
- BREW-01 — EY NULL-propagation (any operand NULL → EY NULL)
                                          → ``test_extraction_yield_null_when_input_null``
- BREW-01 — EY is read-only (GENERATED column rejects a direct write)
                                          → ``test_ey_not_writable``
- BREW-01 — ``flavor_note_ids_observed`` ARRAY round-trips list[int]
                                          → ``test_observed_notes_array``
- BREW-04 — rating Decimal validates 0/2.5/5/1.75; rejects 5.5 and 3.3
                                          → ``test_rating_decimal_steps``

Task 0 (resolved): ``tds_pct`` is stored as a WHOLE PERCENT (1.35 means 1.35%),
so the GENERATED expression is
``(yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100`` (whole-percent
EY out). ``user_id`` FK uses ``ondelete=RESTRICT`` — brew history never silently
vanishes on a user delete.

The integration tests use the sync ``SessionLocal()`` (mirrors
``tests/services/test_settings.py``); each opens a transaction and rolls it back
in ``finally`` so the user/coffee/brew rows created for the RESTRICT FKs never
persist. Tests skip cleanly when Postgres is unreachable (host-only runs).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


def _require_brew_models() -> None:
    """Skip cleanly until Task 2 lands the models + Task 4 lands the migration."""
    try:
        from app.models import BrewDraft, BrewSession  # noqa: F401
    except ImportError:
        pytest.skip("Phase 5 dependency: app.models.BrewSession / BrewDraft (Task 2)")


def _require_brew_schema() -> None:
    """Skip cleanly until Task 3 lands the Pydantic schemas."""
    try:
        from app.schemas.brew_session import (  # noqa: F401
            BrewSessionCreate,
            BrewSessionUpdate,
        )
    except ImportError:
        pytest.skip("Phase 5 dependency: app.schemas.brew_session (Task 3)")


def _require_postgres() -> None:
    """Skip when Postgres is unreachable — DB read-back tests need a real DB."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — schema read-back test needs the DB")


def _seed_user_and_coffee(db):
    """Insert a throwaway user + coffee to satisfy the RESTRICT FKs.

    Returns ``(user_id, coffee_id)``. Both rows live only inside the caller's
    transaction, which the test rolls back in ``finally``.
    """
    from app.models import Coffee, User

    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"brewtest-{suffix}",
        password_hash="x",  # not exercised; column is NOT NULL
    )
    db.add(user)
    db.flush()

    coffee = Coffee(name=f"Brew Test Coffee {suffix}")
    db.add(coffee)
    db.flush()

    return user.id, coffee.id


def test_extraction_yield_generated() -> None:
    """BREW-01: EY is GENERATED — dose/yield/tds insert → DB returns computed EY.

    Task 0 unit: tds whole-percent. With dose=15, yield=250, tds=1.35:
        EY = (250 * 1.35 / 100.0) / 15 * 100 = 22.50 (whole percent).
    """
    _require_brew_models()
    _require_postgres()
    from app.db import SessionLocal
    from app.models import BrewSession

    db = SessionLocal()
    try:
        user_id, coffee_id = _seed_user_and_coffee(db)
        brew = BrewSession(
            user_id=user_id,
            coffee_id=coffee_id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=Decimal("250"),
            tds_pct=Decimal("1.35"),
        )
        db.add(brew)
        db.flush()
        db.refresh(brew)

        assert brew.extraction_yield_pct is not None, "EY must compute for non-NULL inputs"
        assert brew.extraction_yield_pct == Decimal("22.50"), (
            f"whole-percent EY mismatch: got {brew.extraction_yield_pct}, expected 22.50"
        )
    finally:
        db.rollback()
        db.close()


def test_extraction_yield_null_when_input_null() -> None:
    """BREW-01: EY NULL-propagates when any operand (tds here) is NULL."""
    _require_brew_models()
    _require_postgres()
    from app.db import SessionLocal
    from app.models import BrewSession

    db = SessionLocal()
    try:
        user_id, coffee_id = _seed_user_and_coffee(db)
        brew = BrewSession(
            user_id=user_id,
            coffee_id=coffee_id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=Decimal("250"),
            tds_pct=None,  # operand NULL → EY NULL
        )
        db.add(brew)
        db.flush()
        db.refresh(brew)

        assert brew.extraction_yield_pct is None, "EY must be NULL when an operand is NULL"
    finally:
        db.rollback()
        db.close()


def test_ey_not_writable() -> None:
    """BREW-01: extraction_yield_pct is GENERATED — a direct write is rejected by Postgres."""
    _require_brew_models()
    _require_postgres()
    from sqlalchemy.exc import DBAPIError, ProgrammingError

    from app.db import SessionLocal
    from app.models import BrewSession

    db = SessionLocal()
    try:
        user_id, coffee_id = _seed_user_and_coffee(db)
        brew = BrewSession(
            user_id=user_id,
            coffee_id=coffee_id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=Decimal("250"),
            tds_pct=Decimal("1.35"),
        )
        # Attempt to write the GENERATED column directly. Postgres raises
        # error 428C9 ("cannot insert a non-DEFAULT value into column ...
        # GENERATED ALWAYS") on flush.
        brew.extraction_yield_pct = Decimal("99.99")
        db.add(brew)
        with pytest.raises((ProgrammingError, DBAPIError)):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_observed_notes_array() -> None:
    """BREW-01: flavor_note_ids_observed ARRAY round-trips list[int]."""
    _require_brew_models()
    _require_postgres()
    from app.db import SessionLocal
    from app.models import BrewSession

    db = SessionLocal()
    try:
        user_id, coffee_id = _seed_user_and_coffee(db)
        brew = BrewSession(
            user_id=user_id,
            coffee_id=coffee_id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            flavor_note_ids_observed=[3, 7, 12],
        )
        db.add(brew)
        db.flush()
        db.refresh(brew)

        assert brew.flavor_note_ids_observed == [3, 7, 12], (
            f"ARRAY round-trip mismatch: got {brew.flavor_note_ids_observed}"
        )
    finally:
        db.rollback()
        db.close()


def test_rating_decimal_steps() -> None:
    """BREW-04: rating Decimal accepts 0/2.5/5/1.75; rejects 5.5 (range) and 3.3 (step)."""
    _require_brew_schema()
    from pydantic import ValidationError

    from app.schemas.brew_session import BrewSessionCreate

    base = {
        "coffee_id": 1,
        "dose_grams_actual": Decimal("15"),
        "water_grams_actual": Decimal("250"),
    }

    # Accepts valid 0.25-step ratings within 0..5.
    for good in ("0", "2.5", "5", "1.75"):
        model = BrewSessionCreate(**base, rating=Decimal(good))
        assert model.rating == Decimal(good)

    # Rejects out-of-range (le=5).
    with pytest.raises(ValidationError):
        BrewSessionCreate(**base, rating=Decimal("5.5"))

    # Rejects non-0.25 step (multiple_of).
    with pytest.raises(ValidationError):
        BrewSessionCreate(**base, rating=Decimal("3.3"))

    # extra="forbid" blocks mass-assignment of the GENERATED EY column.
    with pytest.raises(ValidationError):
        BrewSessionCreate(**base, extraction_yield_pct=Decimal("18.5"))


def test_brew_create_rejects_ey_overflow() -> None:
    """CR-02: a dose/yield/tds combo whose COMPUTED EY overflows numeric(5,2)
    (max 999.99) is rejected at the schema (pydantic ValidationError), not at
    INSERT (which would be an unhandled 500). A normal brew still validates."""
    _require_brew_schema()
    from pydantic import ValidationError

    from app.schemas.brew_session import BrewSessionCreate

    # dose=0.01, yield=3000, tds=100 -> EY = 3000*100/0.01 = 30,000,000 >> 999.99
    with pytest.raises(ValidationError):
        BrewSessionCreate(
            coffee_id=1,
            dose_grams_actual=Decimal("0.01"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=Decimal("3000"),
            tds_pct=Decimal("100"),
        )

    # A normal brew (dose 15 / yield 250 / tds 1.35 -> EY 22.5) still validates.
    model = BrewSessionCreate(
        coffee_id=1,
        dose_grams_actual=Decimal("15"),
        water_grams_actual=Decimal("250"),
        yield_grams_actual=Decimal("250"),
        tds_pct=Decimal("1.35"),
    )
    assert model.tds_pct == Decimal("1.35")

    # EY exactly at the column ceiling (999.99) is accepted; just over is not.
    # dose=10, yield=100, tds=99.999 -> EY = 100*99.999/10 = 999.99 (boundary).
    ok = BrewSessionCreate(
        coffee_id=1,
        dose_grams_actual=Decimal("10"),
        water_grams_actual=Decimal("250"),
        yield_grams_actual=Decimal("100"),
        tds_pct=Decimal("99.999"),
    )
    assert ok.yield_grams_actual == Decimal("100")
    with pytest.raises(ValidationError):
        BrewSessionCreate(
            coffee_id=1,
            dose_grams_actual=Decimal("10"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=Decimal("100"),
            tds_pct=Decimal("100.001"),  # EY = 1000.01 > 999.99
        )

    # Any NULL operand -> EY is NULL in the DB (no overflow); must validate.
    partial = BrewSessionCreate(
        coffee_id=1,
        dose_grams_actual=Decimal("0.01"),
        water_grams_actual=Decimal("250"),
        yield_grams_actual=Decimal("3000"),
        tds_pct=None,  # NULL -> no EY computed -> no overflow
    )
    assert partial.tds_pct is None


def test_brew_csv_row_rejects_ey_overflow() -> None:
    """CR-02 (CSV path): BrewCsvRow rejects the same EY-overflow combo so the
    importer refuses the row instead of crashing the import with a 500."""
    try:
        from app.schemas.brew_csv import BrewCsvRow
    except ImportError:
        pytest.skip("Phase 5 dependency: app.schemas.brew_csv")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BrewCsvRow(
            coffee_name="Anything",
            dose_grams_actual=Decimal("0.01"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=Decimal("3000"),
            tds_pct=Decimal("100"),
        )

    # Normal row still validates.
    ok = BrewCsvRow(
        coffee_name="Anything",
        dose_grams_actual=Decimal("15"),
        water_grams_actual=Decimal("250"),
        yield_grams_actual=Decimal("250"),
        tds_pct=Decimal("1.35"),
    )
    assert ok.coffee_name == "Anything"
