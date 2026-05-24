"""Real router tests for plan 04-10 (replaces the Wave-0 stub).

Cases per 04-VALIDATION.md row 04-10-NN — D-06 / T-04-AUTH photo serving
contract:

* **Auth gate (T-04-AUTH)** — anonymous → 404 (NOT 401 / 403). The
  handler reads ``request.state.user`` directly instead of using
  :func:`require_user`, so the unauth branch can return 404 to defeat
  existence enumeration. Asserted by ``test_anonymous_returns_404`` and
  ``test_anonymous_with_existing_file_still_404``.
* **Path traversal (T-04-PHOTO)** — filenames must match
  :func:`_is_safe_photo_filename`. ``../etc/passwd``, ``foo.png``,
  ``short.jpg``, ``UPPERCASEHEX.jpg`` all return 404. Asserted by
  ``test_authed_path_traversal_returns_404``,
  ``test_authed_wrong_extension_returns_404``,
  ``test_authed_malformed_uuid_returns_404``.
* **D-06 header contract** — ``Content-Type: image/jpeg``,
  ``Cache-Control: private, max-age=31536000, immutable``,
  ``X-Content-Type-Options: nosniff``, ``Content-Disposition: inline``.
  Asserted in ``test_authed_response_has_*`` cases.
* **Phase 1 D-12 contract** — route-set ``Cache-Control`` survives
  :class:`FragmentCacheHeadersMiddleware` (does not get overwritten to
  ``no-store`` or ``private, no-cache, must-revalidate``). Asserted by
  ``test_cache_control_not_overwritten_by_middleware`` and
  ``test_hx_request_does_not_force_no_store``.

The auth gate goes through ``SessionMiddleware`` which is DB-backed, so
the authed tests require Postgres + the Phase 2 sessions table to exist.
Tests skip cleanly otherwise. The anonymous tests work without the DB
because ``SessionMiddleware`` short-circuits on a missing cookie before
any DB query.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# Canonical UUID-shaped names used across tests. ``_main`` exercises the
# happy path; ``_thumb`` checks the ``-thumb`` regex branch; ``_missing``
# is the regex-passes-but-file-absent branch.
UUID_MAIN = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
UUID_THUMB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
UUID_MISSING = "cccccccccccccccccccccccccccccccc"


def _require_postgres() -> None:
    """Skip cleanly when the host has no Postgres (unit-only run)."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 4 router test needs the DB")


@pytest.fixture
def written_main_jpeg(
    photo_volume: Path,
    synthetic_jpeg: Any,
) -> str:
    """Write ``{UUID_MAIN}.jpg`` to ``photo_volume`` and return its filename.

    Uses :func:`synthetic_jpeg` for a real JPEG payload so the
    ``FileResponse`` content check (``len(response.content) > 0``) reflects
    a meaningful round-trip, not a sentinel byte. Returns the bare
    filename — callers join with ``photo_volume`` if they need the path.
    """
    name = f"{UUID_MAIN}.jpg"
    (photo_volume / name).write_bytes(synthetic_jpeg())
    return name


@pytest.fixture
def written_thumb_jpeg(
    photo_volume: Path,
    synthetic_jpeg: Any,
) -> str:
    """Write ``{UUID_THUMB}-thumb.jpg`` to ``photo_volume`` for the thumb branch."""
    name = f"{UUID_THUMB}-thumb.jpg"
    (photo_volume / name).write_bytes(synthetic_jpeg(dimensions=(400, 400)))
    return name


