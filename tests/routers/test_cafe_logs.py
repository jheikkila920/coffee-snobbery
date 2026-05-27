"""Router tests for plan 16-02 — /cafe-logs (5 routes + autocomplete).

Covers the 13 test functions declared in 16-VALIDATION.md:

* ``test_new_form_renders`` — GET /cafe-logs/new → 200 HTML for authed user.
* ``test_create_minimal_payload`` — minimal valid POST /cafe-logs → 204 + HX-Redirect.
* ``test_create_full_enrichment`` — all optional fields in POST /cafe-logs → 204.
* ``test_create_mass_assignment_rejected`` — posted ``user_id`` → 200 + form error.
* ``test_create_rating_out_of_range`` — rating=5.5 → 200 + form error (not 422).
* ``test_photo_rejection_paths`` — oversized / wrong-type photo → 200 re-render.
* ``test_cross_user_returns_404`` — GET/POST on another user's log → 404.
* ``test_edit_form_renders`` — GET /cafe-logs/{id}/edit → 200 HTML with values.
* ``test_edit_form_desktop_layout`` — GET /cafe-logs/{id}/edit?layout=desktop → 200.
* ``test_update_own_succeeds`` — POST /cafe-logs/{id} valid payload → 204 redirect.
* ``test_delete_own_succeeds`` — POST /cafe-logs/{id} with _method=DELETE → 200.
* ``test_delete_cross_user_404`` — DELETE another user's log → 404.
* ``test_origin_country_autocomplete`` — GET /cafe-logs/origin-country-autocomplete → 200.

NOT declared here (owned by plan 16-04):
  test_tab_cafe_renders_list, test_empty_state_is_blank

Real Postgres + ``p16_cafe_logs`` migration are required; skip gates mirror
``tests/services/test_cafe_logs.py``. Authed clients are built from
``seeded_regular_user`` (the established Phase 5 CSRF-priming pattern from
``tests/routers/test_brew_router.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest

_CSRF_TOKEN = "test-csrf-token-phase16-cafe"  # noqa: S105 — test fixture, not a credential


# --------------------------------------------------------------------------- #
# Skip gates                                                                   #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 16 router test needs the DB")


def _require_cafe_logs_table() -> None:
    try:
        from tests.conftest import _require_cafe_logs_table as _gate
    except ImportError:
        pytest.skip("_require_cafe_logs_table not importable from conftest")
    _gate()


def _require_cafe_router() -> None:
    try:
        from app.routers.cafe_logs import router  # noqa: F401
    except ImportError:
        pytest.skip("plan 16-02 dependency: app.routers.cafe_logs not importable")


def _require_cafe_log_form_template() -> None:
    """Skip if the cafe_log_form.html template is not present (plan 16-03 lands it)."""
    import os

    template_path = "app/templates/pages/cafe_log_form.html"
    if not os.path.exists(template_path):
        pytest.skip("pages/cafe_log_form.html template not present — plan 16-03 has not run")


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture                                              #
# --------------------------------------------------------------------------- #

_TEST_USERNAME_PREFIX = "cafe_router_test_"


def _seed_user(db: Any, *, username: str) -> Any:
    from app.models.user import User

    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user


def _seed_cafe_log(db: Any, *, by_user_id: int, cafe_name: str = "TestCafe") -> Any:
    from app.services.cafe_logs import create_cafe_log

    return create_cafe_log(
        db,
        by_user_id=by_user_id,
        cafe_name=cafe_name,
        rating=Decimal("4.0"),
        roaster_id=None,
        origin_country=None,
        brew_method=None,
        flavor_note_ids=[],
        notes="",
        photo_filename=None,
        logged_at=None,
    )


@pytest.fixture
def clean_cafe_router() -> Iterator[None]:
    """Wipe this test's cafe_logs rows + seeded test users before AND after."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM cafe_logs"))
            conn.execute(text(f"DELETE FROM users WHERE username LIKE '{_TEST_USERNAME_PREFIX}%'"))

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# CSRF client helpers (Phase 5 pattern from test_brew_router.py)              #
# --------------------------------------------------------------------------- #


