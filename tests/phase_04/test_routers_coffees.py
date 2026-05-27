"""Real router tests for plan 04-07 (replaces the Wave-0 stub).

Cases per 04-VALIDATION.md row 04-07-NN. Mirrors the structure of
``tests/phase_04/test_routers_roasters.py``.

Uses:

* ``authed_client`` — session cookie preloaded; we re-arm the CSRF token
  per-test via ``_prime_csrf`` (the conftest fixture's literal placeholder
  fails starlette-csrf's signed-token check).
* ``csrf_client`` — same session but the cookie/header are intentionally
  mismatched (negative-CSRF probe).
* ``clean_catalog`` — local fixture: wipes the bag/coffee/flavor/roaster
  chain before AND after each test.

Most tests require Postgres + the p4_shared_catalog migration. Uses the
same ``_require_*`` helpers as ``test_routers_roasters.py``.
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
            row = conn.execute(text("SELECT to_regclass('public.coffees')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p4_shared_catalog migration not applied")


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real, signed csrftoken; wire it onto the client.

    Same shape as the helper in ``test_routers_roasters.py``.
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
def clean_catalog() -> Iterator[None]:
    """Wipe the catalog chain before AND after each router test.

    Reset order respects FKs: bags → coffees → flavor_notes → roasters.
    """
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


def _seed_roaster(**kwargs: Any) -> int:
    from app.db import SessionLocal
    from app.services import roasters as roasters_service

    defaults = {
        "name": kwargs.pop("name", "Onyx"),
        "location": kwargs.pop("location", None),
        "website": kwargs.pop("website", None),
        "notes": kwargs.pop("notes", ""),
        "by_user_id": kwargs.pop("by_user_id", 0),
    }
    with SessionLocal() as db:
        return roasters_service.create_roaster(db, **defaults).id


def _seed_flavor_note(**kwargs: Any) -> int:
    from app.db import SessionLocal
    from app.services import flavor_notes as flavor_notes_service

    defaults = {
        "name": kwargs.pop("name", "Bergamot"),
        "category": kwargs.pop("category", "fruit"),
        "by_user_id": kwargs.pop("by_user_id", 0),
    }
    with SessionLocal() as db:
        return flavor_notes_service.create_flavor_note(db, **defaults).id


def _seed_coffee(**kwargs: Any) -> int:
    from app.db import SessionLocal
    from app.services import coffees as coffees_service

    country = kwargs.pop("country", None)
    kwargs.pop("origin", None)
    kwargs.pop("varietal", None)
    defaults: dict[str, Any] = {
        "name": kwargs.pop("name", "Geometry"),
        "roaster_id": kwargs.pop("roaster_id", None),
        "origins": [(country, None)] if country else [],
        "process": kwargs.pop("process", None),
        "roast_level": kwargs.pop("roast_level", None),
        "notes": kwargs.pop("notes", ""),
        "advertised_flavor_note_ids": kwargs.pop("advertised_flavor_note_ids", []),
        "by_user_id": kwargs.pop("by_user_id", 0),
    }
    with SessionLocal() as db:
        return coffees_service.create_coffee(db, **defaults).id


def _seed_bag(coffee_id: int) -> int:
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        row = conn.execute(
            text("INSERT INTO bags (coffee_id) VALUES (:cid) RETURNING id"),
            {"cid": coffee_id},
        ).scalar_one()
    return int(row)


# --------------------------------------------------------------------------- #
# GET /coffees — list page                                                    #
# --------------------------------------------------------------------------- #


def test_list_coffees_renders_page(authed_client: Any, clean_catalog: None) -> None:
    """Authed GET /coffees → 200 + page HTML with h1 + Coffees + filter bar."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees")
    assert resp.status_code == 200
    body = resp.text
    assert "<h1" in body
    assert "Coffees" in body
    assert 'id="coffee-filters"' in body


def test_list_coffees_hx_request_returns_fragment_only(
    authed_client: Any, clean_catalog: None
) -> None:
    """HX-Request: true → fragment without <html>/<!doctype>."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert "<!doctype" not in resp.text.lower()


def test_list_coffees_includes_responsive_layout_markers(
    authed_client: Any, clean_catalog: None
) -> None:
    """Body includes BOTH `hidden md:block` desktop AND `md:hidden` mobile markers."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_roaster(name="Onyx")
    _seed_coffee(name="Geometry", roaster_id=rid)
    resp = authed_client.get("/coffees")
    assert resp.status_code == 200
    body = resp.text
    # The desktop table wrapper uses `hidden md:block`; the mobile card
    # list uses `md:hidden`. CAT-07 dual-layout shipped.
    assert "hidden md:block" in body
    assert "md:hidden" in body


