"""Real router tests for plan 04-09 (replaces the Wave-0 stub).

Cases per 04-VALIDATION.md row 04-09-NN. Mirrors the structure of
``tests/phase_04/test_routers_roasters.py`` and ``test_routers_coffees.py``.

Bag CRUD nested under coffee detail + bag photo upload pipeline coverage:
- bag CRUD endpoints (new/create/edit/update/archive)
- photo upload pipeline (valid JPEG round-trip, oversize / bad magic /
  polyglot / EXIF strip / replace-unlinks-old / delete)
- CSRF gate
- T-04-MASS via extra='forbid'

Most tests require Postgres + the p4_shared_catalog migration AND the
``photo_volume`` fixture (monkeypatches ``app.services.photos.PHOTOS_DIR``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image


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
            row = conn.execute(text("SELECT to_regclass('public.bags')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p4_shared_catalog migration not applied")


def _prime_csrf(client: Any) -> str:
    """GET ``/`` to mint a real, signed csrftoken; wire it onto the client.

    Same shape as the helper in ``test_routers_roasters.py`` —
    ``starlette-csrf`` validates tokens via ``URLSafeSerializer.loads``,
    so the conftest fixture's literal placeholder fails the signature
    check until we replace it with a freshly-minted signed token.
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


def _seed_coffee(name: str = "Geometry") -> int:
    from app.db import SessionLocal
    from app.services import coffees as coffees_service

    with SessionLocal() as db:
        return coffees_service.create_coffee(
            db,
            name=name,
            roaster_id=None,
            origins=[],
            process=None,
            roast_level=None,
            notes="",
            advertised_flavor_note_ids=[],
            by_user_id=0,
        ).id


def _seed_bag(coffee_id: int) -> int:
    from app.db import SessionLocal
    from app.services import bags as bags_service

    with SessionLocal() as db:
        return bags_service.create_bag(db, coffee_id=coffee_id, by_user_id=0).id


def _get_bag(bag_id: int) -> Any:
    from app.db import SessionLocal
    from app.services import bags as bags_service

    with SessionLocal() as db:
        return bags_service.get_bag(db, bag_id=bag_id)


# --------------------------------------------------------------------------- #
# GET /coffees/{id}/bags/new — empty form fragment                             #
# --------------------------------------------------------------------------- #


def test_open_new_bag_returns_form_fragment(authed_client: Any, clean_catalog: None) -> None:
    """GET /coffees/{id}/bags/new → 200 + form fragment with coffee_id hidden."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    resp = authed_client.get(f"/coffees/{cid}/bags/new")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "<form" in body
    # Hidden input wires the coffee_id into the create POST.
    assert f'value="{cid}"' in body


# --------------------------------------------------------------------------- #
# POST /coffees/{id}/bags — create                                             #
# --------------------------------------------------------------------------- #


def test_create_bag_valid(authed_client: Any, clean_catalog: None) -> None:
    """Valid form → 200 + bag row fragment; DB has the row."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        f"/coffees/{cid}/bags",
        data={
            "roast_date": "2026-05-01",
            "weight_grams": "250",
            "opened_at": "",
            "finished_at": "",
            "notes": "First test bag.",
        },
    )
    assert resp.status_code == 200, resp.text
    assert 'id="bag-' in resp.text
    # OOB form-clear on create.
    assert 'id="bag-form-mount"' in resp.text

    # DB row exists.
    from app.db import SessionLocal
    from app.services import bags as bags_service

    with SessionLocal() as db:
        rows = bags_service.list_bags_for_coffee(db, coffee_id=cid)
    assert len(rows) == 1
    assert rows[0].weight_grams == 250


def test_create_bag_unknown_coffee_id_returns_404(authed_client: Any, clean_catalog: None) -> None:
    """POST to a coffee that doesn't exist → 404 (router pre-checks)."""
    _require_postgres()
    _require_p4_migration_applied()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        "/coffees/999999/bags",
        data={"notes": ""},
    )
    assert resp.status_code == 404


def test_create_bag_zero_weight_rejected(authed_client: Any, clean_catalog: None) -> None:
    """weight_grams=0 → 200 + form re-render with field error."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        f"/coffees/{cid}/bags",
        data={
            "roast_date": "",
            "weight_grams": "0",
            "opened_at": "",
            "finished_at": "",
            "notes": "",
        },
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


def test_create_bag_extra_field_rejected(authed_client: Any, clean_catalog: None) -> None:
    """T-04-MASS: unknown form field → 200 + form re-render with error."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    _prime_csrf(authed_client)
    resp = authed_client.post(
        f"/coffees/{cid}/bags",
        data={
            "notes": "ok",
            "is_admin": "true",  # extra='forbid' rejects.
        },
    )
    assert resp.status_code == 200
    assert "text-red-700" in resp.text