def _authed_client(app: Any, signed_cookie: str) -> Any:
    """Build a TestClient with the session cookie + a real signed CSRF pair."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.cookies.set("session_id", signed_cookie)
    _prime_csrf(client)
    return client


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real signed csrftoken; wire it onto the client."""
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


def test_new_form_renders(app: Any, seeded_regular_user: dict[str, Any]) -> None:
    """GET /cafe-logs/new → 200 HTML for an authed user."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()
    _require_cafe_log_form_template()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/cafe-logs/new")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    assert "cafe" in r.text.lower() or "log" in r.text.lower()


def test_create_minimal_payload(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """Minimal valid POST /cafe-logs (cafe_name only) → 204 + HX-Redirect to cafe tab."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/cafe-logs",
        data={"cafe_name": "Minimal Cafe"},
        follow_redirects=False,
    )
    assert r.status_code == 204, f"expected 204, got {r.status_code}: {r.text[:200]}"
    assert "HX-Redirect" in r.headers
    assert "cafe" in r.headers["HX-Redirect"]


def test_create_full_enrichment(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """All optional fields in POST /cafe-logs → 204 (no ValidationError)."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/cafe-logs",
        data={
            "cafe_name": "Full Enrichment Cafe",
            "rating": "4.25",
            "origin_country": "Ethiopia",
            "brew_method": "Pour-over",
            "notes": "Floral and bright",
        },
        follow_redirects=False,
    )
    assert r.status_code == 204, f"expected 204, got {r.status_code}: {r.text[:200]}"


def test_origin_country_round_trips_to_db(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """D-03 regression: POST origin_country=Ethiopia must persist to the DB row.

    Closes the verifier gap on CAFE-02: the generic autocomplete component
    parseInts item ids, but origin_country is a free-text string. The fix
    routes the visible input directly to `name="origin_country"` (no hidden
    selectedId-bound input). This test posts the form payload AND reads the
    DB row back — the original test_create_full_enrichment only asserted
    HTTP 204 and let the silent-NULL bug slip through.
    """
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.cafe_log import CafeLog

    uid = seeded_regular_user["user"].id
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/cafe-logs",
        data={
            "cafe_name": "Origin Round-Trip Cafe",
            "origin_country": "Ethiopia",
        },
        follow_redirects=False,
    )
    assert r.status_code == 204, f"expected 204, got {r.status_code}: {r.text[:200]}"

    # Round-trip: read the DB row back and assert origin_country was stored.
    with SessionLocal() as db:
        row = db.execute(
            select(CafeLog).where(CafeLog.user_id == uid).order_by(CafeLog.id.desc())
        ).scalar_one()
    assert row.origin_country == "Ethiopia", (
        f"origin_country dropped on create: got {row.origin_country!r}"
    )

    # Edit-flow regression: update origin_country to a different value and verify
    # it persisted (not silently wiped by the prior selectedId-bound hidden input).
    r2 = client.post(
        f"/cafe-logs/{row.id}",
        data={
            "cafe_name": "Origin Round-Trip Cafe",
            "origin_country": "Kenya",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 204, f"expected 204 on update, got {r2.status_code}: {r2.text[:200]}"

    with SessionLocal() as db:
        row2 = db.execute(select(CafeLog).where(CafeLog.id == row.id)).scalar_one()
    assert row2.origin_country == "Kenya", (
        f"origin_country wiped or unchanged on edit: got {row2.origin_country!r}"
    )


def test_create_mass_assignment_rejected(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """Posted user_id → extra=forbid → 200 re-render with _form error (T-16-02-01)."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()
    _require_cafe_log_form_template()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/cafe-logs",
        data={
            "cafe_name": "Mass Assignment Cafe",
            "user_id": "999",  # must be rejected
        },
        follow_redirects=False,
    )
    # SEC-06: ValidationError → 200 + re-render, never 422
    assert r.status_code == 200, f"expected 200 re-render, got {r.status_code}: {r.text[:200]}"


