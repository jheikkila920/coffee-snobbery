"""Regression tests for the create flow of POST /equipment and POST /coffees.

Covers CR-01 + WR-01 (plan 13-03 review remediation):
  - VALIDATION ERROR must re-render the form into the form mount; the list
    must remain intact (response is the form fragment, NOT the list fragment).
  - SUCCESS must update the list (via OOB swap) AND collapse the form mount
    (the response body swapped into #*-form-mount is empty except for the
    OOB div; the form mount ends up empty, the list gets the OOB update).

test_equipment_create_returns_list_fragment — POST /equipment success:
    response body contains OOB list update; newly created brand in body;
    form-mount ID NOT in body (the empty form-mount response carries no
    form-mount markup itself — the OOB div updates #equipment-list only).

test_coffee_create_returns_list_fragment — POST /coffees success:
    same contract for coffees.

test_equipment_create_invalid_renders_form_not_list — POST /equipment with
    blank brand: response is the form fragment; does NOT contain list-only
    markers; list container is NOT replaced.

test_coffee_create_invalid_renders_form_not_list — POST /coffees with blank
    name: same contract for coffees.

Both test modules are RED before the CR-01/WR-01 fix; GREEN after.
Both tests clean their own catalog rows (LIKE-scoped) to avoid cross-module
FK pollution (see memory full-suite-test-isolation-gaps.md).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Skip gates                                                                   #
# --------------------------------------------------------------------------- #

_EQUIPMENT_BRAND = "FragTestBrand"
_EQUIPMENT_MODEL = "FragTestModel"
_COFFEE_NAME = "FragTestCoffee Washed"


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — plan 13-03 router test needs the DB")


def _require_catalog_tables() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT to_regclass('public.equipment')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")


# --------------------------------------------------------------------------- #
# Clean fixture — LIKE-scoped deletes so this test's rows never pollute the   #
# full suite (memory: full-suite-test-isolation-gaps.md).                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def clean_create_fragment() -> Iterator[None]:
    """Wipe this test's equipment + coffee rows before AND after."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM equipment WHERE brand LIKE :prefix"),
                {"prefix": f"{_EQUIPMENT_BRAND}%"},
            )
            conn.execute(
                text("DELETE FROM coffees WHERE name LIKE :prefix"),
                {"prefix": f"{_COFFEE_NAME}%"},
            )

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# HTMX client helpers (mirrors test_brew_router._authed_client pattern)       #
# --------------------------------------------------------------------------- #