# --------------------------------------------------------------------------- #
# POST /coffees — create                                                      #
# --------------------------------------------------------------------------- #


def test_create_coffee_minimal_valid(authed_client: Any, clean_catalog: None) -> None:
    """POST minimal valid form → 200 + OOB list update; form mount collapsed.

    CR-01/WR-01 fix (plan 13-03 review): the form targets #coffee-form-mount.
    On success the response body is swapped into #coffee-form-mount (emptying
    it), and contains an OOB div that updates #coffee-list with the full list.
    """
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/coffees",
        data={
            "name": "Geometry",
            "process": "washed",
            "roast_level": "light",
            "origins_country": "Ethiopia",
            "origins_region": "",
            "notes": "",
        },
    )
    assert resp.status_code == 200, resp.text
    assert 'id="coffee-' in resp.text
    # Success response contains OOB swap that updates #coffee-list.
    assert 'hx-swap-oob="innerHTML"' in resp.text
    # List-container markers appear inside the OOB div.
    assert "space-y-3" in resp.text or 'class="hidden md:block"' in resp.text
    # No form is rendered in the response — only the row + the OOB list update.
    # (15.1-05 added per-row desktop edit buttons that reference #coffee-form-mount
    # as hx-target, so the literal string is now present in row markup; the contract
    # being tested is the absence of a re-rendered <form>.)
    assert "<form " not in resp.text


def test_create_coffee_with_array_round_trip(authed_client: Any, clean_catalog: None) -> None:
    """POST with advertised_flavor_note_ids → array preserved on get_coffee.

    httpx-0.28 form-encoding gotcha: ``data=[("k","v"), ("k","v2"), ...]``
    (list of 2-tuples) is NOT a supported shape — httpx silently drops the
    body and the request reaches the handler with no form fields, so
    ``CoffeeCreate(name=...)`` fails the required-name check and the
    handler re-renders the form at 200 with the row never persisted. The
    documented httpx shape for repeated form keys is
    ``data={"key": [v1, v2], ...}`` — a dict whose values can be lists.
    The handler reads repeated keys via ``form_data.getlist`` either way.
    """
    _require_postgres()
    _require_p4_migration_applied()
    fn1 = _seed_flavor_note(name="Blueberry", category="fruit")
    fn2 = _seed_flavor_note(name="Jasmine", category="floral")
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/coffees",
        data={
            "name": "Geometry",
            "notes": "",
            "origins_country": "Ethiopia",
            "origins_region": "",
            "advertised_flavor_note_ids": [str(fn1), str(fn2)],
        },
    )
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import coffees as coffees_service

    with SessionLocal() as db:
        rows = coffees_service.list_coffees(db)
    assert len(rows) == 1
    assert rows[0].advertised_flavor_note_ids == [fn1, fn2]


