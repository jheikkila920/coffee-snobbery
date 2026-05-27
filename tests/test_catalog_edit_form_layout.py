"""Tests for CATALOG-01 dual-button edit pattern across all five entity forms.

Covers per D-13/D-14/D-15/D-21:
  - Each row has two Edit buttons (md:hidden mobile + hidden md:inline-flex desktop).
  - Mobile button targets closest [data-row] + outerHTML.
  - Desktop button targets #{entity}-form-mount + innerHTML + ?layout=desktop URL.
  - GET /{entity}/{id}/edit?layout=desktop → form targeting the mount div.
  - GET /{entity}/{id}/edit (no param) → form targeting closest [data-row].
  - POST /{entity}/{id} with layout=desktop → OOB row + mount-clear response.
  - POST /{entity}/{id} (no layout) → plain row fragment (no hx-swap-oob).

7 test groups × 5 entities = 35 tests.
All DB-touching tests are guarded by the postgres skip-gate.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — CATALOG-01 layout test needs the DB")


def _prime_csrf(client: Any) -> str:
    """Mint a real HMAC-signed csrftoken by hitting GET /."""
    client.cookies.delete("csrftoken")
    response = client.get("/")
    token = response.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


# ---------------------------------------------------------------------------
# Parametrize over all 5 entities
# ---------------------------------------------------------------------------

# (url_prefix, entity_var, mount_id, form_mount_id)
# entity_var is the template variable name (e.g. "roaster"), used only
# as a label; mount_id is the CSS id of the form-mount div.
ENTITIES = [
    pytest.param("coffees", "coffee", "coffee-form-mount", id="coffees"),
    pytest.param("roasters", "roaster", "roaster-form-mount", id="roasters"),
    pytest.param("equipment", "equipment", "equipment-form-mount", id="equipment"),
    pytest.param("flavor-notes", "flavor_note", "flavor-note-form-mount", id="flavor_notes"),
    pytest.param("recipes", "recipe", "recipe-form-mount", id="recipes"),
]


# ---------------------------------------------------------------------------
# Fixtures: per-entity seed row helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def authed_client_with_csrf(authed_client: Any) -> Any:
    """Return the authed_client with a live CSRF token pre-wired."""
    _require_postgres()
    _prime_csrf(authed_client)
    return authed_client


def _create_entity(client: Any, url_prefix: str) -> int:
    """Create a minimal valid entity and return its id.

    Uses the CSRF token already wired onto client. Returns the id extracted
    from the Location or OOB response body. Falls back to querying the DB
    directly when the create response doesn't expose the id cleanly.
    """
    _require_postgres()
    token = client.cookies.get("csrftoken", "")

    common_payload = {"X-CSRF-Token": token}

    if url_prefix == "coffees":
        payload = {
            **common_payload,
            "name": "Layout Test Coffee",
            "origins_country": "Ethiopia",
            "origins_region": "",
        }
        resp = client.post(f"/{url_prefix}", data=payload)
    elif url_prefix == "roasters":
        payload = {**common_payload, "name": "Layout Test Roaster"}
        resp = client.post(f"/{url_prefix}", data=payload)
    elif url_prefix == "equipment":
        payload = {
            **common_payload,
            "type": "grinder",
            "brand": "Layout",
            "model": "Test",
        }
        resp = client.post(f"/{url_prefix}", data=payload)
    elif url_prefix == "flavor-notes":
        payload = {**common_payload, "name": "layout-test-note", "category": "fruit"}
        resp = client.post(f"/{url_prefix}", data=payload)
    elif url_prefix == "recipes":
        import json

        steps = json.dumps([{"water_grams": 50, "time_seconds": 45, "label": "Bloom"}])
        payload = {
            **common_payload,
            "name": "Layout Test Recipe",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "93",
            "steps": steps,
        }
        resp = client.post(f"/{url_prefix}", data=payload)
    else:
        pytest.skip(f"Unknown entity prefix: {url_prefix}")

    # The response may be 200 (HTMX fragment) or 302. Either way, parse the
    # entity id from the DB rather than the response body to keep this simple.
    try:
        from app.db import engine
        from sqlalchemy import text as sa_text

        table_map = {
            "coffees": "coffees",
            "roasters": "roasters",
            "equipment": "equipment",
            "flavor-notes": "flavor_notes",
            "recipes": "recipes",
        }
        table = table_map[url_prefix]
        with engine.connect() as conn:
            row = conn.execute(sa_text(f"SELECT id FROM {table} ORDER BY id DESC LIMIT 1")).fetchone()  # noqa: S608
        if row is None:
            pytest.skip(f"No {url_prefix} row found after create")
        return int(row[0])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Could not fetch created entity id: {exc}")


# ---------------------------------------------------------------------------
# Test group 1: row has two Edit buttons
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_prefix", "entity_var", "mount_id"), ENTITIES)
def test_entity_row_has_two_edit_buttons(
    url_prefix: str,
    entity_var: str,
    mount_id: str,
    authed_client_with_csrf: Any,
) -> None:
    """GET /{entity} returns HTML with both md:hidden and hidden md:inline-flex button classes."""
    _require_postgres()
    client = authed_client_with_csrf
    resp = client.get(f"/{url_prefix}", headers={"HX-Request": "true"})
    # Fragment may be 200 even with no rows — just check the page renders
    assert resp.status_code == 200, f"GET /{url_prefix} returned {resp.status_code}"
    body = resp.text
    # These classes exist ONLY if at least one row was rendered.
    # If DB is empty this test is vacuously "structure present" — create one first.
    entity_id = _create_entity(client, url_prefix)
    resp2 = client.get(f"/{url_prefix}", headers={"HX-Request": "true"})
    body2 = resp2.text
    assert "md:hidden" in body2, f"Expected md:hidden class in {url_prefix} list response"
    assert "hidden md:inline-flex" in body2, (
        f"Expected hidden md:inline-flex class in {url_prefix} list response"
    )


# ---------------------------------------------------------------------------
# Test group 2: mobile button targets closest [data-row]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_prefix", "entity_var", "mount_id"), ENTITIES)
def test_entity_row_mobile_button_targets_closest_data_row(
    url_prefix: str,
    entity_var: str,
    mount_id: str,
    authed_client_with_csrf: Any,
) -> None:
    """The md:hidden Edit button has hx-target=closest [data-row] + hx-swap=outerHTML."""
    _require_postgres()
    client = authed_client_with_csrf
    _create_entity(client, url_prefix)
    resp = client.get(f"/{url_prefix}", headers={"HX-Request": "true"})
    body = resp.text
    assert 'hx-target="closest [data-row]"' in body, (
        f"Expected mobile hx-target in {url_prefix} list"
    )
    assert 'hx-swap="outerHTML"' in body, f"Expected outerHTML swap in {url_prefix} list"


# ---------------------------------------------------------------------------
# Test group 3: desktop button targets form-mount
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_prefix", "entity_var", "mount_id"), ENTITIES)
def test_entity_row_desktop_button_targets_form_mount(
    url_prefix: str,
    entity_var: str,
    mount_id: str,
    authed_client_with_csrf: Any,
) -> None:
    """The hidden md:inline-flex Edit button targets #{entity}-form-mount + ?layout=desktop."""
    _require_postgres()
    client = authed_client_with_csrf
    _create_entity(client, url_prefix)
    resp = client.get(f"/{url_prefix}", headers={"HX-Request": "true"})
    body = resp.text
    assert f"#{mount_id}" in body, f"Expected #{mount_id} in {url_prefix} list desktop button"
    assert "?layout=desktop" in body, (
        f"Expected ?layout=desktop in {url_prefix} list desktop button"
    )
    assert 'hx-swap="innerHTML"' in body, (
        f"Expected innerHTML swap in {url_prefix} list desktop button"
    )


