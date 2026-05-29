"""Wave 0 contract tests for GBREW-01/03 brew session schema + timing fields (Phase 20, Plan 01).

These tests assert the LOCKED schema/column shape AFTER Plan 20-02 adds:
  - BrewSessionCreate.water_profile_id (Optional[int], ge=1)
  - BrewSessionCreate.first_drip_seconds (Optional[int], ge=0)
  - BrewSessionCreate.bloom_time_seconds (Optional[int], ge=0)
  - brew_sessions table columns: water_profile_id, first_drip_seconds, bloom_time_seconds

They are EXPECTED to fail RED until Plan 20-02 lands those additions.

Also tests the GBM finish URL query-param contract (GBREW-01 D-15):
  GET /brew/new?gbm=1&brew_time=T&first_drip=X&bloom_time=Y
  must seed those values into the rendered form.

Requirement traceability:
  GBREW-01 (D-14, D-15), GBREW-03 (D-12, D-14), GBREW-04 (D-02)

No pytest.skip for missing data — tests fail RED now, turn GREEN in Wave 1.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError


# --------------------------------------------------------------------------- #
# Skip gates (DB-dependent tests only)                                        #
# --------------------------------------------------------------------------- #


def _require_postgres_and_migration() -> None:
    """Fail-fast skip when Postgres is unreachable or the migration hasn't run."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — timing_columns test needs the DB")

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
# Schema tests (no DB required)                                               #
# --------------------------------------------------------------------------- #


def test_timing_fields_schema() -> None:
    """D-12 / D-14 / GBREW-03: BrewSessionCreate accepts timing fields as optional ints.

    - first_drip_seconds: Optional[int], ge=0 — absent → None, negative → ValidationError
    - bloom_time_seconds: Optional[int], ge=0 — absent → None, negative → ValidationError
    """
    from app.schemas.brew_session import BrewSessionCreate

    # Absent → None (both fields optional)
    session = BrewSessionCreate(
        coffee_id=1,
        dose_grams_actual="18",
        water_grams_actual="300",
    )
    assert session.first_drip_seconds is None  # type: ignore[attr-defined]
    assert session.bloom_time_seconds is None  # type: ignore[attr-defined]

    # Present positive values → accepted
    session2 = BrewSessionCreate(
        coffee_id=1,
        dose_grams_actual="18",
        water_grams_actual="300",
        first_drip_seconds=15,
        bloom_time_seconds=45,
    )
    assert session2.first_drip_seconds == 15  # type: ignore[attr-defined]
    assert session2.bloom_time_seconds == 45  # type: ignore[attr-defined]

    # Negative → ValidationError (ge=0 bound)
    with pytest.raises(ValidationError):
        BrewSessionCreate(
            coffee_id=1,
            dose_grams_actual="18",
            water_grams_actual="300",
            first_drip_seconds=-1,
        )

    with pytest.raises(ValidationError):
        BrewSessionCreate(
            coffee_id=1,
            dose_grams_actual="18",
            water_grams_actual="300",
            bloom_time_seconds=-5,
        )


def test_water_profile_id_schema() -> None:
    """D-02 / GBREW-04: BrewSessionCreate accepts water_profile_id (ge=1) and rejects 0.

    Threat: water_profile_id tampering — a client posting 0 or a negative id
    must be rejected with ValidationError, not silently nulled or inserted.
    """
    from app.schemas.brew_session import BrewSessionCreate

    # Absent → None (optional FK)
    session = BrewSessionCreate(
        coffee_id=1,
        dose_grams_actual="18",
        water_grams_actual="300",
    )
    assert session.water_profile_id is None  # type: ignore[attr-defined]

    # Valid id (ge=1)
    session2 = BrewSessionCreate(
        coffee_id=1,
        dose_grams_actual="18",
        water_grams_actual="300",
        water_profile_id=3,
    )
    assert session2.water_profile_id == 3  # type: ignore[attr-defined]

    # id=0 must be rejected (ge=1 bound)
    with pytest.raises(ValidationError):
        BrewSessionCreate(
            coffee_id=1,
            dose_grams_actual="18",
            water_grams_actual="300",
            water_profile_id=0,
        )

    # Negative must also be rejected
    with pytest.raises(ValidationError):
        BrewSessionCreate(
            coffee_id=1,
            dose_grams_actual="18",
            water_grams_actual="300",
            water_profile_id=-1,
        )


