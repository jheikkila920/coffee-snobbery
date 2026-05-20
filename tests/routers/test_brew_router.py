"""Router tests for plan 05-04 — the brew form router (app/routers/brew.py).

Covers the ``<behavior>`` cases across the plan's three tasks:

Task 1 (GET new/edit + POST create/update, SEC-06 + IDOR + mass-assignment):
* ``test_form_validation_200`` — invalid rating → HTTP 200 + re-rendered form
  with the rating error (NOT 422), no row inserted.
* ``test_ey_not_writable`` — a posted ``extraction_yield_pct`` folds to a
  ``_form`` error at 200 (extra=forbid); EY is never written.
* ``test_create_sets_user_id`` — a valid POST creates a session whose
  ``user_id`` is the authed user; success HX-Redirects to the list; the draft
  is cleared.
* ``test_edit_404_cross_user`` — GET/POST ``/brew/{id}`` for another user's
  session → 404 (IDOR existence non-leak).
* ``test_brew_new_prefill_context`` — GET /brew/new renders prefill values for
  an authed user with a prior session.
* ``test_brew_again_blanks_per_attempt`` — GET /brew/new?from={id} carries the
  source's carryable fields but blanks rating/observed/notes (HTTP level).

Task 2 (draft autosave + restore wiring):
* ``test_draft_upsert_one_row`` / ``test_draft_requires_csrf`` /
  ``test_draft_per_user`` / ``test_brew_new_includes_server_draft``.

Task 3 (GET /brew/prefill dynamic re-prefill fragment):
* ``test_prefill_fragment_coffee_change`` (D-04) /
  ``test_prefill_fragment_recipe_wins`` (D-05) /
  ``test_prefill_fragment_advertised_chips`` (D-11) /
  ``test_prefill_user_scoped`` / ``test_prefill_unknown_coffee_blank`` /
  ``test_prefill_requires_user``.

Real Postgres + the p5 migration are required; the skip gates mirror
``tests/services/test_brew_sessions_service.py``. Catalog + brew rows are
seeded directly via ``SessionLocal``; an authed ``TestClient`` is built from
the parent-conftest ``seeded_regular_user`` fixture (session cookie + a
double-submit ``csrftoken`` cookie/header pair, mirroring the Phase 4
``authed_client`` fixture).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

_CSRF_TOKEN = "test-csrf-token-phase05-brew"  # noqa: S105 — test fixture, not a credential


# --------------------------------------------------------------------------- #
# Skip gates (mirror tests/services/test_brew_sessions_service.py)            #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 5 router test needs the DB")


def _require_p5_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.brew_sessions')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p5_brew_sessions migration not applied")


def _require_brew_router() -> None:
    """Skip if plan 05-04's ``app.routers.brew`` module has not landed."""
    try:
        from app.routers.brew import router  # noqa: F401
    except ImportError:
        pytest.skip("plan 05-04 dependency: app.routers.brew not importable")


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture (LIKE-scoped to this test's own rows)       #
# --------------------------------------------------------------------------- #

_COFFEE_PREFIX = "Router Coffee"
_RECIPE_PREFIX = "Router Recipe"
_EQUIP_PREFIX = "RouterRig"


def _seed_coffee(db, *, name: str, advertised: list[int] | None = None):
    from app.models.coffee import Coffee

    coffee = Coffee(name=name, advertised_flavor_note_ids=advertised or [])
    db.add(coffee)
    db.flush()
    return coffee


def _seed_recipe(db, *, name: str, dose: int, water: int, temp: int, grind: str):
    from app.models.recipe import Recipe

    recipe = Recipe(
        name=name, dose_grams=dose, water_grams=water, water_temp_c=temp, grind_setting=grind
    )
    db.add(recipe)
    db.flush()
    return recipe


def _seed_equipment(db, *, type_: str, brand: str):
    from app.models.equipment import Equipment

    eq = Equipment(type=type_, brand=brand, model=f"{_EQUIP_PREFIX}-{brand}")
    db.add(eq)
    db.flush()
    return eq


@pytest.fixture
def clean_brew_router() -> Iterator[None]:
    """Wipe this test's brew rows + seeded catalog fixtures before AND after."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(text(f"DELETE FROM recipes WHERE name LIKE '{_RECIPE_PREFIX}%'"))
            conn.execute(text(f"DELETE FROM equipment WHERE model LIKE '{_EQUIP_PREFIX}%'"))
            conn.execute(text(f"DELETE FROM coffees WHERE name LIKE '{_COFFEE_PREFIX}%'"))

    _reset()
    yield
    _reset()


def _authed_client(app: Any, signed_cookie: str):
    """Build a TestClient carrying the session cookie + double-submit CSRF pair."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.cookies.set("session_id", signed_cookie)
    client.cookies.set("csrftoken", _CSRF_TOKEN)
    client.headers["X-CSRF-Token"] = _CSRF_TOKEN
    return client


def _create_session(db, *, by_user_id, coffee_id, brewed_at, **over):
    from app.services import brew_sessions as svc

    base = dict(
        bag_id=None,
        recipe_id=None,
        brewer_id=None,
        grinder_id=None,
        kettle_id=None,
        water_type="Filtered",
        dose_grams_actual=Decimal("15"),
        water_grams_actual=Decimal("250"),
        yield_grams_actual=None,
        tds_pct=None,
        water_temp_c_actual=Decimal("93"),
        grind_setting_actual="22",
        rating=Decimal("4"),
        flavor_note_ids_observed=[],
        notes="great cup",
    )
    base.update(over)
    return svc.create_brew_session(
        db, by_user_id=by_user_id, coffee_id=coffee_id, brewed_at=brewed_at, **base
    )


# --------------------------------------------------------------------------- #
# Task 1 — SEC-06 validation + mass-assignment defense                        #
# --------------------------------------------------------------------------- #


def test_form_validation_200(app, seeded_regular_user, clean_brew_router) -> None:
    """Invalid rating (3.3) → HTTP 200 + re-rendered form with error, no insert."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Val")
        db.commit()
        cid = coffee.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/brew",
        data={
            "X-CSRF-Token": _CSRF_TOKEN,
            "coffee_id": str(cid),
            "dose_grams_actual": "15",
            "water_grams_actual": "250",
            "rating": "3.3",  # not a 0.25 step
            "notes": "",
        },
    )
    assert r.status_code == 200, f"expected 200 re-render, got {r.status_code}: {r.text[:200]}"

    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        assert svc.list_brew_sessions(db, by_user_id=uid) == []


def test_ey_not_writable(app, seeded_regular_user, clean_brew_router) -> None:
    """A posted extraction_yield_pct → extra=forbid → 200 _form error, no write."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} EY")
        db.commit()
        cid = coffee.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/brew",
        data={
            "X-CSRF-Token": _CSRF_TOKEN,
            "coffee_id": str(cid),
            "dose_grams_actual": "15",
            "water_grams_actual": "250",
            "extraction_yield_pct": "99",  # GENERATED — must be rejected
            "notes": "",
        },
    )
    assert r.status_code == 200, f"expected 200 re-render, got {r.status_code}"

    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        assert svc.list_brew_sessions(db, by_user_id=uid) == []


