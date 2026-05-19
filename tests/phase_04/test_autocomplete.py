"""Integration coverage for plan 04-11 (autocomplete + mini-modal).

Replaces the Wave-0 ``pytest.skip`` stub. Pytest cannot drive the actual
JS event-loop (that's Phase 12 Playwright), so this file focuses on the
SERVER-SIDE contract that the Alpine components consume:

1. The coffee form's roaster + flavor-note autocomplete inputs carry the
   locked D-13 / HX-4 / D-14 attribute set.
2. The autocomplete-list fragment's "+ Create new" affordance targets
   ``#modal-mount`` AND includes ``prefill=<query>``.
3. The modal POST endpoints emit ``HX-Trigger`` with the exact payload
   shape autocomplete.js relies on.
4. The Alpine component .js files are served at the URLs base.html loads
   them from, and contain the documented ``Alpine.data`` registrations.
5. The base.html load order ships all three live components + the global
   ``#modal-mount`` div.
6. CSRF still enforced on every state-changing modal POST.
7. Autocomplete response bodies never contain ``hx-swap-oob`` (D-14
   no-OOB-on-datalist contract).

Reuses the test substrate from ``test_routers_roasters.py`` /
``test_routers_coffees.py`` (``authed_client``, ``_prime_csrf``,
``_require_*``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Skips (parallel shape to test_routers_roasters.py + test_routers_coffees.py)
# --------------------------------------------------------------------------- #


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

    Same shape as the helpers in ``test_routers_roasters.py`` and
    ``test_routers_coffees.py``. The conftest ``authed_client`` fixture
    preloads a literal placeholder that fails starlette-csrf's signed-token
    check; we drop it and let the middleware mint a real one on GET /.
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
    """Wipe the catalog chain before AND after each test.

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


# --------------------------------------------------------------------------- #
# 1. Autocomplete attribute contract on the coffee form                       #
# --------------------------------------------------------------------------- #


def test_coffee_form_has_roaster_autocomplete_d13_attrs(
    authed_client: Any, clean_catalog: None
) -> None:
    """Roaster input renders the locked D-13 debounce + HX-4 sync attrs."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees/new")
    assert resp.status_code == 200
    body = resp.text
    # The locked clauses live INSIDE a comma-separated hx-trigger value —
    # assert by substring rather than full-string equality so the test
    # survives the D-14 substrate extension shipped in this plan.
    assert "input changed delay:350ms[target.value.length >= 2]" in body
    assert 'hx-sync="this:replace"' in body
    # Roaster autocomplete shell — hidden FK input + dropdown mount.
    assert 'name="roaster_id"' in body
    assert 'id="roaster-dropdown"' in body


def test_coffee_form_has_flavor_note_autocomplete_d13_attrs(
    authed_client: Any, clean_catalog: None
) -> None:
    """Flavor-note input renders the same D-13 debounce + HX-4 sync attrs."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees/new")
    body = resp.text
    # Two inputs (roaster_query + flavor_note_query) each carry the
    # combined hx-trigger string; substring assertion catches both.
    assert body.count("input changed delay:350ms[target.value.length >= 2]") >= 2
    assert 'name="flavor_note_query"' in body
    assert 'id="flavor-note-dropdown"' in body


def test_coffee_form_has_focus_once_from_closest_field(
    authed_client: Any, clean_catalog: None
) -> None:
    """Both autocompletes carry the D-14 focus-once re-fetch substrate.

    The `field` class on the wrapper is what `focus once from:closest .field`
    targets — assert both the class marker and the trigger clause.
    """
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/coffees/new")
    body = resp.text
    # Trigger clause appears once per autocomplete input (roaster + flavor-note).
    assert body.count("focus once from:closest .field") >= 2
    # And the `field` class marker must appear on at least the two
    # wrapper divs (other unrelated occurrences are tolerated).
    assert 'class="field' in body or "class='field" in body


# --------------------------------------------------------------------------- #
# 2. Autocomplete-list fragment + "+ Create new" affordance                   #
# --------------------------------------------------------------------------- #


def test_autocomplete_list_create_new_targets_modal_mount(
    authed_client: Any, clean_catalog: None
) -> None:
    """The autocomplete-list fragment's "+ Create new" <li> targets #modal-mount."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/roasters/list?roaster_query=neverseenname")
    assert resp.status_code == 200
    body = resp.text
    assert 'hx-target="#modal-mount"' in body
    assert "+ Create new roaster:" in body


def test_autocomplete_list_create_new_passes_prefill(
    authed_client: Any, clean_catalog: None
) -> None:
    """The "+ Create new" hx-get URL includes prefill=<query> so the modal pre-populates."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/roasters/list?roaster_query=spectremill")
    body = resp.text
    # The fragment's hx-get URL must include prefill=spectremill so the
    # modal opens with the Name input pre-populated.
    assert "prefill=spectremill" in body