@pytest.fixture
def anon_client(app: Any) -> Iterator[Any]:
    """``TestClient`` with NO session cookie — exercises the D-06 anon branch.

    Distinct from the conftest ``authed_client`` (preloads a signed
    session cookie) and ``csrf_client`` (preloads session + mismatched
    CSRF). The unauth path never reaches CSRF — only GETs are tested
    here, and the request stops at the route handler's
    ``request.state.user is None`` check.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import DBAPIError, OperationalError

    try:
        with TestClient(app) as client:
            yield client
    except (OperationalError, DBAPIError, ConnectionError, OSError) as exc:
        pytest.skip(
            f"TestClient startup failed (Postgres unreachable?): {type(exc).__name__}: {exc}"
        )


# --------------------------------------------------------------------------- #
# Anonymous → 404 (T-04-AUTH existence-leak defense)                          #
# --------------------------------------------------------------------------- #


def test_anonymous_returns_404(
    anon_client: Any,
    photo_volume: Path,  # noqa: ARG001 — patches PHOTOS_DIR module-wide
    written_main_jpeg: str,
) -> None:
    """Anonymous GET /photos/{filename} → 404 (NOT 401 / NOT 403).

    Locks the D-06 existence-leak defense: returning 401 would advertise
    "this is an auth-gated route" and 403 would advertise "this file
    exists, you just can't see it." 404 says neither.
    """
    resp = anon_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text!r}"


def test_anonymous_with_existing_file_still_404(
    anon_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """Even with the file present on disk, anonymous → 404 (not 200, not 401)."""
    # Pre-condition: file must actually exist so this test is meaningful.
    assert (photo_volume / written_main_jpeg).is_file()  # noqa: PT018 — fixture invariant

    resp = anon_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Authed happy path + D-06 header contract                                    #
# --------------------------------------------------------------------------- #


def test_authed_returns_photo(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """Authenticated GET → 200 + image/jpeg body."""
    _require_postgres()
    resp = authed_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text!r}"
    assert resp.headers["content-type"] == "image/jpeg"
    assert len(resp.content) > 0
    # FileResponse should set the JPEG SOI marker as the first byte pair.
    assert resp.content.startswith(b"\xff\xd8"), "served bytes don't start with JPEG SOI marker"


def test_authed_response_has_d06_cache_headers(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """``Cache-Control`` includes ``private``, ``max-age=31536000``, ``immutable``."""
    _require_postgres()
    resp = authed_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 200

    cache_control = resp.headers["cache-control"].lower()
    assert "private" in cache_control, f"missing 'private' in Cache-Control: {cache_control!r}"
    assert "max-age=31536000" in cache_control, (
        f"missing 'max-age=31536000' in Cache-Control: {cache_control!r}"
    )
    assert "immutable" in cache_control, f"missing 'immutable' in Cache-Control: {cache_control!r}"


def test_authed_response_has_nosniff_header(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """``X-Content-Type-Options: nosniff`` — T-04-POLY MIME-sniff defense.

    The header is set by both the photo route AND the global
    :class:`SecurityHeadersMiddleware` (defense in depth). HTTPX
    collapses duplicate header values into a comma-joined list, so the
    response header may be ``"nosniff, nosniff"`` — we assert
    containment, not equality. Browsers treat any list of identical
    values as the single value (RFC 9110 §5.3 — repeated headers are
    equivalent to one header with comma-joined values).
    """
    _require_postgres()
    resp = authed_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 200
    assert "nosniff" in resp.headers["x-content-type-options"]


def test_authed_response_has_content_disposition_inline(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """``Content-Disposition: inline`` — render in <img>, never offer download."""
    _require_postgres()
    resp = authed_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == "inline"


# --------------------------------------------------------------------------- #
# Path traversal / filename validation (T-04-PHOTO)                           #
# --------------------------------------------------------------------------- #


def test_authed_path_traversal_returns_404(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
) -> None:
    """``/photos/..%2Fetc%2Fpasswd`` → 404 — either FastAPI 404s the route
    or the regex gate rejects, both result in 404 (never 200, never 401)."""
    _require_postgres()
    # URL-encoded traversal: the path parameter binds to the encoded form.
    # If FastAPI URL-decodes before binding, the regex still rejects it.
    resp = authed_client.get("/photos/..%2Fetc%2Fpasswd")
    assert resp.status_code == 404


def test_authed_wrong_extension_returns_404(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
) -> None:
    """``/photos/{uuid}.png`` → 404 — regex requires ``.jpg`` only."""
    _require_postgres()
    resp = authed_client.get(f"/photos/{UUID_MAIN}.png")
    assert resp.status_code == 404


def test_authed_malformed_uuid_returns_404(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
) -> None:
    """``/photos/short.jpg`` → 404 — regex requires 32 lowercase hex chars."""
    _require_postgres()
    resp = authed_client.get("/photos/short.jpg")
    assert resp.status_code == 404


def test_authed_uppercase_uuid_returns_404(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
) -> None:
    """Uppercase hex → 404 — regex anchors to ``[0-9a-f]`` (lowercase only).

    Plan 04-01's ``process_and_save`` always writes ``uuid.uuid4().hex``
    which is lowercase, so case-sensitivity is the intentional contract.
    """
    _require_postgres()
    upper = UUID_MAIN.upper()
    resp = authed_client.get(f"/photos/{upper}.jpg")
    assert resp.status_code == 404


def test_authed_existing_uuid_but_missing_file_returns_404(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
) -> None:
    """Regex passes but file absent → 404 (``photo_path.is_file()`` False)."""
    _require_postgres()
    # No file was written for UUID_MISSING; only the regex path passes.
    resp = authed_client.get(f"/photos/{UUID_MISSING}.jpg")
    assert resp.status_code == 404


def test_authed_thumb_variant_serves(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_thumb_jpeg: str,
) -> None:
    """``{uuid}-thumb.jpg`` → 200 — regex's ``(-thumb)?`` branch works."""
    _require_postgres()
    resp = authed_client.get(f"/photos/{written_thumb_jpeg}")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text!r}"
    assert resp.headers["content-type"] == "image/jpeg"


