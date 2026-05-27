"""Real router tests for plan 04-06 (replaces the Wave-0 stub).

Cases per 04-VALIDATION.md row 04-06-NN. Mirrors the structure of
``tests/phase_04/test_routers_roasters.py`` minus the modal-flow and
autocomplete tests (equipment has neither — no mini-modal, no
autocomplete endpoint).

Uses:

* ``authed_client`` — session cookie preloaded; we re-arm the CSRF
  token per-test via ``_prime_csrf`` (the conftest fixture's literal
  placeholder fails starlette-csrf's signed-token check).
* ``csrf_client`` — same session but the cookie/header are
  intentionally mismatched (negative-CSRF probe).
* ``clean_equipment`` — local fixture: wipes ``equipment`` before AND
  after each test so rows don't bleed across tests.

Most tests require Postgres + the p4_shared_catalog migration.
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
        pytest.skip("Postgres not reachable — Phase 4 router test needs the DB")


def _require_p4_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.equipment')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p4_shared_catalog migration not applied")


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real, signed csrftoken; wire it onto the client.

    Same shape as the helper in ``test_routers_roasters.py`` — the
    conftest fixture preloads a literal placeholder string that fails
    starlette-csrf's ``URLSafeSerializer.loads`` signature check. Drop
    the placeholder, GET ``/`` to coax a fresh Set-Cookie, then re-wire
    the default header.
    """
    client.cookies.delete("csrftoken")
    response = client.get("/")
    token = response.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


@pytest.fixture
def clean_equipment() -> Iterator[None]:
    """Wipe the equipment table before AND after each router test.

    Equipment has no incoming FKs in Phase 4 (Phase 5 brew_sessions will
    reference brewer_id / grinder_id / kettle_id, but those tables don't
    exist yet). A single ``DELETE FROM equipment`` is sufficient.
    """
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM equipment"))

    _reset()
    yield
    _reset()


def _seed_equipment(**kwargs: Any) -> int:
    """Insert an equipment row via the service and return its id."""
    from app.db import SessionLocal
    from app.services import equipment as equipment_service

    defaults = {
        "type_": kwargs.pop("type_", kwargs.pop("type", "brewer")),
        "brand": kwargs.pop("brand", "Hario"),
        "model": kwargs.pop("model", "V60-02"),
        "notes": kwargs.pop("notes", ""),
        "by_user_id": kwargs.pop("by_user_id", 0),
    }
    with SessionLocal() as db:
        equipment = equipment_service.create_equipment(db, **defaults)
        return equipment.id


# --------------------------------------------------------------------------- #
# GET /equipment — list page                                                  #
# --------------------------------------------------------------------------- #


def test_list_equipment_renders(authed_client: Any, clean_equipment: None) -> None:
    """Authenticated GET /equipment → 200 + page HTML with h1."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/equipment")
    assert resp.status_code == 200
    body = resp.text
    assert "<h1" in body
    assert "Equipment" in body


def test_list_equipment_grouped_by_type(authed_client: Any, clean_equipment: None) -> None:
    """Seed 2 brewers + 1 grinder → list has ≥ 2 type group headings."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_equipment(type_="brewer", brand="Hario", model="V60-02")
    _seed_equipment(type_="brewer", brand="Kalita", model="Wave 185")
    _seed_equipment(type_="grinder", brand="Comandante", model="C40")
    resp = authed_client.get("/equipment")
    assert resp.status_code == 200
    body = resp.text
    # UI-SPEC §Equipment: group heading style `text-lg font-semibold`.
    # Two distinct types → at least two h2 headings carrying that class.
    assert body.count("text-lg font-semibold") >= 2
    # The brewer and grinder rows appear.
    assert "Hario" in body
    assert "Kalita" in body
    assert "Comandante" in body


# --------------------------------------------------------------------------- #
# POST /equipment — create                                                    #
# --------------------------------------------------------------------------- #


def test_create_valid_brewer(authed_client: Any, clean_equipment: None) -> None:
    """Valid POST → 200 + OOB list update; form mount collapsed.

    CR-01/WR-01 fix (plan 13-03 review): the form targets #equipment-form-mount.
    On success the response body is swapped into #equipment-form-mount (emptying
    it), and contains an OOB div that updates #equipment-list with the full list.
    """
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/equipment",
        data={
            "type": "brewer",
            "brand": "Hario",
            "model": "V60-02",
            "notes": "",
        },
    )
    assert resp.status_code == 200, resp.text
    assert 'id="equipment-' in resp.text
    # Success response contains OOB swap that updates #equipment-list.
    assert 'hx-swap-oob="innerHTML"' in resp.text
    # List-container markers appear inside the OOB div.
    assert "space-y-3" in resp.text or 'class="hidden md:block"' in resp.text
    # No form is rendered in the response — only the row + the OOB list update.
    # (15.1-05 added per-row desktop edit buttons that reference #equipment-form-mount
    # as hx-target, so the literal string is now present in row markup; the contract
    # being tested is the absence of a re-rendered <form>.)
    assert "<form " not in resp.text


