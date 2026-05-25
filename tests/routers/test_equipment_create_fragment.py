"""C2 regression tests: POST /equipment and POST /coffees must return the full list
fragment, not a bare <tr> row fragment (plan 13-03).

Covers:
  test_equipment_create_returns_list_fragment — POST /equipment success returns
    equipment_list.html content (space-y-3 card section + hidden md:block table);
    body does NOT contain equipment-form-mount (OOB clear removed); newly created
    equipment brand appears in the body.

  test_coffee_create_returns_list_fragment — POST /coffees success returns
    coffee_list.html content (space-y-3 card section + hidden md:block table);
    body does NOT contain coffee-form-mount; newly created coffee name appears.

Both tests are RED before Tasks 2-3 change the create handlers; GREEN after.
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
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_equipment_create_returns_list_fragment(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_create_fragment: None,
) -> None:
    """POST /equipment success must return the equipment_list.html fragment.

    Asserts:
    - HTTP 200
    - Response body contains list-container markers (space-y-3 OR hidden md:block)
    - Response body does NOT contain equipment-form-mount (OOB clear is removed)
    - The newly created equipment brand appears in the body
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
    # Must contain list-container structure (equipment_list.html markers)
    assert "space-y-3" in body or 'class="hidden md:block"' in body, (
        "Response should contain equipment list container markup "
        "(space-y-3 card section or hidden md:block table)"
    )
    # OOB form-clear must be gone (C2)
    assert "equipment-form-mount" not in body, (
        "Response must NOT contain equipment-form-mount — OOB form clear was removed"
    )
    # Newly created equipment must appear
    assert _EQUIPMENT_BRAND in body, (
        f"Newly created equipment brand '{_EQUIPMENT_BRAND}' not found in response"
    )


def test_coffee_create_returns_list_fragment(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_create_fragment: None,
) -> None:
    """POST /coffees success must return the coffee_list.html fragment.

    Asserts:
    - HTTP 200
    - Response body contains list-container markers (space-y-3 OR hidden md:block)
    - Response body does NOT contain coffee-form-mount (no OOB clear remnant)
    - The newly created coffee name appears in the body
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
    # Must contain list-container structure (coffee_list.html markers)
    assert "space-y-3" in body or 'class="hidden md:block"' in body, (
        "Response should contain coffee list container markup "
        "(space-y-3 card section or hidden md:block table)"
    )
    # No OOB form-clear or form-mount id (C2 — form collapses via hx-target swap)
    assert "coffee-form-mount" not in body, (
        "Response must NOT contain coffee-form-mount — form collapse is via list-swap target"
    )
    # Newly created coffee must appear
    assert _COFFEE_NAME in body, (
        f"Newly created coffee name '{_COFFEE_NAME}' not found in response"
    )