# --------------------------------------------------------------------------- #
# Phase 1 D-12 — route Cache-Control survives FragmentCacheHeadersMiddleware  #
# --------------------------------------------------------------------------- #


def test_cache_control_not_overwritten_by_middleware(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """Final ``Cache-Control`` is the route's value, not the middleware's.

    Locks Phase 1 D-12 ("do not overwrite if already set by the route").
    Without that escape hatch, every photo response would carry
    ``private, no-cache, must-revalidate`` (or ``no-store`` for HX-Request)
    instead of ``private, max-age=31536000, immutable``.
    """
    _require_postgres()
    resp = authed_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 200

    cache_control = resp.headers["cache-control"].lower()
    # MUST NOT be the middleware-default full-page value.
    assert "no-cache" not in cache_control, (
        f"Cache-Control overwritten by middleware: {cache_control!r}"
    )
    assert "must-revalidate" not in cache_control, (
        f"Cache-Control overwritten by middleware: {cache_control!r}"
    )
    # MUST NOT be the middleware-default HX-Request value.
    assert "no-store" not in cache_control, (
        f"Cache-Control overwritten by middleware: {cache_control!r}"
    )
    # MUST be the route's D-06 value.
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control


def test_hx_request_does_not_force_no_store(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """Even with ``HX-Request: true`` the photo route keeps its own Cache-Control.

    Extra-defensive test of Phase 1 D-12: the HX-Request branch of
    :class:`FragmentCacheHeadersMiddleware` would set ``no-store +
    Vary: HX-Request`` on a fragment response, but the photo route's
    pre-set ``Cache-Control`` MUST take precedence (the route is not a
    fragment — it's a binary file).
    """
    _require_postgres()
    resp = authed_client.get(
        f"/photos/{written_main_jpeg}",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    cache_control = resp.headers["cache-control"].lower()
    assert "no-store" not in cache_control
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control


# --------------------------------------------------------------------------- #
# Negative test of the StaticFiles-mount hypothesis                           #
# --------------------------------------------------------------------------- #


def test_route_emits_route_owned_headers_not_static_files(
    authed_client: Any,
    photo_volume: Path,  # noqa: ARG001
    written_main_jpeg: str,
) -> None:
    """All four D-06 headers present on the successful response.

    Starlette's :class:`StaticFiles` would not emit
    ``X-Content-Type-Options: nosniff`` or ``Content-Disposition: inline``
    on its own — their presence on a 200 response is a soft proof that
    the request was served by the custom router, not a StaticFiles mount.
    """
    _require_postgres()
    resp = authed_client.get(f"/photos/{written_main_jpeg}")
    assert resp.status_code == 200
    # All four D-06 headers present. ``x-content-type-options`` is also
    # set by :class:`SecurityHeadersMiddleware` so the field value may
    # be ``"nosniff, nosniff"`` (duplicate-header concat) — assert
    # containment, not equality, for that one.
    assert resp.headers["content-type"] == "image/jpeg"
    assert "nosniff" in resp.headers["x-content-type-options"]
    assert resp.headers["content-disposition"] == "inline"
    cc = resp.headers["cache-control"].lower()
    assert "private" in cc
    assert "max-age=31536000" in cc
    assert "immutable" in cc
