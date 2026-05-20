"""Real router tests for plan 04-04 (replaces the Wave-0 stub).

Cases per 04-VALIDATION.md row 04-04-NN. Uses:

* ``authed_client`` — session cookie preloaded; we re-arm the CSRF
  token per-test by GETting `/` first so the cookie/header carry a
  signed token starlette-csrf will accept (its `_csrf_tokens_match`
  runs `URLSafeSerializer.loads` — a literal string fails the
  signature check).
* ``csrf_client`` — same session but the cookie/header are
  intentionally mismatched (negative-CSRF probe).
* ``clean_roasters`` — local fixture: wipes ``roasters`` (and the
  dependent ``bags`` + ``coffees``) before AND after each test so
  rows don't bleed across tests.

Most tests require Postgres + the p4_shared_catalog migration. Uses
the same ``_require_*`` helpers as ``test_models_catalog.py``.
"""

from __future__ import annotations

import json
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
            row = conn.execute(text("SELECT to_regclass('public.roasters')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p4_shared_catalog migration not applied")


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real, signed csrftoken; wire it onto the client.

    The conftest ``authed_client`` fixture preloads a literal placeholder
    string into both the cookie and the X-CSRF-Token header — but
    ``starlette-csrf`` validates the token via ``URLSafeSerializer.loads``
    (HMAC-signed). A literal placeholder fails the signature check, so
    every POST 403s.

    The middleware only mints a new csrftoken when the inbound request
    has NO csrftoken cookie at all (``if csrf_cookie is None`` in
    ``CSRFMiddleware.send``). The fixture pre-populates a placeholder,
    so we must explicitly drop the cookie BEFORE the primer GET to
    coax a fresh Set-Cookie out of the middleware. Then we re-wire
    the client default header to match.
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
def clean_roasters() -> Iterator[None]:
    """Wipe the roasters chain before AND after each router test.

    Reset order respects FKs: bags → coffees → roasters.
    """
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM bags"))
            conn.execute(text("DELETE FROM coffees"))
            conn.execute(text("DELETE FROM roasters"))

    _reset()
    yield
    _reset()


def _seed_roaster(**kwargs: Any) -> int:
    """Insert a roaster via the service and return its id."""
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
        roaster = roasters_service.create_roaster(db, **defaults)
        return roaster.id


# --------------------------------------------------------------------------- #
# GET /roasters — list page                                                   #
# --------------------------------------------------------------------------- #


def test_list_roasters_anon_returns_401(client: Any) -> None:
    """Anonymous GET /roasters → 401 from require_user (no redirect — D-13)."""
    resp = client.get("/roasters")
    assert resp.status_code == 401


def test_list_roasters_authed_renders_page(authed_client: Any, clean_roasters: None) -> None:
    """Authenticated GET /roasters → 200 + page HTML with h1 + Add button."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/roasters")
    assert resp.status_code == 200
    body = resp.text
    assert "<h1" in body
    assert "Roasters" in body
    assert "Add roaster" in body


def test_list_roasters_with_hx_request_returns_fragment(
    authed_client: Any, clean_roasters: None
) -> None:
    """HX-Request: true header → fragment (no <html>) instead of full page."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/roasters", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    # Fragment must not be a full document.
    assert "<html" not in resp.text
    assert "<!doctype" not in resp.text.lower()


# --------------------------------------------------------------------------- #
# POST /roasters — create                                                     #
# --------------------------------------------------------------------------- #


def test_create_roaster_valid_returns_row_fragment(
    authed_client: Any, clean_roasters: None
) -> None:
    """Valid form data → 200 with the row fragment (id="roaster-N")."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/roasters",
        data={
            "name": "Onyx",
            "location": "Bentonville, AR",
            "website": "https://onyxcoffeelab.com",
            "notes": "",
        },
    )
    assert resp.status_code == 200, resp.text
    # Row fragment carries the per-row id.
    assert 'id="roaster-' in resp.text
    # The row also carries the OOB form-clear swap on the create path.
    assert "roaster-form-mount" in resp.text


def test_create_roaster_blank_name_returns_form_with_error(
    authed_client: Any, clean_roasters: None
) -> None:
    """Empty name → 200 + form fragment with error class + preserved values."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/roasters",
        data={
            "name": "",
            "location": "Somewhere",
            "website": "",
            "notes": "",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    # Error styling/marker class on the input + paragraph.
    assert "text-red-700" in body
    # Submitted values preserved on re-render (D-04).
    assert "Somewhere" in body


def test_create_roaster_extra_field_rejected(authed_client: Any, clean_roasters: None) -> None:
    """Extra form field → 200 + form re-render (T-04-MASS via extra='forbid')."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/roasters",
        data={
            "name": "Onyx",
            "is_admin": "true",  # not in RoasterCreate — must be rejected.
        },
    )
    assert resp.status_code == 200
    # Form re-render carries the error styling.
    assert "text-red-700" in resp.text


def test_create_roaster_duplicate_name_returns_friendly_error(
    authed_client: Any, clean_roasters: None
) -> None:
    """Duplicate name on create → 200 + 'Name already exists.' inline, not 500.

    The UNIQUE CITEXT name column raises IntegrityError; the service rolls
    back and raises DuplicateNameError, which the router maps to the friendly
    re-render. A case-variant ("onyx" vs seeded "Onyx") also collides.
    """
    _require_postgres()
    _require_p4_migration_applied()
    _seed_roaster(name="Onyx")
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/roasters",
        data={"name": "onyx", "location": "", "website": "", "notes": ""},
    )
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "text-red-700" in body
    assert "Name already exists." in body
    # Session rolled back cleanly → a subsequent valid create still succeeds.
    follow_up = authed_client.post(
        "/roasters",
        data={"name": "Heart", "location": "", "website": "", "notes": ""},
    )
    assert follow_up.status_code == 200, follow_up.text
    assert 'id="roaster-' in follow_up.text


def test_update_roaster_duplicate_name_returns_friendly_error(
    authed_client: Any, clean_roasters: None
) -> None:
    """Renaming a roaster onto an existing name → 200 + friendly error, not 500."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_roaster(name="Onyx")
    rid = _seed_roaster(name="Heart")
    _prime_csrf(authed_client)
    resp = authed_client.post(
        f"/roasters/{rid}",
        data={"name": "Onyx", "location": "", "website": "", "notes": ""},
    )
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "text-red-700" in body
    assert "Name already exists." in body


def test_create_roaster_as_modal_emits_hx_trigger(authed_client: Any, clean_roasters: None) -> None:
    """as_modal=true → empty body + HX-Trigger roaster-created header (D-15)."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/roasters",
        data={"name": "Heart", "as_modal": "true"},
    )
    assert resp.status_code == 200, resp.text
    assert "HX-Trigger" in resp.headers
    payload = json.loads(resp.headers["HX-Trigger"])
    assert "roaster-created" in payload
    inner = payload["roaster-created"]
    assert inner["name"] == "Heart"
    assert isinstance(inner["roaster_id"], int)
    assert inner["roaster_id"] > 0


# --------------------------------------------------------------------------- #
# GET /roasters/{id}/edit + POST update                                       #
# --------------------------------------------------------------------------- #


def test_edit_roaster_returns_form_fragment_prepopulated(
    authed_client: Any, clean_roasters: None
) -> None:
    """GET /roasters/{id}/edit → form fragment with name pre-populated."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_roaster(name="Onyx", location="AR")
    resp = authed_client.get(f"/roasters/{rid}/edit")
    assert resp.status_code == 200
    # The form input renders value="Onyx".
    assert 'value="Onyx"' in resp.text


def test_update_roaster_persists_changes(authed_client: Any, clean_roasters: None) -> None:
    """POST /roasters/{id} with new name → DB reflects the change."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_roaster(name="Onyx")
    _prime_csrf(authed_client)
    resp = authed_client.post(
        f"/roasters/{rid}",
        data={"name": "Onyx Coffee Lab", "location": "", "website": "", "notes": ""},
    )
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import roasters as roasters_service

    with SessionLocal() as db:
        rows = roasters_service.list_roasters(db, include_archived=False)
    names = [r.name for r in rows]
    assert "Onyx Coffee Lab" in names
    assert "Onyx" not in names


# --------------------------------------------------------------------------- #
# POST /roasters/{id}/archive                                                 #
# --------------------------------------------------------------------------- #


def test_archive_roaster_marks_archived(authed_client: Any, clean_roasters: None) -> None:
    """POST /roasters/{id}/archive → DB row.archived=True."""
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_roaster(name="Onyx")
    _prime_csrf(authed_client)
    resp = authed_client.post(f"/roasters/{rid}/archive")
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import roasters as roasters_service

    with SessionLocal() as db:
        row = roasters_service.get_roaster(db, roaster_id=rid)
        assert row is not None
        assert row.archived is True


# --------------------------------------------------------------------------- #
# GET /roasters/list — autocomplete                                           #
# --------------------------------------------------------------------------- #


def test_autocomplete_short_query_returns_empty(authed_client: Any, clean_roasters: None) -> None:
    """len(q) < 2 → empty body (debounce-cheap)."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/roasters/list?roaster_query=a")
    assert resp.status_code == 200
    assert resp.text.strip() == ""


def test_autocomplete_returns_matches(authed_client: Any, clean_roasters: None) -> None:
    """Prefix match returns roasters whose name starts with q, excludes others."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_roaster(name="Onyx")
    _seed_roaster(name="Heart")
    resp = authed_client.get("/roasters/list?roaster_query=on")
    assert resp.status_code == 200
    body = resp.text
    assert '<li role="option"' in body
    # Match-highlight wraps the matched prefix in <strong> ("<strong>On</strong>yx"),
    # so "Onyx" as a contiguous string is split. Probe for the unwrapped
    # suffix instead — defense against the highlight code path masking a
    # genuine no-result regression.
    assert ">On</strong>yx" in body
    # Heart shares no prefix with "on" and must not appear at all.
    assert "Heart" not in body


def test_autocomplete_appends_create_new_when_no_exact_match(
    authed_client: Any, clean_roasters: None
) -> None:
    """No exact match for q → "+ Create new roaster" affordance appears."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/roasters/list?roaster_query=newname")
    assert resp.status_code == 200
    assert '+ Create new roaster: "newname"' in resp.text


def test_autocomplete_no_create_new_when_exact_match(
    authed_client: Any, clean_roasters: None
) -> None:
    """Exact name match (case-insensitive) → no "+ Create new" affordance."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_roaster(name="Onyx")
    resp = authed_client.get("/roasters/list?roaster_query=Onyx")
    assert resp.status_code == 200
    assert "+ Create new roaster:" not in resp.text


# --------------------------------------------------------------------------- #
# CSRF                                                                        #
# --------------------------------------------------------------------------- #


def test_csrf_missing_returns_403(csrf_client: Any, clean_roasters: None) -> None:
    """POST /roasters with mismatched CSRF → 403 from CSRFMiddleware."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = csrf_client.post("/roasters", data={"name": "X"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Service-layer probe (kept here to round out plan 04-04 coverage)            #
# --------------------------------------------------------------------------- #


def test_search_by_prefix_case_insensitive(clean_roasters: None) -> None:
    """CITEXT-driven ilike is case-insensitive natively (no func.lower)."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_roaster(name="Onyx")

    from app.db import SessionLocal
    from app.services import roasters as roasters_service

    with SessionLocal() as db:
        rows = roasters_service.search_by_prefix(db, query="on")
    names = [r.name for r in rows]
    assert "Onyx" in names
