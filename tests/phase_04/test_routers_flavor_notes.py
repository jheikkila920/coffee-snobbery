"""Real router tests for plan 04-05 (replaces the Wave-0 stub).

Cases per 04-VALIDATION.md row 04-05-NN. Mirrors the structure of
``tests/phase_04/test_routers_roasters.py``.

Uses:

* ``authed_client`` — session cookie preloaded; we re-arm the CSRF
  token per-test via ``_prime_csrf`` (the conftest fixture's literal
  placeholder fails starlette-csrf's signed-token check).
* ``csrf_client`` — same session but the cookie/header are
  intentionally mismatched (negative-CSRF probe).
* ``clean_flavor_notes`` — local fixture: wipes ``flavor_notes`` (and
  the dependent ``bags`` + ``coffees`` so the ``advertised_flavor_note_ids``
  references don't dangle) before AND after each test.

Most tests require Postgres + the p4_shared_catalog migration. Uses the
same ``_require_*`` helpers as ``test_routers_roasters.py``.
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
            row = conn.execute(text("SELECT to_regclass('public.flavor_notes')")).scalar()
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
def clean_flavor_notes() -> Iterator[None]:
    """Wipe the flavor_notes chain before AND after each router test.

    Reset order respects FKs: bags → coffees → flavor_notes. Coffees
    carry the ``advertised_flavor_note_ids`` array; clearing them first
    is harmless (no FK on the array elements) but keeps subsequent
    tests' state predictable.
    """
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM bags"))
            conn.execute(text("DELETE FROM coffees"))
            conn.execute(text("DELETE FROM flavor_notes"))

    _reset()
    yield
    _reset()


def _seed_flavor_note(**kwargs: Any) -> int:
    """Insert a flavor note via the service and return its id."""
    from app.db import SessionLocal
    from app.services import flavor_notes as flavor_notes_service

    defaults = {
        "name": kwargs.pop("name", "Bergamot"),
        "category": kwargs.pop("category", "fruit"),
        "by_user_id": kwargs.pop("by_user_id", 0),
    }
    with SessionLocal() as db:
        flavor_note = flavor_notes_service.create_flavor_note(db, **defaults)
        return flavor_note.id


# --------------------------------------------------------------------------- #
# GET /flavor-notes — list page                                               #
# --------------------------------------------------------------------------- #


def test_list_flavor_notes_renders(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """Authenticated GET /flavor-notes → 200 + page HTML with h1."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/flavor-notes")
    assert resp.status_code == 200
    body = resp.text
    assert "<h1" in body
    assert "Flavor notes" in body


# --------------------------------------------------------------------------- #
# POST /flavor-notes — create                                                 #
# --------------------------------------------------------------------------- #


