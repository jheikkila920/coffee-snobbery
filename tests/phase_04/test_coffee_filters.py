"""CAT-07 filter integration tests for plan 04-07 (coffees CRUD).

Covers the four filter dimensions individually (roaster, country,
process, archived) plus a multi-dim AND combination, the HX-Request
fragment branch with filters applied, and the locked
``hx-push-url="true"`` contract on the filter form (D-03).

The mobile card-list visual verification at 375px is in the
04-VALIDATION.md "Manual-Only Verifications" table (Phase 12 Playwright
will assert no-horizontal-scroll); the HTML markers are exercised in
``test_routers_coffees.test_list_coffees_includes_responsive_layout_markers``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 4 filter test needs the DB")


def _require_p4_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.coffees')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p4_shared_catalog migration not applied")


@pytest.fixture
def clean_catalog() -> Iterator[None]:
    """Wipe the catalog chain before AND after each filter test."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM bags"))
            conn.execute(text("DELETE FROM coffees"))
            conn.execute(text("DELETE FROM flavor_notes"))
            conn.execute(text("DELETE FROM roasters"))

    _reset()
    yield
    _reset()


def _seed_roaster(name: str) -> int:
    from app.db import SessionLocal
    from app.services import roasters as roasters_service

    with SessionLocal() as db:
        return roasters_service.create_roaster(
            db, name=name, location=None, website=None, notes="", by_user_id=0
        ).id


def _seed_coffee(
    *,
    name: str,
    roaster_id: int | None = None,
    country: str | None = None,
    process: str | None = None,
    archived: bool = False,
) -> int:
    from sqlalchemy import text

    from app.db import SessionLocal, engine
    from app.services import coffees as coffees_service

    origins = [(country, None)] if country else []
    with SessionLocal() as db:
        cid = coffees_service.create_coffee(
            db,
            name=name,
            roaster_id=roaster_id,
            origins=origins,
            process=process,
            roast_level=None,
            notes="",
            advertised_flavor_note_ids=[],
            by_user_id=0,
        ).id
    if archived:
        with engine.begin() as conn:
            conn.execute(text("UPDATE coffees SET archived=TRUE WHERE id = :id"), {"id": cid})
    return cid


# --------------------------------------------------------------------------- #
# Individual filter dimensions                                                #
# --------------------------------------------------------------------------- #


def test_filter_by_roaster_returns_only_matching(authed_client: Any, clean_catalog: None) -> None:
    """GET /coffees?roaster_id=R1 → only the coffee with roaster_id=R1."""
    _require_postgres()
    _require_p4_migration_applied()
    r1 = _seed_roaster("Onyx")
    r2 = _seed_roaster("Heart")
    _seed_coffee(name="Geometry", roaster_id=r1)
    _seed_coffee(name="Yirgacheffe", roaster_id=r2)
    resp = authed_client.get(f"/coffees?roaster_id={r1}")
    assert resp.status_code == 200
    body = resp.text
    assert "Geometry" in body
    assert "Yirgacheffe" not in body


def test_filter_by_country_returns_only_matching(authed_client: Any, clean_catalog: None) -> None:
    """GET /coffees?country=Ethiopia → only the coffee whose country=Ethiopia."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_coffee(name="Yirgacheffe", country="Ethiopia")
    _seed_coffee(name="Kiamabara", country="Kenya")
    resp = authed_client.get("/coffees?country=Ethiopia")
    assert resp.status_code == 200
    body = resp.text
    assert "Yirgacheffe" in body
    assert "Kiamabara" not in body


def test_filter_by_process_returns_only_matching(authed_client: Any, clean_catalog: None) -> None:
    """GET /coffees?process=washed → only the washed coffee."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_coffee(name="Geometry", process="washed")
    _seed_coffee(name="Wildcat", process="natural")
    resp = authed_client.get("/coffees?process=washed")
    assert resp.status_code == 200
    body = resp.text
    assert "Geometry" in body
    assert "Wildcat" not in body


def test_filter_archived_false_excludes_archived(authed_client: Any, clean_catalog: None) -> None:
    """Default archived=false → archived coffee excluded."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_coffee(name="Active")
    _seed_coffee(name="Stashed", archived=True)
    resp = authed_client.get("/coffees")
    assert resp.status_code == 200
    body = resp.text
    assert "Active" in body
    assert "Stashed" not in body


def test_filter_archived_true_returns_only_archived(
    authed_client: Any, clean_catalog: None
) -> None:
    """archived=true → archived rows ONLY (UI-SPEC lock — NOT a union)."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_coffee(name="Active")
    _seed_coffee(name="Stashed", archived=True)
    resp = authed_client.get("/coffees?archived=true")
    assert resp.status_code == 200
    body = resp.text
    assert "Stashed" in body
    assert "Active" not in body


# --------------------------------------------------------------------------- #
# Combined filters (AND semantics)                                            #
# --------------------------------------------------------------------------- #


def test_filter_combinations_logical_and(authed_client: Any, clean_catalog: None) -> None:
    """Multi-dim filter → intersection only."""
    _require_postgres()
    _require_p4_migration_applied()
    r1 = _seed_roaster("Onyx")
    r2 = _seed_roaster("Heart")
    target = _seed_coffee(name="Target", roaster_id=r1, country="Ethiopia", process="washed")
    _seed_coffee(name="WrongRoaster", roaster_id=r2, country="Ethiopia", process="washed")
    _seed_coffee(name="WrongCountry", roaster_id=r1, country="Kenya", process="washed")
    _seed_coffee(name="WrongProcess", roaster_id=r1, country="Ethiopia", process="natural")

    resp = authed_client.get(f"/coffees?roaster_id={r1}&country=Ethiopia&process=washed")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "Target" in body
    assert "WrongRoaster" not in body
    assert "WrongCountry" not in body
    assert "WrongProcess" not in body
    # And the target id renders the row marker
    assert f'id="coffee-{target}"' in body


# --------------------------------------------------------------------------- #
# HX-Request fragment branch                                                  #
# --------------------------------------------------------------------------- #


def test_hx_request_with_filters_returns_fragment(authed_client: Any, clean_catalog: None) -> None:
    """HX-Request: true with filter params → fragment body, no <html>."""
    _require_postgres()
    _require_p4_migration_applied()
    r1 = _seed_roaster("Onyx")
    _seed_coffee(name="Geometry", roaster_id=r1)
    resp = authed_client.get(f"/coffees?roaster_id={r1}", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    body = resp.text
    assert "<html" not in body
    assert "<!doctype" not in body.lower()
    assert "Geometry" in body


# --------------------------------------------------------------------------- #
# hx-push-url contract (D-03)                                                 #
# --------------------------------------------------------------------------- #


def test_filter_form_hx_push_url_present(authed_client: Any, clean_catalog: None) -> None:
    """GET /coffees → page body contains hx-push-url="true" on the filter form."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees")
    assert resp.status_code == 200
    body = resp.text
    assert 'hx-push-url="true"' in body
    # Filter form id locked by the page template.
    assert 'id="coffee-filters"' in body