def test_autocomplete_list_flavor_note_create_new_passes_prefill(
    authed_client: Any, clean_catalog: None
) -> None:
    """Parallel check for the flavor-notes datalist."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/flavor-notes/datalist?flavor_note_query=ozonefruit")
    body = resp.text
    assert 'hx-target="#modal-mount"' in body
    assert "+ Create new flavor note:" in body
    assert "prefill=ozonefruit" in body


# --------------------------------------------------------------------------- #
# 3. Modal POST → HX-Trigger payload contract (D-15 / D-16)                   #
# --------------------------------------------------------------------------- #


def test_roaster_modal_post_emits_hx_trigger_with_correct_payload_shape(
    authed_client: Any, clean_catalog: None
) -> None:
    """POST /roasters?as_modal=true → HX-Trigger: roaster-created {roaster_id, name}.

    Pin the exact event name + payload key names so autocomplete.js can
    rely on them. The Alpine listener decodes `evt.detail.roaster_id` and
    `evt.detail.name` literally.
    """
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/roasters",
        data={"name": "Onyx Modal Probe", "as_modal": "true"},
    )
    assert resp.status_code == 200, resp.text
    trigger = resp.headers.get("HX-Trigger")
    assert trigger, f"HX-Trigger header missing; got headers: {dict(resp.headers)}"
    payload = json.loads(trigger)
    assert "roaster-created" in payload
    detail = payload["roaster-created"]
    assert "roaster_id" in detail and isinstance(detail["roaster_id"], int)
    assert "name" in detail and detail["name"] == "Onyx Modal Probe"


def test_flavor_note_modal_post_emits_hx_trigger_with_correct_payload_shape(
    authed_client: Any, clean_catalog: None
) -> None:
    """POST /flavor-notes?as_modal=true → HX-Trigger: flavor-note-created {flavor_note_id, name}."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/flavor-notes",
        data={"name": "Yuzu Probe", "category": "fruit", "as_modal": "true"},
    )
    assert resp.status_code == 200, resp.text
    trigger = resp.headers.get("HX-Trigger")
    assert trigger, "HX-Trigger header missing"
    payload = json.loads(trigger)
    assert "flavor-note-created" in payload
    detail = payload["flavor-note-created"]
    assert "flavor_note_id" in detail and isinstance(detail["flavor_note_id"], int)
    assert "name" in detail and detail["name"] == "Yuzu Probe"


def test_roaster_modal_get_returns_modal_fragment_with_alpine_wiring(
    authed_client: Any, clean_catalog: None
) -> None:
    """GET /roasters/new?as_modal=true → modal body fragment wired with x-data='miniModal'."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/roasters/new?as_modal=true&prefill=Onyx")
    assert resp.status_code == 200
    body = resp.text
    assert 'x-data="miniModal"' in body
    assert 'name="as_modal"' in body
    assert 'name="X-CSRF-Token"' in body
    # prefill pre-populates the Name input.
    assert 'value="Onyx"' in body


def test_flavor_note_modal_get_returns_modal_fragment_with_alpine_wiring(
    authed_client: Any, clean_catalog: None
) -> None:
    """Parallel check for the flavor-note modal."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/flavor-notes/new?as_modal=true&prefill=bergamot")
    assert resp.status_code == 200
    body = resp.text
    assert 'x-data="miniModal"' in body
    assert 'name="as_modal"' in body
    assert 'name="X-CSRF-Token"' in body
    assert 'value="bergamot"' in body


# --------------------------------------------------------------------------- #
# 4. Component .js files served + registration smoke                          #
# --------------------------------------------------------------------------- #


def test_mini_modal_js_served_with_alpine_data_registration(
    authed_client: Any,
) -> None:
    """GET /static/js/alpine-components/mini-modal.js → 200 + Alpine.data('miniModal'."""
    resp = authed_client.get("/static/js/alpine-components/mini-modal.js")
    assert resp.status_code == 200
    assert "Alpine.data('miniModal'" in resp.text


def test_autocomplete_js_served_with_alpine_data_registrations(
    authed_client: Any,
) -> None:
    """GET /static/js/alpine-components/autocomplete.js → 200 + two Alpine.data registrations.

    autocomplete.js ships TWO factories: 'autocomplete' (single-value
    picker) and 'flavorNoteChips' (multi-value chip widget).
    """
    resp = authed_client.get("/static/js/alpine-components/autocomplete.js")
    assert resp.status_code == 200
    body = resp.text
    assert "Alpine.data('autocomplete'" in body
    assert "Alpine.data('flavorNoteChips'" in body