def test_create_coffee_rejects_unknown_process(authed_client: Any, clean_catalog: None) -> None:
    """POST with process=cold_brewed → 200 + form re-render with error."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/coffees",
        data={
            "name": "Bogus",
            "process": "cold_brewed",
            "notes": "",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "text-red-700" in body
    # Submitted name preserved on re-render (D-04).
    assert "Bogus" in body


def test_create_coffee_rejects_blank_name(authed_client: Any, clean_catalog: None) -> None:
    """POST with name="" → 200 + form re-render with error on `name`."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/coffees",
        data={
            "name": "",
            "origins_country": "Ethiopia",
            "origins_region": "",
            "notes": "",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "text-red-700" in body
    # Submitted origin country preserved on re-render (D-04).
    assert "Ethiopia" in body


def test_create_coffee_extra_field_rejected(authed_client: Any, clean_catalog: None) -> None:
    """Extra form field → 200 + form re-render (T-04-MASS via extra='forbid')."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/coffees",
        data={
            "name": "Geometry",
            "is_admin": "true",  # not in CoffeeCreate — must be rejected.
            "notes": "",
        },
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


# --------------------------------------------------------------------------- #
# GET /coffees/{id} — detail page                                             #
# --------------------------------------------------------------------------- #


def test_coffee_detail_page_renders(authed_client: Any, clean_catalog: None) -> None:
    """Seed coffee + bag → GET /coffees/{id} → body has name + Bags + Open new bag."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee(name="Geometry")
    _seed_bag(coffee_id=cid)
    resp = authed_client.get(f"/coffees/{cid}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "Geometry" in body
    # Section heading for bags
    assert "Bags" in body
    # Open new bag affordance is present
    assert "Open new bag" in body
    # Mount div for plan 04-09 to consume
    assert 'id="bag-form-mount"' in body


def test_coffee_detail_page_404_for_unknown_id(authed_client: Any, clean_catalog: None) -> None:
    """GET /coffees/999999 → 404."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees/999999")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# GET /coffees/{id}/edit + POST update                                        #
# --------------------------------------------------------------------------- #


def test_edit_pre_populates_advertised_array(authed_client: Any, clean_catalog: None) -> None:
    """Seed coffee with [id1, id2] → GET /{id}/edit body has hidden inputs for both."""
    _require_postgres()
    _require_p4_migration_applied()
    fn1 = _seed_flavor_note(name="Blueberry", category="fruit")
    fn2 = _seed_flavor_note(name="Jasmine", category="floral")
    cid = _seed_coffee(name="Geometry", advertised_flavor_note_ids=[fn1, fn2])
    resp = authed_client.get(f"/coffees/{cid}/edit")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert f'<input type="hidden" name="advertised_flavor_note_ids" value="{fn1}">' in body
    assert f'<input type="hidden" name="advertised_flavor_note_ids" value="{fn2}">' in body


def test_update_persists_array_change(authed_client: Any, clean_catalog: None) -> None:
    """POST /{id} with [id1] only → array becomes [id1]."""
    _require_postgres()
    _require_p4_migration_applied()
    fn1 = _seed_flavor_note(name="Blueberry", category="fruit")
    fn2 = _seed_flavor_note(name="Jasmine", category="floral")
    cid = _seed_coffee(name="Geometry", advertised_flavor_note_ids=[fn1, fn2])
    _prime_csrf(authed_client)
    # See ``test_create_coffee_with_array_round_trip`` for the httpx-0.28
    # form-encoding gotcha: pass repeated keys via ``data={"k": [v1, v2]}``
    # not via a list of 2-tuples (the latter silently sends no body).
    resp = authed_client.post(
        f"/coffees/{cid}",
        data={
            "name": "Geometry",
            "notes": "",
            "origins_country": "Ethiopia",
            "origins_region": "",
            "advertised_flavor_note_ids": [str(fn1)],
        },
    )
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import coffees as coffees_service

    with SessionLocal() as db:
        row = coffees_service.get_coffee(db, coffee_id=cid)
    assert row is not None
    assert row.advertised_flavor_note_ids == [fn1]


# --------------------------------------------------------------------------- #
# POST /coffees/{id}/archive                                                  #
# --------------------------------------------------------------------------- #


def test_archive_marks_archived(authed_client: Any, clean_catalog: None) -> None:
    """POST /{id}/archive → DB row.archived=True."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee(name="Geometry")
    _prime_csrf(authed_client)
    resp = authed_client.post(f"/coffees/{cid}/archive")
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import coffees as coffees_service

    with SessionLocal() as db:
        row = coffees_service.get_coffee(db, coffee_id=cid)
    assert row is not None
    assert row.archived is True


# --------------------------------------------------------------------------- #
# CSRF                                                                        #
# --------------------------------------------------------------------------- #


def test_csrf_missing_returns_403(csrf_client: Any, clean_catalog: None) -> None:
    """POST /coffees with mismatched CSRF → 403."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = csrf_client.post("/coffees", data={"name": "X"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Form autocomplete attributes (HX-4 + D-13 contract)                         #
# --------------------------------------------------------------------------- #


def test_form_renders_roaster_autocomplete_attributes(
    authed_client: Any, clean_catalog: None
) -> None:
    """GET /coffees/new → body has the locked HX-4 + D-13 + D-14 autocomplete attrs.

    Plan 04-11 extended the trigger clause to add the D-14 ``focus once
    from:closest .field`` re-fetch substrate. The original D-13 debounce
    clause and HX-4 ``hx-sync="this:replace"`` clause stay; both must be
    present as substrings.
    """
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees/new")
    assert resp.status_code == 200
    body = resp.text
    # D-13 (debounce) + HX-4 (sync) substrings still pinned. Plan 04-11
    # appends `, focus once from:closest .field` to the hx-trigger value,
    # so the original full-string match no longer holds — assert by
    # substring to keep the test stable across the contract extension.
    assert "input changed delay:350ms[target.value.length >= 2]" in body
    assert 'hx-sync="this:replace"' in body
    # D-14 mitigation (plan 04-11): focus-once re-fetch from closest .field wrapper.
    assert "focus once from:closest .field" in body
    # Roaster autocomplete target + hidden id field.
    assert 'id="roaster-dropdown"' in body
    assert 'name="roaster_id"' in body