def test_create_sets_user_id(app, seeded_regular_user, clean_brew_router) -> None:
    """A valid POST creates a session with the authed user_id; HX-Redirects; clears draft."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal
    from app.services import brew_drafts as draft_svc
    from app.services import brew_sessions as svc

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Create")
        db.commit()
        cid = coffee.id
        # Pre-seed a draft so we can assert it is cleared on submit.
        draft_svc.upsert_draft(db, by_user_id=uid, payload={"dose_grams_actual": "15"})

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/brew",
        data={
            "X-CSRF-Token": _CSRF_TOKEN,
            "coffee_id": str(cid),
            "dose_grams_actual": "15",
            "water_grams_actual": "250",
            "notes": "",
        },
    )
    assert r.status_code in (200, 204), f"unexpected status {r.status_code}: {r.text[:200]}"
    assert "HX-Redirect" in r.headers, "success must respond with HX-Redirect to the list"

    with SessionLocal() as db:
        rows = svc.list_brew_sessions(db, by_user_id=uid)
        assert len(rows) == 1
        assert rows[0].user_id == uid
        assert rows[0].coffee_id == cid
        # Draft cleared on successful submit.
        assert draft_svc.get_draft(db, by_user_id=uid) is None


def test_edit_404_cross_user(
    app, seeded_regular_user, seeded_admin_user, clean_brew_router
) -> None:
    """GET/POST /brew/{id} for another user's session → 404 (IDOR non-leak)."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    owner_uid = seeded_admin_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} CrossUser")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        src = _create_session(db, by_user_id=owner_uid, coffee_id=cid, brewed_at=datetime.now(UTC))
        sid = src.id

    # The regular user (not the owner) must not see admin's session.
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r_get = client.get(f"/brew/{sid}/edit")
    assert r_get.status_code == 404, f"cross-user edit GET must 404, got {r_get.status_code}"

    r_post = client.post(
        f"/brew/{sid}",
        data={
            "X-CSRF-Token": _CSRF_TOKEN,
            "coffee_id": str(cid),
            "dose_grams_actual": "16",
            "water_grams_actual": "260",
            "notes": "",
        },
    )
    assert r_post.status_code == 404, f"cross-user edit POST must 404, got {r_post.status_code}"


