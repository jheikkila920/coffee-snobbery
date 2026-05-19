"""Phase 4 (Shared Catalog) shared test fixtures.

Wave 0 contract per ``.planning/phases/04-shared-catalog/04-VALIDATION.md``
§"Wave 0 Requirements": every Phase 4 test file is collectable after this
plan ships, even if most tests are skipped or red. Downstream plans
(04-02..04-11) replace the stubs in ``tests/phase_04/test_*.py`` with real
assertions and consume the fixtures defined below.

Fixtures (six per VALIDATION.md plus a seventh ``bad_magic_jpeg`` per the
plan's own action body):

- ``authed_client`` — :class:`fastapi.testclient.TestClient` carrying a
  valid session cookie + ``csrftoken`` cookie. Reuses the Phase 2
  ``seeded_admin_user`` fixture from ``tests/conftest.py``; if the auth
  service is not yet importable, the fixture skips (kept collectable).
- ``csrf_client`` — TestClient where ``csrftoken`` cookie does NOT match
  the ``X-CSRF-Token`` header (negative-CSRF probe).
- ``photo_volume`` — monkeypatches
  ``app.services.photos.PHOTOS_DIR`` to a ``tmp_path / "photos"`` Path
  (created on disk). Yielded value is the Path so callers can read it
  back to assert files exist / were unlinked. The module is imported
  lazily so the fixture stays collectable until plan 04-01 ships the
  service module.
- ``synthetic_jpeg`` — factory fixture returning bytes for a clean
  Pillow-generated JPEG of the requested size / dimensions. Used as the
  baseline happy-path payload.
- ``polyglot_jpeg`` — wraps ``synthetic_jpeg()`` and appends a PHP-tag
  trailer past the JPEG EOI marker (``\xff\xd9``). Re-encode-after-decode
  must strip the trailer (SEC-4 polyglot defense).
- ``exif_jpeg`` — produces a JPEG with GPS EXIF tags embedded. The Phase
  4 photos pipeline must strip EXIF; tests reopen the saved file and
  assert ``getexif()`` is empty.
- ``bad_magic_jpeg`` — bytes that start with ``<html><?php ...`` and end
  in ``.jpg`` (UI-uploadable). The magic-byte gate must reject before
  Pillow ever sees it.

The fixtures intentionally avoid importing ``app.services.photos`` at
module level. Plan 04-01 Task 1 lands the test stubs BEFORE Task 2 lands
the photos service module; importing at module level would break Task 1's
verify command.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image


# --------------------------------------------------------------------------- #
# Auth-aware TestClient fixtures                                              #
# --------------------------------------------------------------------------- #


@pytest.fixture
def authed_client(app: Any, seeded_admin_user: dict[str, Any]) -> Iterator[Any]:
    """``TestClient`` with a valid session cookie + ``csrftoken`` preloaded.

    Wraps the Phase 2 ``seeded_admin_user`` fixture (defined in the parent
    ``tests/conftest.py``) and the FastAPI app. The session cookie is the
    signed session id; ``csrftoken`` is a stable string the CSRFMiddleware
    accepts (the cookie itself only needs to match the header — the value
    is not cryptographically validated, per Phase 1 D-09).

    Lazy-imports :class:`fastapi.testclient.TestClient` to keep collection
    clean if FastAPI's optional dependency tree slips.
    """
    from fastapi.testclient import TestClient

    csrf_token = "test-csrf-token-phase04-fixture"  # noqa: S105 — test fixture, not a credential
    with TestClient(app) as client:
        client.cookies.set("session_id", seeded_admin_user["signed_cookie"])
        client.cookies.set("csrftoken", csrf_token)
        # Stash the token on the client so tests can pass it as the
        # ``X-CSRF-Token`` header (or the hidden form field via the shim).
        client.headers["X-CSRF-Token"] = csrf_token
        yield client


@pytest.fixture
def csrf_client(app: Any, seeded_admin_user: dict[str, Any]) -> Iterator[Any]:
    """``TestClient`` with mismatched CSRF (cookie != header) for negative tests.

    The session cookie is valid (so the request reaches the CSRF gate
    rather than auth), but the ``X-CSRF-Token`` header value differs from
    the ``csrftoken`` cookie value. Phase 1's CSRFMiddleware (double-submit
    cookie) rejects with 403.
    """
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        client.cookies.set("session_id", seeded_admin_user["signed_cookie"])
        client.cookies.set("csrftoken", "cookie-side-token")
        client.headers["X-CSRF-Token"] = "header-side-different-token"
        yield client


# --------------------------------------------------------------------------- #
# Photo-pipeline fixtures (Wave 0 baseline for plan 04-01 Task 2 and beyond)  #
# --------------------------------------------------------------------------- #


@pytest.fixture
def photo_volume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Monkeypatch ``app.services.photos.PHOTOS_DIR`` to a per-test directory.

    Required by every photos test to avoid touching the real
    ``/app/data/photos`` named volume. Yields the Path so the test can
    assert against it directly.

    Lazy-imports the module so this fixture stays collectable BEFORE plan
    04-01 Task 2 lands ``app.services.photos``. Tests that request this
    fixture will skip cleanly until the module exists.
    """
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    try:
        import app.services.photos as photos_mod
    except ImportError:
        pytest.skip("Wave 1 dependency: app.services.photos (plan 04-01 Task 2)")
    monkeypatch.setattr(photos_mod, "PHOTOS_DIR", photos_dir)
    yield photos_dir