def _authed_client(app: Any, signed_cookie: str) -> Any:
    """Build a TestClient with the session cookie + a real signed CSRF pair."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.cookies.set("session_id", signed_cookie)
    _prime_csrf(client)
    return client


def _prime_csrf(client: Any) -> str:
    """GET / to mint a real signed csrftoken; wire it onto the client."""
    client.cookies.delete("csrftoken")
    response = client.get("/")
    token = response.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


# --------------------------------------------------------------------------- #
# SUCCESS PATH tests                                                           #
# --------------------------------------------------------------------------- #


def test_equipment_create_returns_list_fragment(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_create_fragment: None,
) -> None:
    """POST /equipment success: OOB list update in body; form mount NOT in body.

    CR-01/WR-01 fix: the form targets #equipment-form-mount (innerHTML).
    On success the response body (swapped into the form mount) is empty
    except for the OOB div that updates #equipment-list. The form mount
    ends up empty (form collapsed). The list is updated via OOB swap.

    Asserts:
    - HTTP 200
    - Response body contains OOB list update (hx-swap-oob + list markers)
    - The newly created equipment brand appears in the body (via OOB list)
    - equipment-form-mount NOT in the response body
    """
    _require_postgres()
    _require_catalog_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])

    r = client.post(
        "/equipment",
        data={
            "type": "grinder",
            "brand": _EQUIPMENT_BRAND,
            "model": _EQUIPMENT_MODEL,
            "notes": "",
        },
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"

    body = r.text
    # Must contain the OOB swap div wrapping the updated list
    assert 'hx-swap-oob="innerHTML"' in body, (
        "Success response must contain an OOB swap div to update #equipment-list"
    )
    # List-container structure appears inside the OOB div
    assert "space-y-3" in body or 'class="hidden md:block"' in body, (
        "Response should contain equipment list container markup "
        "(space-y-3 card section or hidden md:block table)"
    )
    # form-mount ID must NOT appear in the response body
    assert "equipment-form-mount" not in body, (
        "Response must NOT contain equipment-form-mount — the response body is "
        "swapped into #equipment-form-mount (emptying it); it should not reference itself"
    )
    # Newly created equipment must appear (inside the OOB list)
    assert _EQUIPMENT_BRAND in body, (
        f"Newly created equipment brand '{_EQUIPMENT_BRAND}' not found in response"
    )


def test_coffee_create_returns_list_fragment(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_create_fragment: None,
) -> None:
    """POST /coffees success: OOB list update in body; form mount NOT in body.

    CR-01/WR-01 fix: the form targets #coffee-form-mount (innerHTML).
    On success the response body (swapped into the form mount) is empty
    except for the OOB div that updates #coffee-list. The form mount
    ends up empty (form collapsed). The list is updated via OOB swap.

    Asserts:
    - HTTP 200
    - Response body contains OOB list update (hx-swap-oob + list markers)
    - The newly created coffee name appears in the body (via OOB list)
    - coffee-form-mount NOT in the response body
    """
    _require_postgres()
    _require_catalog_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])

    r = client.post(
        "/coffees",
        data={
            "name": _COFFEE_NAME,
        },
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"

    body = r.text
    # Must contain the OOB swap div wrapping the updated list
    assert 'hx-swap-oob="innerHTML"' in body, (
        "Success response must contain an OOB swap div to update #coffee-list"
    )
    # List-container structure appears inside the OOB div
    assert "space-y-3" in body or 'class="hidden md:block"' in body, (
        "Response should contain coffee list container markup "
        "(space-y-3 card section or hidden md:block table)"
    )
    # form-mount ID must NOT appear in the response body
    assert "coffee-form-mount" not in body, (
        "Response must NOT contain coffee-form-mount — the response body is "
        "swapped into #coffee-form-mount (emptying it); it should not reference itself"
    )
    # Newly created coffee must appear (inside the OOB list)
    assert _COFFEE_NAME in body, f"Newly created coffee name '{_COFFEE_NAME}' not found in response"


# --------------------------------------------------------------------------- #
# ERROR PATH tests (CR-01 regression: these would have caught the bug)        #
# --------------------------------------------------------------------------- #


def test_equipment_create_invalid_renders_form_not_list(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_create_fragment: None,
) -> None:
    """POST /equipment with blank brand: response is the form, NOT the list.

    CR-01 regression test. Before the fix, a validation error swapped
    the form fragment into #equipment-list (destroying the list). After
    the fix, the form targets #equipment-form-mount, so the error re-render
    lands in the form mount and the list remains intact.

    Asserts:
    - HTTP 200
    - Response contains the form fragment (hx-post="/equipment" present)
    - Response contains validation error styling (text-red-700)
    - Response does NOT contain full-list-only markup that would only
      appear if the list fragment were returned (equipment group headings
      rendered by equipment_list.html: "text-lg font-semibold"). The form
      has no such headings.
    - Response does NOT contain hx-swap-oob (the error path is a plain
      form re-render, no OOB update needed)
    - Submitted values preserved (D-04): submitted model value in body
    """
    _require_postgres()
    _require_catalog_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])

    r = client.post(
        "/equipment",
        data={
            "type": "grinder",
            "brand": "",  # blank — triggers ValidationError
            "model": _EQUIPMENT_MODEL,
            "notes": "",
        },
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"

    body = r.text
    # Must be the form fragment (contains the POST action)
    assert 'hx-post="/equipment"' in body, (
        "Validation error response must be the form fragment (hx-post=/equipment)"
    )
    # Must have validation error styling
    assert "text-red-700" in body, (
        "Validation error response must contain error styling (text-red-700)"
    )
    # Must NOT be the list fragment (no group headings that equipment_list.html renders)
    assert "text-lg font-semibold" not in body, (
        "Validation error response must NOT contain list group headings — "
        "the form was incorrectly swapped into #equipment-list (CR-01 regression)"
    )
    # Must NOT contain OOB swap (error path is plain form re-render)
    assert "hx-swap-oob" not in body, (
        "Validation error response must NOT contain hx-swap-oob — only success uses OOB"
    )
    # Submitted model value preserved (D-04)
    assert _EQUIPMENT_MODEL in body, (
        f"Submitted model '{_EQUIPMENT_MODEL}' must be preserved in error re-render (D-04)"
    )


def test_coffee_create_invalid_renders_form_not_list(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_create_fragment: None,
) -> None:
    """POST /coffees with blank name: response is the form, NOT the list.

    CR-01 regression test. Before the fix, a validation error swapped
    the form fragment into #coffee-list (destroying the list). After the
    fix, the form targets #coffee-form-mount, so the error re-render
    lands in the form mount and the list remains intact.

    Asserts:
    - HTTP 200
    - Response contains the form fragment (hx-post="/coffees" present)
    - Response contains validation error styling (text-red-700)
    - Response does NOT contain full-list-only markup (hidden md:block table
      wrapper that coffee_list.html renders but the form does not)
    - Response does NOT contain hx-swap-oob
    - Submitted values preserved (D-04): submitted country value in body
    """
    _require_postgres()
    _require_catalog_tables()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])

    r = client.post(
        "/coffees",
        data={
            "name": "",  # blank — triggers ValidationError
            "country": "Ethiopia",
            "notes": "",
        },
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"

    body = r.text
    # Must be the form fragment (contains the POST action)
    assert 'hx-post="/coffees"' in body, (
        "Validation error response must be the form fragment (hx-post=/coffees)"
    )
    # Must have validation error styling
    assert "text-red-700" in body, (
        "Validation error response must contain error styling (text-red-700)"
    )
    # Must NOT contain the list's desktop table wrapper (only in coffee_list.html)
    assert 'class="hidden md:block"' not in body, (
        "Validation error response must NOT contain list table wrapper — "
        "the form was incorrectly swapped into #coffee-list (CR-01 regression)"
    )
    # Must NOT contain OOB swap (error path is plain form re-render)
    assert "hx-swap-oob" not in body, (
        "Validation error response must NOT contain hx-swap-oob — only success uses OOB"
    )
    # Submitted country value preserved (D-04)
    assert "Ethiopia" in body, (
        "Submitted country 'Ethiopia' must be preserved in error re-render (D-04)"
    )