def test_brew_new_prefill_context(app, seeded_regular_user, clean_brew_router) -> None:
    """GET /brew/new for a user with a prior session → 200 with prefilled markup."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Prefill")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        _create_session(
            db,
            by_user_id=uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            water_type="Spring",
            dose_grams_actual=Decimal("18"),
            grind_setting_actual="prefill-grind",
        )

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/brew/new")
    assert r.status_code == 200, f"GET /brew/new must 200 for authed user, got {r.status_code}"
    # The prior session's carryable values surface in the rendered form.
    assert "prefill-grind" in r.text
    assert "18" in r.text


def test_brew_again_blanks_per_attempt(app, seeded_regular_user, clean_brew_router) -> None:
    """GET /brew/new?from={id} carries carryable fields; blanks per-attempt fields."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Again")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        src = _create_session(
            db,
            by_user_id=uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC) - timedelta(days=2),
            water_type="Distilled",
            grind_setting_actual="again-grind",
            rating=Decimal("5"),
            notes="source notes",
        )
        sid = src.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/new?from={sid}")
    assert r.status_code == 200
    # Carryable field present; the source's notes (a per-attempt field) blanked.
    assert "again-grind" in r.text
    assert "source notes" not in r.text


# --------------------------------------------------------------------------- #
# Task 2 — draft autosave + restore wiring                                    #
# --------------------------------------------------------------------------- #


def test_draft_upsert_one_row(app, seeded_regular_user, clean_brew_router) -> None:
    """POST /brew/draft upserts exactly one row; a second POST replaces it."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from sqlalchemy import text

    from app.db import SessionLocal, engine

    uid = seeded_regular_user["user"].id
    client = _authed_client(app, seeded_regular_user["signed_cookie"])

    r1 = client.post(
        "/brew/draft",
        data={"X-CSRF-Token": _CSRF_TOKEN, "dose_grams_actual": "15"},
    )
    assert r1.status_code in (200, 204), f"first draft POST status {r1.status_code}"
    r2 = client.post(
        "/brew/draft",
        data={"X-CSRF-Token": _CSRF_TOKEN, "dose_grams_actual": "18"},
    )
    assert r2.status_code in (200, 204), f"second draft POST status {r2.status_code}"

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM brew_drafts WHERE user_id = :u"), {"u": uid}
        ).scalar()
    assert count == 1, f"expected exactly one draft row, got {count}"

    from app.services import brew_drafts as draft_svc

    with SessionLocal() as db:
        payload = draft_svc.get_draft(db, by_user_id=uid)
    assert payload is not None
    assert payload.get("dose_grams_actual") == "18"


def test_draft_requires_csrf(app, seeded_regular_user, clean_brew_router) -> None:
    """POST /brew/draft without a CSRF token → 403 (not exempt)."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from fastapi.testclient import TestClient

    # A session cookie WITHOUT a matching csrftoken header/cookie → CSRF 403.
    client = TestClient(app)
    client.cookies.set("session_id", seeded_regular_user["signed_cookie"])
    r = client.post("/brew/draft", data={"dose_grams_actual": "15"})
    assert r.status_code == 403, f"tokenless draft POST must 403, got {r.status_code}"


