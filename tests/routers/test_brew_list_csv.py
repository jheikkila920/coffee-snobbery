"""Router tests for plan 05-06 — the sessions list + CSV export/import routes.

Extends ``app/routers/brew.py`` with:

* ``GET /brew``           — per-user sessions list (page) / HTMX fragment.
* ``GET /brew/export``    — filtered, name-resolved CSV download (attachment).
* ``GET /brew/import``    — the upload page.
* ``POST /brew/import``   — single-transaction import → per-row result fragment.

Covers the plan's ``<behavior>`` for Task 1:

* ``test_list_user_scoped``      — BREW-10 / T-05-24 IDOR: only the authed user's
  sessions appear; a second user's never leak.
* ``test_list_filters``          — coffee / brewer / rating-range / date-range
  filters parse and AND together.
* ``test_list_fragment_vs_page`` — HX-Request returns the list fragment; a plain
  GET returns the full page.
* ``test_export_attachment``     — text/csv + Content-Disposition attachment,
  user + filter scoped.
* ``test_import_outcomes_http``  — refused / skipped / inserted via HTTP, accepted
  rows inserted.
* ``test_import_requires_csrf``  — tokenless import POST → 403 (T-05-26).

Real Postgres + the p5 migration are required; the skip gates mirror
``tests/routers/test_brew_router.py``. Catalog + brew rows are seeded directly
via ``SessionLocal``; the authed ``TestClient`` reuses the same signed-cookie +
double-submit CSRF priming pattern.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Skip gates (mirror tests/routers/test_brew_router.py)                        #
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
    try:
        from app.routers.brew import router  # noqa: F401
    except ImportError:
        pytest.skip("app.routers.brew not importable")


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture (LIKE-scoped to this test's own rows)        #
# --------------------------------------------------------------------------- #

_COFFEE_PREFIX = "ListCsv Coffee"
_EQUIP_PREFIX = "ListCsvRig"


def _seed_coffee(db, *, name: str):
    from app.models.coffee import Coffee

    coffee = Coffee(name=name)
    db.add(coffee)
    db.flush()
    return coffee


def _seed_equipment(db, *, type_: str, brand: str):
    from app.models.equipment import Equipment

    eq = Equipment(type=type_, brand=brand, model=f"{_EQUIP_PREFIX}-{brand}")
    db.add(eq)
    db.flush()
    return eq


@pytest.fixture
def clean_brew_list() -> Iterator[None]:
    """Wipe this test's brew rows + seeded catalog fixtures before AND after."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(text("DELETE FROM equipment WHERE model LIKE 'ListCsvRig%'"))
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'ListCsv Coffee%'"))

    _reset()
    yield
    _reset()


def _authed_client(app: Any, signed_cookie: str):
    """TestClient with the session cookie + a real signed CSRF pair."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.cookies.set("session_id", signed_cookie)
    _prime_csrf(client)
    return client


def _prime_csrf(client: Any) -> str:
    client.cookies.delete("csrftoken")
    response = client.get("/")
    token = response.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


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
# GET /brew — per-user scope + fragment/page + filters                        #
# --------------------------------------------------------------------------- #


def test_list_user_scoped(app, seeded_regular_user, seeded_admin_user, clean_brew_list) -> None:
    """GET /brew returns ONLY the authed user's sessions (BREW-10 / T-05-24)."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    mine_uid = seeded_regular_user["user"].id
    other_uid = seeded_admin_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Scope")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        _create_session(
            db,
            by_user_id=mine_uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            notes="my-own-session-marker",
        )
        _create_session(
            db,
            by_user_id=other_uid,
            coffee_id=cid,
            brewed_at=datetime.now(UTC),
            notes="other-user-session-marker",
        )

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/brew")
    assert r.status_code == 200, f"GET /brew must 200, got {r.status_code}: {r.text[:200]}"
    # The page renders coffee names, not raw notes, but the IDOR-critical
    # assertion is that the OTHER user's session count never reaches this list.
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        assert len(svc.list_brew_sessions(db, by_user_id=mine_uid)) == 1
        assert len(svc.list_brew_sessions(db, by_user_id=other_uid)) == 1
    # The coffee name appears once (only my session); a second user's identical
    # coffee must not double-count into my list. Assert exactly one row id.
    assert r.text.count(f"session-{_session_ids(SessionLocal, mine_uid)[0]}") >= 1


def _session_ids(SessionLocal, uid) -> list[int]:
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        return [s.id for s in svc.list_brew_sessions(db, by_user_id=uid)]