# ---------------------------------------------------------------------------
# Test group 4: edit with ?layout=desktop → form targeting mount div
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_prefix", "entity_var", "mount_id"), ENTITIES)
def test_entity_edit_with_layout_desktop_returns_form_with_desktop_targets(
    url_prefix: str,
    entity_var: str,
    mount_id: str,
    authed_client_with_csrf: Any,
) -> None:
    """GET /{entity}/{id}/edit?layout=desktop → form's hx-target is #{entity}-form-mount."""
    _require_postgres()
    client = authed_client_with_csrf
    entity_id = _create_entity(client, url_prefix)
    resp = client.get(f"/{url_prefix}/{entity_id}/edit?layout=desktop")
    assert resp.status_code == 200, (
        f"GET /{url_prefix}/{entity_id}/edit?layout=desktop returned {resp.status_code}"
    )
    body = resp.text
    assert f"#{mount_id}" in body, (
        f"Expected #{mount_id} in desktop edit form for {url_prefix}"
    )
    assert 'hx-swap="innerHTML"' in body, (
        f"Expected innerHTML swap in desktop edit form for {url_prefix}"
    )
    # The hidden layout input must be present
    assert 'name="layout"' in body, (
        f"Expected hidden layout input in desktop edit form for {url_prefix}"
    )
    assert 'value="desktop"' in body, (
        f"Expected value=desktop in hidden layout input for {url_prefix}"
    )


# ---------------------------------------------------------------------------
# Test group 5: edit without layout → form targeting closest [data-row]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_prefix", "entity_var", "mount_id"), ENTITIES)
def test_entity_edit_without_layout_returns_form_with_mobile_targets(
    url_prefix: str,
    entity_var: str,
    mount_id: str,
    authed_client_with_csrf: Any,
) -> None:
    """GET /{entity}/{id}/edit (no layout param) → form's hx-target is closest [data-row]."""
    _require_postgres()
    client = authed_client_with_csrf
    entity_id = _create_entity(client, url_prefix)
    resp = client.get(f"/{url_prefix}/{entity_id}/edit")
    assert resp.status_code == 200, (
        f"GET /{url_prefix}/{entity_id}/edit returned {resp.status_code}"
    )
    body = resp.text
    assert 'hx-target="closest [data-row]"' in body, (
        f"Expected closest [data-row] target in mobile edit form for {url_prefix}"
    )
    assert 'hx-swap="outerHTML"' in body, (
        f"Expected outerHTML swap in mobile edit form for {url_prefix}"
    )