def test_base_html_loads_all_three_components_and_modal_mount(
    authed_client: Any,
) -> None:
    """A page extending base.html loads all three Alpine components + #modal-mount.

    Hits /login (the simplest public page that extends base.html). The
    check is structural — the three component <script> tags are all
    present and the global modal mount div lives inside </body>.
    """
    # /login is unauthenticated — drop the session cookie to avoid the
    # auto-redirect to / on an authed visit.
    authed_client.cookies.delete("session_id")
    resp = authed_client.get("/login")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "/static/js/alpine-components/mini-modal.js" in body
    assert "/static/js/alpine-components/autocomplete.js" in body
    assert "/static/js/alpine-components/recipe-step-builder.js" in body
    assert 'id="modal-mount"' in body


# --------------------------------------------------------------------------- #
# 5. CSRF still enforced on modal POSTs                                       #
# --------------------------------------------------------------------------- #


def test_roaster_modal_post_csrf_missing_returns_403(csrf_client: Any, clean_catalog: None) -> None:
    """T-04-CSRF — POST /roasters?as_modal=true with mismatched CSRF → 403."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = csrf_client.post(
        "/roasters",
        data={"name": "ShouldNotPersist", "as_modal": "true"},
    )
    assert resp.status_code == 403


def test_flavor_note_modal_post_csrf_missing_returns_403(
    csrf_client: Any, clean_catalog: None
) -> None:
    """T-04-CSRF — POST /flavor-notes?as_modal=true with mismatched CSRF → 403."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = csrf_client.post(
        "/flavor-notes",
        data={"name": "ShouldNotPersist", "category": "fruit", "as_modal": "true"},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# 6. No HX-3 OOB anti-pattern in autocomplete responses                       #
# --------------------------------------------------------------------------- #


def test_roaster_autocomplete_response_has_no_hx_swap_oob(
    authed_client: Any, clean_catalog: None
) -> None:
    """D-14 contract: NO `hx-swap-oob` on the autocomplete-list fragment.

    Plan-04-11 documents HX-3 race avoidance via `focus once` re-fetch
    on the input element instead of OOB swapping. Lock the no-OOB
    contract here so a future refactor that re-introduces it trips the
    test immediately.
    """
    _require_postgres()
    _require_p4_migration_applied()
    _seed_roaster(name="Onyx Roasters")
    resp = authed_client.get("/roasters/list?roaster_query=onyx")
    assert resp.status_code == 200
    assert "hx-swap-oob" not in resp.text


def test_flavor_note_autocomplete_response_has_no_hx_swap_oob(
    authed_client: Any, clean_catalog: None
) -> None:
    """Same contract for the flavor-notes datalist."""
    _require_postgres()
    _require_p4_migration_applied()
    resp = authed_client.get("/flavor-notes/datalist?flavor_note_query=ber")
    assert resp.status_code == 200
    assert "hx-swap-oob" not in resp.text


# --------------------------------------------------------------------------- #
# 7. Per-item commit handler — entity-aware (select vs addChip)               #
# --------------------------------------------------------------------------- #


def test_autocomplete_list_items_carry_alpine_click_handler_for_roaster(
    authed_client: Any, clean_catalog: None
) -> None:
    """Each <li role="option"> commits the choice via the CSP-safe handler.

    The shared autocomplete_list.html binds a uniform
    ``x-on:click="commitItem($el)"`` and carries the id+name on
    ``data-item-id`` / ``data-item-name`` attributes (the @alpinejs/csp
    build cannot parse inline string-literal method args, so the id+name
    travel via data-* attributes the component reads off ``$el``).
    """
    _require_postgres()
    _require_p4_migration_applied()
    rid = _seed_roaster(name="Onyx Roasters")
    resp = authed_client.get("/roasters/list?roaster_query=onyx")
    body = resp.text
    assert 'x-on:click="commitItem($el)"' in body
    assert f'data-item-id="{rid}"' in body


def test_autocomplete_list_items_carry_alpine_click_handler_for_flavor_note(
    authed_client: Any, clean_catalog: None
) -> None:
    """Flavor-note datalist items commit via the same CSP-safe handler.

    Plan 04-11's chip widget (Alpine.data('flavorNoteChips')) and the
    single-value picker share the uniform ``commitItem($el)`` handler;
    the component variant decides select-vs-addChip. The dropdown markup
    carries the id+name on data-* attributes (CSP-safe — no inline
    string-literal method args).
    """
    _require_postgres()
    _require_p4_migration_applied()
    from app.db import SessionLocal
    from app.services import flavor_notes as flavor_notes_service

    with SessionLocal() as db:
        fn = flavor_notes_service.create_flavor_note(
            db, name="Bergamot", category="fruit", by_user_id=0
        )
        fn_id = fn.id
    resp = authed_client.get("/flavor-notes/datalist?flavor_note_query=ber")
    body = resp.text
    assert 'x-on:click="commitItem($el)"' in body
    assert f'data-item-id="{fn_id}"' in body