def test_create_valid_returns_row(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """Valid form data → 200 + row fragment (id="flavor-note-N")."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/flavor-notes",
        data={"name": "Bergamot", "category": "fruit"},
    )
    assert resp.status_code == 200, resp.text
    # Row fragment carries the per-row id.
    assert 'id="flavor-note-' in resp.text
    # Category pill text.
    assert "fruit" in resp.text
    # OOB form-clear on the create path.
    assert "flavor-note-form-mount" in resp.text


def test_create_rejects_unknown_category_with_form_re_render(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """Invalid category → 200 (NOT 422) + form re-render with error styling."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/flavor-notes",
        data={"name": "Bergamot", "category": "metallic"},
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


def test_create_with_as_modal_emits_hx_trigger(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """as_modal=true → empty body + HX-Trigger flavor-note-created header (D-15)."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/flavor-notes",
        data={"name": "Jasmine", "category": "floral", "as_modal": "true"},
    )
    assert resp.status_code == 200, resp.text
    assert "HX-Trigger" in resp.headers
    payload = json.loads(resp.headers["HX-Trigger"])
    assert "flavor-note-created" in payload
    inner = payload["flavor-note-created"]
    assert inner["name"] == "Jasmine"
    assert isinstance(inner["flavor_note_id"], int)
    assert inner["flavor_note_id"] > 0


# --------------------------------------------------------------------------- #
# GET /flavor-notes/{id}/edit — pre-population                                #
# --------------------------------------------------------------------------- #


def test_edit_pre_populates_category(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """GET /edit → form fragment with the right <option> pre-selected."""
    _require_postgres()
    _require_p4_migration_applied()
    fnid = _seed_flavor_note(name="Cocoa", category="chocolate")
    resp = authed_client.get(f"/flavor-notes/{fnid}/edit")
    assert resp.status_code == 200
    body = resp.text
    # The 9-value <select> must render all options + select the right one.
    assert 'value="chocolate" selected' in body
    # And the name input is pre-populated.
    assert 'value="Cocoa"' in body


# --------------------------------------------------------------------------- #
# POST /flavor-notes/{id}/archive                                             #
# --------------------------------------------------------------------------- #


def test_archive_marks_archived(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """POST /archive → DB row.archived=True."""
    _require_postgres()
    _require_p4_migration_applied()
    fnid = _seed_flavor_note(name="Almond", category="nutty")
    _prime_csrf(authed_client)
    resp = authed_client.post(f"/flavor-notes/{fnid}/archive")
    assert resp.status_code == 200, resp.text

    from app.db import SessionLocal
    from app.services import flavor_notes as flavor_notes_service

    with SessionLocal() as db:
        row = flavor_notes_service.get_flavor_note(db, flavor_note_id=fnid)
        assert row is not None
        assert row.archived is True


# --------------------------------------------------------------------------- #
# GET /flavor-notes/datalist — autocomplete                                   #
# --------------------------------------------------------------------------- #


def test_datalist_short_query_empty(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """len(q) < 2 → empty body (debounce-cheap)."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/flavor-notes/datalist?q=a")
    assert resp.status_code == 200
    assert resp.text.strip() == ""


def test_datalist_returns_matches(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """Prefix match returns flavor notes whose name starts with q."""
    _require_postgres()
    _require_p4_migration_applied()
    _seed_flavor_note(name="Bergamot", category="fruit")
    _seed_flavor_note(name="Jasmine", category="floral")
    resp = authed_client.get("/flavor-notes/datalist?q=ber")
    assert resp.status_code == 200
    body = resp.text
    assert '<li role="option"' in body
    # Match-highlight wraps the prefix with <strong>, so probe the unwrapped
    # suffix instead of the contiguous name.
    assert ">Ber</strong>gamot" in body
    # Jasmine shares no prefix with "ber" → must not appear.
    assert "Jasmine" not in body


def test_datalist_create_new_when_no_match(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """No exact match for q → "+ Create new flavor note" affordance appears."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/flavor-notes/datalist?q=watermelon")
    assert resp.status_code == 200
    assert '+ Create new flavor note: "watermelon"' in resp.text


# --------------------------------------------------------------------------- #
# T-04-MASS                                                                   #
# --------------------------------------------------------------------------- #


def test_extra_field_rejected(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """Extra form field → 200 + form re-render (T-04-MASS via extra='forbid')."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/flavor-notes",
        data={
            "name": "Bergamot",
            "category": "fruit",
            "is_admin": "true",  # not in FlavorNoteCreate — must be rejected.
        },
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


# --------------------------------------------------------------------------- #
# T-04-CSRF                                                                   #
# --------------------------------------------------------------------------- #


def test_csrf_missing_returns_403(
    csrf_client: Any, clean_flavor_notes: None
) -> None:
    """POST /flavor-notes with mismatched CSRF → 403 from CSRFMiddleware."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = csrf_client.post(
        "/flavor-notes", data={"name": "X", "category": "other"}
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# CITEXT uniqueness                                                           #
# --------------------------------------------------------------------------- #


def test_name_unique_citext_returns_validation_error(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """CITEXT unique on name: 'Bergamot' then 'bergamot' must collide.

    The DB raises IntegrityError. The service does not currently catch
    this (no validation_error mapping exists yet — Phase 4-11 may add a
    pre-insert dedupe). At Phase 4-05 the expected behavior is a 500-
    range error from the unhandled IntegrityError, OR — if the test
    framework rolls back cleanly — a successful retry. This test asserts
    the contract that the second insert does NOT silently succeed (i.e.
    we do not end up with two near-duplicate rows).
    """
    _require_postgres()
    _require_p4_migration_applied()
    _seed_flavor_note(name="Bergamot", category="fruit")
    _prime_csrf(authed_client)

    # The second insert must NOT succeed silently — either it raises
    # (TestClient surfaces as 500) or the router catches and re-renders.
    # The post-state assertion is the authoritative check.
    try:
        resp = authed_client.post(
            "/flavor-notes",
            data={"name": "bergamot", "category": "floral"},
        )
        # If it returned a 2xx, the second row must NOT have been inserted
        # (collision must have been rejected somewhere).
        assert resp.status_code in (200, 422, 500), resp.status_code
    except Exception:  # noqa: BLE001 — IntegrityError can bubble in test mode
        pass

    from app.db import SessionLocal
    from app.services import flavor_notes as flavor_notes_service

    with SessionLocal() as db:
        rows = flavor_notes_service.list_flavor_notes(db, include_archived=False)
    # Exactly one Bergamot — CITEXT collision was rejected somewhere.
    bergamot_rows = [
        fn for fn, _ in rows if fn.name.lower() == "bergamot"
    ]
    assert len(bergamot_rows) == 1


# --------------------------------------------------------------------------- #
# Service-layer probe — usage count via array contains                        #
# --------------------------------------------------------------------------- #


def test_list_flavor_notes_usage_count_from_advertised_array(
    authed_client: Any, clean_flavor_notes: None
) -> None:
    """list_flavor_notes counts coffees that reference the flavor note in their
    advertised_flavor_note_ids array (UI-SPEC §"Flavor notes").
    """
    _require_postgres()
    _require_p4_migration_applied()
    fn1 = _seed_flavor_note(name="Bergamot", category="fruit")
    fn2 = _seed_flavor_note(name="Jasmine", category="floral")

    # Seed two coffees: one references both, one references only bergamot.
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO coffees (name, advertised_flavor_note_ids) "
                "VALUES (:n, :ids)"
            ),
            {"n": "Geometry", "ids": [fn1, fn2]},
        )
        conn.execute(
            text(
                "INSERT INTO coffees (name, advertised_flavor_note_ids) "
                "VALUES (:n, :ids)"
            ),
            {"n": "Kabingo", "ids": [fn1]},
        )

    from app.db import SessionLocal
    from app.services import flavor_notes as flavor_notes_service

    with SessionLocal() as db:
        rows = flavor_notes_service.list_flavor_notes(db, include_archived=False)
    counts = {fn.name: count for fn, count in rows}
    assert counts.get("Bergamot") == 2
    assert counts.get("Jasmine") == 1