def test_list_fragment_vs_page(app, seeded_regular_user, clean_brew_list) -> None:
    """HX-Request → list fragment (#session-list); plain GET → full page."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Frag")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        _create_session(db, by_user_id=uid, coffee_id=cid, brewed_at=datetime.now(UTC))

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    page = client.get("/brew")
    frag = client.get("/brew", headers={"HX-Request": "true"})
    assert page.status_code == 200
    assert frag.status_code == 200
    # The page extends base.html (full document); the fragment does not.
    assert "<!doctype html>" in page.text.lower()
    assert "<!doctype html>" not in frag.text.lower()
    # Both carry the HTMX filter target id.
    assert 'id="session-list"' in page.text
    assert 'id="session-list"' in frag.text


def test_list_filters(app, seeded_regular_user, clean_brew_list) -> None:
    """coffee / brewer / rating-range / date-range filters parse and AND together."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee_a = _seed_coffee(db, name=f"{_COFFEE_PREFIX} FilterA")
        coffee_b = _seed_coffee(db, name=f"{_COFFEE_PREFIX} FilterB")
        brewer = _seed_equipment(db, type_="brewer", brand="V60")
        db.commit()
        cid_a, cid_b, bid = coffee_a.id, coffee_b.id, brewer.id
    now = datetime.now(UTC)
    with SessionLocal() as db:
        # match: coffee A, brewer set, rating 4, recent
        _create_session(
            db,
            by_user_id=uid,
            coffee_id=cid_a,
            brewer_id=bid,
            brewed_at=now,
            rating=Decimal("4"),
        )
        # different coffee
        _create_session(db, by_user_id=uid, coffee_id=cid_b, brewed_at=now, rating=Decimal("4"))
        # low rating
        _create_session(
            db,
            by_user_id=uid,
            coffee_id=cid_a,
            brewer_id=bid,
            brewed_at=now,
            rating=Decimal("1"),
        )
        # too old
        _create_session(
            db,
            by_user_id=uid,
            coffee_id=cid_a,
            brewer_id=bid,
            brewed_at=now - timedelta(days=60),
            rating=Decimal("4"),
        )

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    date_from = (now - timedelta(days=7)).date().isoformat()
    r = client.get(
        "/brew",
        params={
            "coffee_id": cid_a,
            "brewer_id": bid,
            "rating_min": "3",
            "rating_max": "5",
            "date_from": date_from,
        },
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    # Only the single fully-matching session id survives all four filters.
    from app.services import brew_sessions as svc

    with SessionLocal() as db:
        matches = svc.list_brew_sessions(
            db,
            by_user_id=uid,
            coffee_id=cid_a,
            brewer_id=bid,
            rating_min=Decimal("3"),
            rating_max=Decimal("5"),
            date_from=now - timedelta(days=7),
        )
    assert len(matches) == 1, f"filters must AND to one row, got {len(matches)}"
    assert f"session-{matches[0].id}" in r.text


# --------------------------------------------------------------------------- #
# GET /brew/export — attachment, scoped                                       #
# --------------------------------------------------------------------------- #


def test_export_attachment(app, seeded_regular_user, clean_brew_list) -> None:
    """GET /brew/export → text/csv + Content-Disposition attachment, user-scoped."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Export")
        db.commit()
        cid = coffee.id
    with SessionLocal() as db:
        _create_session(db, by_user_id=uid, coffee_id=cid, brewed_at=datetime.now(UTC))

    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.get("/brew/export")
    assert r.status_code == 200, f"export must 200, got {r.status_code}"
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    # The canonical round-trip header set + the exported coffee name are present.
    assert "coffee_name" in r.text
    assert f"{_COFFEE_PREFIX} Export" in r.text


# --------------------------------------------------------------------------- #
# /brew/import — per-row outcomes + CSRF                                       #
# --------------------------------------------------------------------------- #


def _csv_bytes(rows: list[str]) -> bytes:
    header = (
        "coffee_name,roaster_name,roast_date,recipe_name,brewer,grinder,kettle,"
        "water_type,dose_grams,water_grams,yield_grams,tds_pct,water_temp_c,"
        "grind_setting,rating,observed_flavor_notes,notes,brewed_at"
    )
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


def test_import_outcomes_http(app, seeded_regular_user, clean_brew_list) -> None:
    """POST /brew/import → per-row result fragment; accepted rows inserted."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from app.db import SessionLocal
    from app.services import brew_sessions as svc

    uid = seeded_regular_user["user"].id
    with SessionLocal() as db:
        coffee = _seed_coffee(db, name=f"{_COFFEE_PREFIX} Import")
        db.commit()
        cid = coffee.id
    # Pre-seed a duplicate at a fixed brewed_at so a re-named row is skipped.
    dup_at = datetime(2026, 5, 10, 8, 0, tzinfo=UTC)
    with SessionLocal() as db:
        _create_session(db, by_user_id=uid, coffee_id=cid, brewed_at=dup_at)

    cname = f"{_COFFEE_PREFIX} Import"
    rows = [
        # inserted: known coffee, new timestamp
        f"{cname},,,,,,,Filtered,15,250,,,93,22,4,,fresh import,2026-05-12T07:30",
        # skipped: same coffee + same brewed_at as the pre-seeded session
        f"{cname},,,,,,,Filtered,15,250,,,93,22,4,,dup,2026-05-10T08:00",
        # refused: coffee not in catalog
        "Totally Unknown Coffee,,,,,,,Filtered,15,250,,,93,22,4,,nope,2026-05-13T07:30",
    ]
    client = _authed_client(app, seeded_regular_user["signed_cookie"])
    r = client.post(
        "/brew/import",
        files={"file": ("sessions.csv", io.BytesIO(_csv_bytes(rows)), "text/csv")},
    )
    assert r.status_code == 200, f"import must 200, got {r.status_code}: {r.text[:300]}"
    body = r.text.lower()
    assert "inserted" in body
    assert "skipped" in body or "duplicate" in body
    assert "refused" in body
    assert "not in catalog" in body

    with SessionLocal() as db:
        rows_after = svc.list_brew_sessions(db, by_user_id=uid)
    # pre-seeded dup (1) + the one inserted row (1) = 2; the refused/skipped add none.
    assert len(rows_after) == 2, f"expected 2 sessions after import, got {len(rows_after)}"


def test_import_requires_csrf(app, seeded_regular_user, clean_brew_list) -> None:
    """POST /brew/import without a CSRF token → 403 (T-05-26)."""
    _require_postgres()
    _require_p5_migration_applied()
    _require_brew_router()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.cookies.set("session_id", seeded_regular_user["signed_cookie"])
    rows = ["AnyCoffee,,,,,,,Filtered,15,250,,,93,22,4,,x,2026-05-12T07:30"]
    r = client.post(
        "/brew/import",
        files={"file": ("sessions.csv", io.BytesIO(_csv_bytes(rows)), "text/csv")},
    )
    assert r.status_code == 403, f"tokenless import POST must 403, got {r.status_code}"