@pytest.fixture
def synthetic_jpeg() -> Callable[..., bytes]:
    """Factory returning bytes for a clean Pillow-generated JPEG.

    Signature: ``synthetic_jpeg(size_bytes: int | None = None,
    dimensions: tuple[int, int] = (800, 600)) -> bytes``.

    ``size_bytes`` is informational only — Pillow's quality-85 JPEG of an
    800x600 solid-color image lands around 8–12KB; callers that need a
    specific byte count for an oversize-rejection probe should construct
    the payload directly instead of asking this fixture for one. The
    parameter is accepted to keep the call site readable.
    """
    def _factory(
        size_bytes: int | None = None,  # noqa: ARG001 — see docstring
        dimensions: tuple[int, int] = (800, 600),
    ) -> bytes:
        buf = io.BytesIO()
        img = Image.new("RGB", dimensions, color=(120, 80, 60))
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    return _factory


@pytest.fixture
def polyglot_jpeg(synthetic_jpeg: Callable[..., bytes]) -> bytes:
    """Valid JPEG with a PHP/HTML trailer past the EOI marker.

    SEC-4 polyglot defense fixture. The trailer survives a naive byte-copy
    but the Pillow re-encode in ``app.services.photos.process_and_save``
    strips it (the saved file ends with the JPEG ``\\xff\\xd9`` EOI
    marker and no ``<?php`` substring).
    """
    return synthetic_jpeg() + b"\x00<?php echo 'pwn'; ?>"


@pytest.fixture
def exif_jpeg() -> Callable[..., bytes]:
    """Factory returning a JPEG with GPS EXIF tags embedded.

    Uses Pillow's own EXIF API to attach GPS coordinates rather than the
    optional ``piexif`` dependency. The fixture asserts (at construction
    time) that the produced bytes round-trip back through ``Image.open``
    with a non-empty ``getexif()`` — guaranteeing the EXIF-strip test
    has a meaningful baseline.
    """
    def _factory(gps_lat: float = 37.0, gps_lon: float = -122.0) -> bytes:
        buf = io.BytesIO()
        img = Image.new("RGB", (640, 480), color=(50, 50, 50))
        exif = img.getexif()
        # 0x8825 = GPSInfo IFD pointer; storing the IFD inline keeps the
        # fixture self-contained (no piexif dep). Pillow accepts dict-style
        # writes into the GPS IFD via the GPS-info child.
        gps_ifd = exif.get_ifd(0x8825)
        # Tag 1 = N/S ref, 2 = lat, 3 = E/W ref, 4 = lon. Rational triples
        # as ((deg, 1), (min, 1), (sec, 100)) per the EXIF GPS spec.
        gps_ifd[1] = "N" if gps_lat >= 0 else "S"
        gps_ifd[3] = "E" if gps_lon >= 0 else "W"
        abs_lat = abs(gps_lat)
        abs_lon = abs(gps_lon)
        gps_ifd[2] = (
            (int(abs_lat), 1),
            (int((abs_lat % 1) * 60), 1),
            (int(((abs_lat * 60) % 1) * 6000), 100),
        )
        gps_ifd[4] = (
            (int(abs_lon), 1),
            (int((abs_lon % 1) * 60), 1),
            (int(((abs_lon * 60) % 1) * 6000), 100),
        )
        # 0x010E = ImageDescription — a top-level EXIF tag, easier to
        # round-trip than the GPS IFD on all Pillow paths. Belt-and-braces.
        exif[0x010E] = "snobbery-phase04-fixture"
        img.save(buf, format="JPEG", quality=85, exif=exif.tobytes())
        data = buf.getvalue()
        # Sanity: the fixture itself must produce non-empty EXIF, or the
        # downstream "EXIF stripped" assertion is meaningless.
        with Image.open(io.BytesIO(data)) as probe:
            assert probe.getexif(), "exif_jpeg fixture produced no EXIF — fix the fixture"
        return data

    return _factory


@pytest.fixture
def bad_magic_jpeg() -> bytes:
    """JPEG-extension bytes that are actually HTML/PHP (magic-byte mismatch)."""
    return b"<html><body><?php system($_GET['c']); ?></body></html>"