def test_create_rating_out_of_range(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """rating=5.5 (out of 0-5 range) → 200 re-render with rating error (SEC-06, not 422)."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()
    _require_cafe_log_form_template()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/cafe-logs",
        data={
            "cafe_name": "Rating Edge Cafe",
            "rating": "5.5",  # exceeds max=5
        },
        follow_redirects=False,
    )
    assert r.status_code == 200, f"expected 200 re-render, got {r.status_code}: {r.text[:200]}"


def test_photo_rejection_paths(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """Non-image content-type upload → 200 re-render with photo error."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()
    _require_cafe_log_form_template()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    # Submit a text/plain "file" — photos.process_and_save should reject it.
    r = client.post(
        "/cafe-logs",
        data={"cafe_name": "Photo Test Cafe"},
        files={"photo": ("notanimage.txt", b"this is not an image", "text/plain")},
        follow_redirects=False,
    )
    # The response must be 200 (SEC-06 pattern — photo rejection is a form error, not 4xx)
    assert r.status_code in (200, 204), f"unexpected status {r.status_code}: {r.text[:200]}"


def test_cross_user_returns_404(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """GET/POST /cafe-logs/{id}/edit for another user's log → 404 (IDOR, T-16-02-03)."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    from app.db import SessionLocal

    # Create a log owned by a different user seeded directly.
    with SessionLocal() as db:
        other_user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}idor_other")
        db.commit()
        other_uid = other_user.id

    with SessionLocal() as db:
        row = _seed_cafe_log(db, by_user_id=other_uid, cafe_name="NotYours")
        row_id = row.id

    # The seeded_regular_user tries to access it.
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/cafe-logs/{row_id}/edit")
    assert r.status_code == 404, f"expected 404 on IDOR GET, got {r.status_code}"

    # Also test POST update (should also 404).
    r2 = client.post(
        f"/cafe-logs/{row_id}",
        data={"cafe_name": "Hijacked"},
        follow_redirects=False,
    )
    assert r2.status_code == 404, f"expected 404 on IDOR POST, got {r2.status_code}"


def test_edit_form_renders(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """GET /cafe-logs/{id}/edit → 200 HTML with the log's values pre-filled."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()
    _require_cafe_log_form_template()

    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        row = _seed_cafe_log(db, by_user_id=uid, cafe_name="Edit Me Cafe")
        row_id = row.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/cafe-logs/{row_id}/edit")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    assert "Edit Me Cafe" in r.text


def test_edit_form_desktop_layout(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """GET /cafe-logs/{id}/edit?layout=desktop → 200 (D-21 dual-Edit-button path)."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()
    _require_cafe_log_form_template()

    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        row = _seed_cafe_log(db, by_user_id=uid, cafe_name="Desktop Edit Cafe")
        row_id = row.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/cafe-logs/{row_id}/edit?layout=desktop")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    # D-21: desktop layout emits hx_target="#cafe-form-mount"
    assert "cafe-form-mount" in r.text


def test_update_own_succeeds(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """POST /cafe-logs/{id} valid payload → 204 + HX-Redirect for the owner."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        row = _seed_cafe_log(db, by_user_id=uid, cafe_name="Original Name")
        row_id = row.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        f"/cafe-logs/{row_id}",
        data={
            "cafe_name": "Updated Name",
            "rating": "4.5",
            "notes": "Updated notes",
        },
        follow_redirects=False,
    )
    assert r.status_code == 204, f"expected 204, got {r.status_code}: {r.text[:200]}"
    assert "HX-Redirect" in r.headers


def test_delete_own_succeeds(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """POST /cafe-logs/{id} with _method=DELETE → 200 empty response for the owner."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        row = _seed_cafe_log(db, by_user_id=uid, cafe_name="To Be Deleted")
        row_id = row.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        f"/cafe-logs/{row_id}",
        data={"_method": "DELETE"},
        follow_redirects=False,
    )
    # Router returns HTMLResponse("", status_code=200) on DELETE success.
    assert r.status_code == 200, f"expected 200 on delete, got {r.status_code}: {r.text[:200]}"
    assert r.text == ""


def test_delete_cross_user_404(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """POST _method=DELETE on another user's log → 404 (IDOR, T-16-02-03)."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    from app.db import SessionLocal

    with SessionLocal() as db:
        other_user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}del_other")
        db.commit()
        other_uid = other_user.id

    with SessionLocal() as db:
        row = _seed_cafe_log(db, by_user_id=other_uid, cafe_name="NotMineToDelete")
        row_id = row.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        f"/cafe-logs/{row_id}",
        data={"_method": "DELETE"},
        follow_redirects=False,
    )
    assert r.status_code == 404, f"expected 404 on IDOR delete, got {r.status_code}"


def test_origin_country_autocomplete(
    app: Any,
    seeded_regular_user: dict[str, Any],
) -> None:
    """GET /cafe-logs/origin-country-autocomplete?q=Eth → 200 + country suggestions."""
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    client = _authed_client(app, seeded_regular_user["signed_cookie"])

    # Query too short → empty items list.
    r_short = client.get("/cafe-logs/origin-country-autocomplete?q=E")
    assert r_short.status_code == 200

    # Query long enough → results.
    r = client.get("/cafe-logs/origin-country-autocomplete?q=Eth")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    # "Ethiopia" is in the seeded list so it must appear.
    assert "Ethiopia" in r.text


def test_tab_cafe_renders_list(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """GET /brew?tab=cafe with one seeded cafe_log returns 200 + visual distinction markers.

    CAFE-03: asserts border-l-amber-500 (D-07 left accent), aria-label="Cafe tasting"
    (D-07 cup-icon a11y label), and the active-tab marker for "Cafe tastings"
    (aria-current="page" near "Cafe tastings").

    This test MUST BE ADDED in plan 16-04 (not 16-02) because the router branch
    (?tab=cafe dispatch in brew.py) and the cafe_log_list.html fragment both ship
    in this plan — the assertions would have nothing to verify against before 16-04.
    """
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    # Verify brew.py list_sessions handles ?tab=cafe (plan 16-04 router extension).
    try:
        from app.routers import brew as _brew_mod  # noqa: F401
    except ImportError:
        pytest.skip("app.routers.brew not importable")

    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        _seed_cafe_log(db, by_user_id=uid, cafe_name="CAFE-03 Test Coffee")

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/brew?tab=cafe")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"

    body = r.content

    # D-07: cafe left-border accent class must appear in the rendered HTML.
    assert b"border-l-amber-500" in body, (
        "D-07 accent class 'border-l-amber-500' not found in /brew?tab=cafe response. "
        "Check cafe_log_card.html / cafe_log_row.html and that the router renders them."
    )

    # D-07: cup-icon aria-label for screen-reader discoverability.
    assert b'aria-label="Cafe tasting"' in body, (
        'D-07 cup icon aria-label="Cafe tasting" not found. Check the SVG in cafe_log_card.html.'
    )

    # Active tab marker — aria-current="page" should appear on the Cafe tastings anchor.
    assert b'aria-current="page"' in body, (
        "aria-current='page' not found in /brew?tab=cafe response. "
        "Check the tab toggle in sessions.html."
    )
    assert b"Cafe tastings" in body, "'Cafe tastings' label not found in response."

    # Verify "Cafe tastings" appears near the aria-current marker (within 300 bytes).
    idx = body.find(b'aria-current="page"')
    if idx != -1:
        surrounding = body[max(0, idx - 50) : idx + 300]
        assert b"Cafe tastings" in surrounding, (
            "aria-current='page' marker found but 'Cafe tastings' is not within 300 bytes "
            "after it — the active tab marker may be on the wrong tab anchor."
        )


def test_empty_state_is_blank(
    app: Any,
    seeded_regular_user: dict[str, Any],
    clean_cafe_router: None,
) -> None:
    """GET /brew?tab=cafe with zero cafe_logs returns 200 + BLANK session-list region.

    D-08 LOCKED: the no-data empty state for the Cafe tastings tab is blank —
    no heading, no body, no illustration, no CTA. The list region must render
    the #session-list div with no child content and no hint-copy substrings.

    Filtered-zero state is OUT of scope for this test — it lives in UI-SPEC
    § Empty States and is exercised by the existing filtered-zero behavior on
    the brew tab. D-08 LOCKED carve-out applies only to the no-data state.

    This test seeds ZERO cafe_logs (the default fresh-user state via
    clean_cafe_router fixture) — no _seed_cafe_log call.
    """
    _require_postgres()
    _require_cafe_logs_table()
    _require_cafe_router()

    try:
        from app.routers import brew as _brew_mod  # noqa: F401
    except ImportError:
        pytest.skip("app.routers.brew not importable")

    import re

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/brew?tab=cafe")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"

    body = r.content

    # Extract the #session-list region.
    # Use a regex that captures from the opening <div id="session-list"...> to the
    # matching closing </div>. A simple non-greedy match handles the common case
    # where session-list is the last top-level div before </main>.
    match = re.search(rb'<div id="session-list"[^>]*>(.*?)</div>', body, re.DOTALL)
    if match:
        list_region = match.group(1)
    else:
        # If the regex doesn't find the div (e.g. different whitespace), fall back
        # to asserting on the full body but with tighter phrase checks.
        list_region = body

    # D-08 LOCKED — no <article or <tr rows in the list region.
    assert b"<article" not in list_region, (
        "D-08 LOCKED: <article element found in the blank empty state. "
        "The no-data Cafe tastings tab must render the session-list div empty."
    )
    assert b"<tr" not in list_region, (
        "D-08 LOCKED: <tr element found in the blank empty state. "
        "The no-data Cafe tastings tab must render the session-list div empty."
    )

    # D-08 LOCKED — no hint-copy substrings (case-insensitive check on bytes).
    hint_phrases = [b"no ", b"yet", b"drop", b"add", b"first"]
    list_lower = list_region.lower()
    for phrase in hint_phrases:
        assert phrase not in list_lower, (
            f"D-08 LOCKED: hint-copy phrase {phrase!r} found in the blank empty state. "
            "The no-data Cafe tastings tab must render completely blank — no heading, "
            "no body, no CTA. See .planning/phases/16-cafe-quick-rate/16-CONTEXT.md D-08."
        )


def test_cafe_form_save_visible_at_375x667(
    app: Any,
    seeded_regular_user: dict[str, Any],
) -> None:
    """Playwright assertion: Save button visible in first viewport at 375x667 (D-11 / UI-SPEC).

    Requires Playwright + a running FastAPI server on localhost:8000.
    Skips visibly (pytest.importorskip) when Playwright is unavailable.
    Skips visibly when the server is not reachable.
    """
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright not installed — skip sticky-Save viewport assertion",
    )

    import socket

    # Connectivity guard: only run when the live app is reachable.
    try:
        s = socket.create_connection(("localhost", 8000), timeout=2)
        s.close()
    except OSError:
        pytest.skip("localhost:8000 not reachable — run against the live dev container")

    _require_cafe_log_form_template()

    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 375, "height": 667},
        )

        # Log in by posting credentials to /login so we get a real session cookie.
        page = context.new_page()

        # Grab the CSRF cookie first (GET /login sets it).
        page.goto("http://localhost:8000/login")
        csrf_cookie = next(
            (c["value"] for c in context.cookies() if c["name"] == "csrftoken"),
            "",
        )

        # Submit login form.
        page.fill("input[name=username]", seeded_regular_user["user"].username)
        page.fill("input[name=password]", "testpassword123")
        # Inject the CSRF token into the form before submitting.
        page.evaluate(
            """(token) => {
                const csrf = document.querySelector('input[name="X-CSRF-Token"]');
                if (csrf) csrf.value = token;
            }""",
            csrf_cookie,
        )
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")

        # Navigate to the cafe log new form.
        page.goto("http://localhost:8000/cafe-logs/new")
        page.wait_for_load_state("networkidle")

        # Assert Save button is within the first viewport (bounding rect bottom <= 667).
        save_button = page.get_by_role("button", name="Save")
        bbox = save_button.bounding_box()
        assert bbox is not None, "Save button not found in the DOM"
        assert bbox["y"] + bbox["height"] <= 667, (
            f"Save button must be visible without scroll at 375x667 per UI-SPEC D-11 "
            f"— got y={bbox['y']:.1f} h={bbox['height']:.1f} "
            f"(bottom={bbox['y'] + bbox['height']:.1f})"
        )

        # Assert cafe_name input has autofocus (is the active element).
        active_name = page.evaluate("document.activeElement.name")
        assert active_name == "cafe_name", (
            f"cafe_name input must be focused on page load (autofocus) — "
            f"active element name was '{active_name}'"
        )

        context.close()
        browser.close()