# --------------------------------------------------------------------------- #
# GET /bags/{id}/edit + POST /bags/{id} — update                               #
# --------------------------------------------------------------------------- #


def test_edit_bag_pre_populates_fields(authed_client: Any, clean_catalog: None) -> None:
    """GET /bags/{id}/edit → form fragment carries existing values."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    # Seed a bag with explicit weight + notes so the prepopulation
    # assertion has something deterministic to check.
    from app.db import SessionLocal
    from app.services import bags as bags_service

    with SessionLocal() as db:
        bag = bags_service.create_bag(
            db, coffee_id=cid, weight_grams=300, notes="Test bag.", by_user_id=0
        )
    resp = authed_client.get(f"/bags/{bag.id}/edit")
    assert resp.status_code == 200
    assert 'value="300"' in resp.text
    assert "Test bag." in resp.text


def test_update_bag_persists(authed_client: Any, clean_catalog: None) -> None:
    """POST /bags/{id} with new weight → DB reflects."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)
    resp = authed_client.post(
        f"/bags/{bid}",
        data={
            "roast_date": "",
            "weight_grams": "500",
            "opened_at": "",
            "finished_at": "",
            "notes": "updated",
        },
    )
    assert resp.status_code == 200, resp.text

    bag = _get_bag(bid)
    assert bag.weight_grams == 500
    assert bag.notes == "updated"


# --------------------------------------------------------------------------- #
# POST /bags/{id}/photo — upload                                               #
# --------------------------------------------------------------------------- #


def test_upload_photo_valid_jpeg_round_trip(
    authed_client: Any,
    clean_catalog: None,
    photo_volume: Path,
    synthetic_jpeg: Callable[..., bytes],
) -> None:
    """Valid JPEG upload → 200 + zone re-render; bag.photo_filename set; file on disk."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    payload = synthetic_jpeg(dimensions=(1200, 900))
    resp = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("test.jpg", payload, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text

    bag = _get_bag(bid)
    assert bag.photo_filename, "photo_filename was not set"
    assert bag.photo_filename.endswith(".jpg")

    # File on disk inside photo_volume.
    main_path = photo_volume / bag.photo_filename
    assert main_path.exists()
    stem = bag.photo_filename.removesuffix(".jpg")
    thumb_path = photo_volume / f"{stem}-thumb.jpg"
    assert thumb_path.exists()

    # Zone fragment carries the new thumb URL.
    assert f"/photos/{stem}-thumb.jpg" in resp.text


def test_upload_photo_oversize_rejected(
    authed_client: Any,
    clean_catalog: None,
    photo_volume: Path,
) -> None:
    """Oversize body (>5MB) → 200 + zone re-render with 'too large' message."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    from app.services.photos import MAX_BYTES

    oversized = b"\xff\xd8\xff\xe0" + b"\x00" * (MAX_BYTES + 1 - 4)
    resp = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("big.jpg", oversized, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    assert "too large" in resp.text.lower()

    bag = _get_bag(bid)
    assert bag.photo_filename is None


def test_upload_photo_bad_magic_rejected(
    authed_client: Any,
    clean_catalog: None,
    photo_volume: Path,
    bad_magic_jpeg: bytes,
) -> None:
    """Magic-byte mismatch → 200 + zone with 'unsupported' or 'couldn't read' message."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    resp = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("evil.jpg", bad_magic_jpeg, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    body_lower = resp.text.lower()
    assert "unsupported" in body_lower or "couldn't read" in body_lower

    bag = _get_bag(bid)
    assert bag.photo_filename is None


def test_upload_photo_polyglot_strip_at_route(
    authed_client: Any,
    clean_catalog: None,
    photo_volume: Path,
    polyglot_jpeg: bytes,
) -> None:
    """Polyglot JPEG+PHP → re-encode strips the trailer; saved file has no <?php."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    resp = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("poly.jpg", polyglot_jpeg, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text

    bag = _get_bag(bid)
    assert bag.photo_filename, "polyglot should round-trip the magic-byte gate"
    saved = (photo_volume / bag.photo_filename).read_bytes()
    assert b"<?php" not in saved, "polyglot trailer survived re-encode"
    assert saved.endswith(b"\xff\xd9"), "saved file does not end at JPEG EOI"


def test_upload_photo_exif_stripped_at_route(
    authed_client: Any,
    clean_catalog: None,
    photo_volume: Path,
    exif_jpeg: Callable[..., bytes],
) -> None:
    """EXIF-laden JPEG → saved file has empty EXIF (T-04-EXIF end-to-end)."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    resp = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("exif.jpg", exif_jpeg(gps_lat=37.0, gps_lon=-122.0), "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text

    bag = _get_bag(bid)
    assert bag.photo_filename
    saved = photo_volume / bag.photo_filename
    with Image.open(saved) as img:
        exif = img.getexif()
        assert not exif or len(exif) == 0, f"EXIF leaked: {dict(exif)!r}"


def test_upload_photo_replace_unlinks_old(
    authed_client: Any,
    clean_catalog: None,
    photo_volume: Path,
    synthetic_jpeg: Callable[..., bytes],
) -> None:
    """Second photo upload → first file pair unlinked; bag points at the new pair."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    # First upload.
    resp1 = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("a.jpg", synthetic_jpeg(dimensions=(800, 600)), "image/jpeg")},
    )
    assert resp1.status_code == 200, resp1.text
    first = _get_bag(bid).photo_filename
    assert first
    first_stem = first.removesuffix(".jpg")
    first_main = photo_volume / first
    first_thumb = photo_volume / f"{first_stem}-thumb.jpg"
    assert first_main.exists()
    assert first_thumb.exists()

    # Second upload — replace.
    resp2 = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("b.jpg", synthetic_jpeg(dimensions=(900, 700)), "image/jpeg")},
    )
    assert resp2.status_code == 200, resp2.text
    second = _get_bag(bid).photo_filename
    assert second
    assert second != first
    second_stem = second.removesuffix(".jpg")
    second_main = photo_volume / second
    second_thumb = photo_volume / f"{second_stem}-thumb.jpg"

    # Old pair is gone.
    assert not first_main.exists(), "old main not unlinked"
    assert not first_thumb.exists(), "old thumb not unlinked"
    # New pair is on disk.
    assert second_main.exists()
    assert second_thumb.exists()