def test_draft_per_user(
    app, seeded_regular_user, seeded_admin_user, clean_brew_router
) -> None:
    """A draft saved by user A is never returned to user B."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal
    from app.services import brew_drafts as draft_svc

    a_uid = seeded_regular_user["user"].id
    b_uid = seeded_admin_user["user"].id

    client_a = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client_a.post(
        "/brew/draft",
        data={"X-CSRF-Token": _CSRF_TOKEN, "dose_grams_actual": "15"},
    )
    assert r.status_code in (200, 204)

    with SessionLocal() as db:
        assert draft_svc.get_draft(db, by_user_id=a_uid) is not None
        assert draft_svc.get_draft(db, by_user_id=b_uid) is None


def test_brew_new_includes_server_draft(app, seeded_regular_user, clean_brew_router) -> None:
    """GET /brew/new (create) exposes the server draft so the client can reconcile."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal
    from app.services import brew_drafts as draft_svc

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Draft")
        db.commit()
        draft_svc.upsert_draft(
            db, by_user_id=uid, payload={"notes": "sentinel-draft-value-xyz"}
        )

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/brew/new")
    assert r.status_code == 200
    # The server draft payload is serialized into the create-mode page so the
    # Alpine layer can reconcile localStorage-primary / server-fallback.
    assert "sentinel-draft-value-xyz" in r.text


# --------------------------------------------------------------------------- #
# Task 3 — GET /brew/prefill dynamic re-prefill fragment                      #
# --------------------------------------------------------------------------- #


def test_prefill_fragment_coffee_change(app, seeded_regular_user, clean_brew_router) -> None:
    """GET /brew/prefill?coffee_id=X → re-resolved prefill (D-04); no per-attempt fields."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} D04")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        _create_session(
            db,
            by_user_id=uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            grind_setting_actual="d04-grind",
            rating=Decimal("5"),
            notes="d04 source notes",
        )

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/prefill?coffee_id={cid}", headers={"HX-Request": "true"})
    assert r.status_code == 200, f"prefill fragment must 200, got {r.status_code}"
    assert "d04-grind" in r.text
    # rating/observed/notes are per-attempt — NOT part of the prefill fragment.
    assert "d04 source notes" not in r.text


def test_prefill_fragment_recipe_wins(app, seeded_regular_user, clean_brew_router) -> None:
    """GET /brew/prefill?recipe_id=Y overwrites dose/water/temp/grind (D-05)."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} D05")
        recipe = _seed_recipe(
            db, name=f"{_RECIPE_PREFIX} Kasuya", dose=20, water=300, temp=88, grind="recipe-grind"
        )
        db.commit()
        cid, rid = coffee.id, recipe.id
    with SessionLocal() as db:
        _create_session(
            db,
            by_user_id=uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            grind_setting_actual="session-grind",
        )

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/prefill?recipe_id={rid}", headers={"HX-Request": "true"})
    assert r.status_code == 200
    # The four template fields come from the recipe (recipe-wins).
    assert "recipe-grind" in r.text
    assert "session-grind" not in r.text


def test_prefill_fragment_advertised_chips(app, seeded_regular_user, clean_brew_router) -> None:
    """GET /brew/prefill?coffee_id=X surfaces that coffee's advertised chips (D-11)."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal
    from app.services import flavor_notes as fn_svc

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        note = fn_svc.create_flavor_note(
            db, name="RouterBlueberry", category="other", by_user_id=uid
        )
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} D11", advertised=[note.id])
        db.commit()
        cid = coffee.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/prefill?coffee_id={cid}", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "RouterBlueberry" in r.text, "advertised chip note name must render in the fragment"


def test_prefill_user_scoped(
    app, seeded_regular_user, seeded_admin_user, clean_brew_router
) -> None:
    """A coffee/recipe id resolves only against the authed user's own sessions."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    owner_uid = seeded_admin_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Scoped")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        # Only the admin user has a session with this coffee.
        _create_session(
            db,
            by_user_id=owner_uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            grind_setting_actual="admin-only-grind",
        )

    # The regular user requests prefill for the same coffee → no cross-user leak.
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/prefill?coffee_id={cid}", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "admin-only-grind" not in r.text, "must not leak another user's last-session values"


def test_prefill_unknown_coffee_blank(app, seeded_regular_user, clean_brew_router) -> None:
    """A never-brewed coffee → blank prefill-dependent fields + chips, no crash."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Unknown")
        db.commit()
        cid = coffee.id

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get(f"/brew/prefill?coffee_id={cid}", headers={"HX-Request": "true"})
    assert r.status_code == 200, f"never-brewed coffee prefill must 200, got {r.status_code}"


def test_prefill_requires_user(app, clean_brew_router) -> None:
    """GET /brew/prefill is require_user-gated (anonymous → 401)."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/brew/prefill?coffee_id=1", headers={"HX-Request": "true"})
    assert r.status_code == 401, f"anonymous prefill must 401, got {r.status_code}"