def test_create_rejects_unknown_type(authed_client: Any, clean_equipment: None) -> None:
    """Invalid type value → 200 + form re-render with error styling."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/equipment",
        data={
            "type": "grinder_v2",  # not in the 6-value enum.
            "brand": "Comandante",
            "model": "C40",
            "notes": "",
        },
    )
    assert resp.status_code == 200
    # Form re-render carries the error styling.
    assert "text-red-700" in resp.text


def test_create_rejects_blank_brand(authed_client: Any, clean_equipment: None) -> None:
    """Blank brand → 200 + form re-render with error class + preserved values."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/equipment",
        data={
            "type": "brewer",
            "brand": "",
            "model": "V60-02",
            "notes": "",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "text-red-700" in body
    # Submitted values preserved on re-render (D-04).
    assert "V60-02" in body


# --------------------------------------------------------------------------- #
# GET /equipment/{id}/edit + POST update                                      #
# --------------------------------------------------------------------------- #


def test_edit_pre_populates(authed_client: Any, clean_equipment: None) -> None:
    """GET /equipment/{id}/edit → form fragment with existing brand in value=."""
    _require_postgres()
    _require_p4_migration_applied()
    eid = _seed_equipment(type_="brewer", brand="Hario", model="V60-02")
    resp = authed_client.get(f"/equipment/{eid}/edit")
    assert resp.status_code == 200
    assert 'value="Hario"' in resp.text


def test_update_persists(authed_client: Any, clean_equipment: None) -> None:
    """POST /equipment/{id} → DB reflects the new brand."""
    _require_postgres()
    _require_p4_migration_applied()
    eid = _seed_equipment(type_="brewer", brand="Hario", model="V60-02")
    _prime_csrf(authed_client)
    resp = authed_client.post(
        f"/equipment/{eid}",
        data={
            "type": "brewer",
            "brand": "Hario Co.",
            "model": "V60-02",
            "notes": "",
        },
    )
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import equipment as equipment_service

    with SessionLocal() as db:
        rows = equipment_service.list_equipment(db, include_archived=False)
    brands = [r.brand for r in rows]
    assert "Hario Co." in brands
    assert "Hario" not in brands


# --------------------------------------------------------------------------- #
# POST /equipment/{id}/archive                                                #
# --------------------------------------------------------------------------- #


def test_archive_marks_archived(authed_client: Any, clean_equipment: None) -> None:
    """POST /equipment/{id}/archive → DB row.archived=True."""
    _require_postgres()
    _require_p4_migration_applied()
    eid = _seed_equipment(type_="brewer", brand="Hario", model="V60-02")
    _prime_csrf(authed_client)
    resp = authed_client.post(f"/equipment/{eid}/archive")
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import equipment as equipment_service

    with SessionLocal() as db:
        row = equipment_service.get_equipment(db, equipment_id=eid)
        assert row is not None
        assert row.archived is True


# --------------------------------------------------------------------------- #
# usage_count default                                                         #
# --------------------------------------------------------------------------- #


def test_usage_count_defaults_zero(clean_equipment: None) -> None:
    """Newly created equipment has usage_count == 0 (Phase 5 increments)."""
    _require_postgres()
    _require_p4_migration_applied()
    eid = _seed_equipment(type_="brewer", brand="Hario", model="V60-02")

    from app.db import SessionLocal
    from app.services import equipment as equipment_service

    with SessionLocal() as db:
        row = equipment_service.get_equipment(db, equipment_id=eid)
        assert row is not None
        assert row.usage_count == 0


# --------------------------------------------------------------------------- #
# Mass-assignment (T-04-MASS)                                                 #
# --------------------------------------------------------------------------- #


def test_extra_field_rejected(authed_client: Any, clean_equipment: None) -> None:
    """Extra form field → 200 + form re-render (T-04-MASS via extra='forbid')."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/equipment",
        data={
            "type": "brewer",
            "brand": "Hario",
            "model": "V60-02",
            "notes": "",
            "is_admin": "true",  # not in EquipmentCreate — must be rejected.
        },
    )
    assert resp.status_code == 200
    # Form re-render carries the error styling.
    assert "text-red-700" in resp.text


# --------------------------------------------------------------------------- #
# CSRF                                                                        #
# --------------------------------------------------------------------------- #


def test_csrf_missing_returns_403(csrf_client: Any, clean_equipment: None) -> None:
    """POST /equipment with mismatched CSRF → 403 from CSRFMiddleware."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = csrf_client.post(
        "/equipment",
        data={"type": "brewer", "brand": "Hario", "model": "V60-02"},
    )
    assert resp.status_code == 403