# --------------------------------------------------------------------------- #
# POST /bags/{id}/photo/delete                                                 #
# --------------------------------------------------------------------------- #


def test_delete_photo(
    authed_client: Any,
    clean_catalog: None,
    photo_volume: Path,
    synthetic_jpeg: Callable[..., bytes],
) -> None:
    """Delete clears photo_filename + unlinks the on-disk pair."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    resp_up = authed_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("a.jpg", synthetic_jpeg(), "image/jpeg")},
    )
    assert resp_up.status_code == 200
    fn = _get_bag(bid).photo_filename
    assert fn
    stem = fn.removesuffix(".jpg")
    main = photo_volume / fn
    thumb = photo_volume / f"{stem}-thumb.jpg"
    assert main.exists()
    assert thumb.exists()

    resp_del = authed_client.post(f"/bags/{bid}/photo/delete")
    assert resp_del.status_code == 200, resp_del.text

    bag = _get_bag(bid)
    assert bag.photo_filename is None
    assert not main.exists()
    assert not thumb.exists()


# --------------------------------------------------------------------------- #
# POST /bags/{id}/archive                                                      #
# --------------------------------------------------------------------------- #


def test_archive_bag(authed_client: Any, clean_catalog: None) -> None:
    """Archive surrogate: finished_at IS NOT NULL after POST /archive.

    Bags have NO ``archived`` column — finished_at IS NOT NULL is the
    archive surrogate per the plan-04-09 lock.
    """
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)
    _prime_csrf(authed_client)

    resp = authed_client.post(f"/bags/{bid}/archive")
    assert resp.status_code == 200, resp.text

    bag = _get_bag(bid)
    assert bag.finished_at is not None


# --------------------------------------------------------------------------- #
# CSRF                                                                        #
# --------------------------------------------------------------------------- #


def test_csrf_missing_returns_403_on_photo_upload(
    csrf_client: Any,
    clean_catalog: None,
    photo_volume: Path,
    synthetic_jpeg: Callable[..., bytes],
) -> None:
    """Mismatched CSRF on multipart photo upload → 403 from CSRFMiddleware."""
    _require_postgres()
    _require_p4_migration_applied()
    cid = _seed_coffee()
    bid = _seed_bag(cid)

    resp = csrf_client.post(
        f"/bags/{bid}/photo",
        files={"photo": ("a.jpg", synthetic_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 403