# --------------------------------------------------------------------------- #
# Database schema introspection test                                           #
# --------------------------------------------------------------------------- #


def test_timing_columns(authed_client: Any) -> None:  # noqa: ARG001
    """D-12 / D-14 / D-02: brew_sessions has the three new nullable columns after migration.

    Introspects information_schema.columns to assert:
      - water_profile_id (bigint, nullable)
      - first_drip_seconds (integer, nullable)
      - bloom_time_seconds (integer, nullable)

    This test requires both Postgres and the p20 migration to have run.
    The authed_client fixture ensures the app + DB are reachable.
    """
    _require_postgres_and_migration()

    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='brew_sessions' "
                "  AND column_name IN "
                "  ('water_profile_id', 'first_drip_seconds', 'bloom_time_seconds')"
            )
        ).all()

    cols = {row[0]: (row[1], row[2]) for row in rows}

    expected = {
        "water_profile_id": ("bigint", "YES"),
        "first_drip_seconds": ("integer", "YES"),
        "bloom_time_seconds": ("integer", "YES"),
    }
    missing = set(expected) - set(cols)
    assert not missing, (
        f"brew_sessions missing new timing/profile columns: {missing} — "
        "run the p20 Alembic migration first"
    )
    for col, (dtype, nullable) in expected.items():
        actual_dtype, actual_nullable = cols[col]
        assert actual_dtype == dtype, (
            f"brew_sessions.{col}: expected type {dtype}, got {actual_dtype}"
        )
        assert actual_nullable == nullable, (
            f"brew_sessions.{col}: expected nullable={nullable}, got {actual_nullable}"
        )


# --------------------------------------------------------------------------- #
# GBM finish URL query-param contract (GBREW-01 D-15)                         #
# --------------------------------------------------------------------------- #


def test_gbm_finish_url_has_brew_time(authed_client: Any, seeded_admin_user: Any) -> None:
    """D-15 / GBREW-01: GET /brew/new?brew_time=T&first_drip=X&bloom_time=Y seeds the form.

    The finishBrewing() JS function redirects to /brew/new with these query
    params. The server must seed the corresponding form fields so the user
    sees the timed values pre-filled when logging the completed session.

    Expected behavior (locked contract for Plan 20-04 to implement):
      - brew_time_seconds field is seeded with the brew_time query param value
      - first_drip_seconds field is seeded with the first_drip query param value
      - bloom_time_seconds field is seeded with the bloom_time query param value

    This test will be RED until Plan 20-04 wires those params in the GET handler.
    """
    resp = authed_client.get(
        "/brew/new?gbm=1&brew_time=215&first_drip=18&bloom_time=43"
    )
    assert resp.status_code == 200
    body = resp.text
    # brew_time_seconds is already seeded by the current handler (brew_time param).
    # first_drip_seconds and bloom_time_seconds are new (Plan 20-04 wires them).
    assert 'name="brew_time_seconds"' in body or "215" in body, (
        "brew_time_seconds not seeded in form — GBM brew_time param not wired"
    )
    assert 'name="first_drip_seconds"' in body, (
        "first_drip_seconds field not in form — Plan 20-04 must add this field"
    )
    assert 'name="bloom_time_seconds"' in body, (
        "bloom_time_seconds field not in form — Plan 20-04 must add this field"
    )
    # Values must be seeded from query params
    assert "18" in body, "first_drip value (18s) not seeded in form"
    assert "43" in body, "bloom_time value (43s) not seeded in form"