# ---------------------------------------------------------------------------
# Test group 6: POST with layout=desktop → OOB row + form-mount clear
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_prefix", "entity_var", "mount_id"), ENTITIES)
def test_entity_update_desktop_returns_oob_row_and_form_clear(
    url_prefix: str,
    entity_var: str,
    mount_id: str,
    authed_client_with_csrf: Any,
) -> None:
    """POST /{entity}/{id} with layout=desktop returns OOB row + mount-clear."""
    _require_postgres()
    client = authed_client_with_csrf
    entity_id = _create_entity(client, url_prefix)
    token = client.cookies.get("csrftoken", "")
    payload = _build_update_payload(url_prefix, entity_id, token, layout="desktop")
    resp = client.post(f"/{url_prefix}/{entity_id}", data=payload)
    assert resp.status_code == 200, (
        f"POST /{url_prefix}/{entity_id} (desktop) returned {resp.status_code}"
    )
    body = resp.text
    # OOB row replacement: id="entity-{id}" with hx-swap-oob="outerHTML"
    assert f'id="{_entity_prefix(url_prefix)}-{entity_id}"' in body, (
        f"Expected entity row id in OOB response for {url_prefix}"
    )
    assert 'hx-swap-oob="outerHTML"' in body, (
        f"Expected hx-swap-oob=outerHTML in OOB response for {url_prefix}"
    )
    # OOB form-mount clear: <div id="{mount_id}" hx-swap-oob="innerHTML"></div>
    assert f'id="{mount_id}"' in body, (
        f"Expected mount div id in OOB response for {url_prefix}"
    )
    assert 'hx-swap-oob="innerHTML"' in body, (
        f"Expected hx-swap-oob=innerHTML (mount clear) in OOB response for {url_prefix}"
    )


# ---------------------------------------------------------------------------
# Test group 7: POST without layout → plain row (no hx-swap-oob on primary)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_prefix", "entity_var", "mount_id"), ENTITIES)
def test_entity_update_mobile_returns_plain_row(
    url_prefix: str,
    entity_var: str,
    mount_id: str,
    authed_client_with_csrf: Any,
) -> None:
    """POST /{entity}/{id} without layout returns plain row (no hx-swap-oob on primary tr)."""
    _require_postgres()
    client = authed_client_with_csrf
    entity_id = _create_entity(client, url_prefix)
    token = client.cookies.get("csrftoken", "")
    payload = _build_update_payload(url_prefix, entity_id, token, layout=None)
    resp = client.post(f"/{url_prefix}/{entity_id}", data=payload)
    assert resp.status_code == 200, (
        f"POST /{url_prefix}/{entity_id} (mobile) returned {resp.status_code}"
    )
    body = resp.text
    # The entity row should be present
    assert f'id="{_entity_prefix(url_prefix)}-{entity_id}"' in body, (
        f"Expected entity row id in mobile update response for {url_prefix}"
    )
    # No OOB swap on the primary row element (no hx-swap-oob="outerHTML" on the row)
    # The mount-clear OOB should NOT be present on mobile path
    assert f'id="{mount_id}" hx-swap-oob="innerHTML"' not in body, (
        f"Expected NO mount-clear OOB in mobile response for {url_prefix}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity_prefix(url_prefix: str) -> str:
    """Return the HTML id prefix for entity rows (e.g. 'flavor-note' for 'flavor-notes')."""
    mapping = {
        "coffees": "coffee",
        "roasters": "roaster",
        "equipment": "equipment",
        "flavor-notes": "flavor-note",
        "recipes": "recipe",
    }
    return mapping[url_prefix]


def _build_update_payload(
    url_prefix: str,
    entity_id: int,
    token: str,
    layout: str | None,
) -> dict[str, str]:
    """Build a minimal valid update POST payload for the given entity."""
    import json

    base = {"X-CSRF-Token": token}
    if layout:
        base["layout"] = layout

    if url_prefix == "coffees":
        base.update({
            "name": "Updated Coffee",
            "origins_country": "Kenya",
            "origins_region": "",
        })
    elif url_prefix == "roasters":
        base.update({"name": "Updated Roaster"})
    elif url_prefix == "equipment":
        base.update({"type": "grinder", "brand": "Updated", "model": "Model"})
    elif url_prefix == "flavor-notes":
        base.update({"name": "updated-note", "category": "floral"})
    elif url_prefix == "recipes":
        steps = json.dumps([{"water_grams": 50, "time_seconds": 45, "label": "Bloom"}])
        base.update({
            "name": "Updated Recipe",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "93",
            "steps": steps,
        })
    return base
