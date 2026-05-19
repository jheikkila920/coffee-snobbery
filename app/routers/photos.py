"""Auth-gated photo serving route — D-06.

Anonymous → 404 (NOT 403); only well-formed UUID filenames accepted;
explicit ``Content-Type`` + ``X-Content-Type-Options: nosniff`` +
``Cache-Control: private, max-age=31536000, immutable`` +
``Content-Disposition: inline``.

NOT a :class:`fastapi.staticfiles.StaticFiles` mount (Phase 0 invariant +
CONTEXT D-06): a StaticFiles mount would serve photos to unauthenticated
clients and would let the browser MIME-sniff the response. The custom
route here is the only safe path.

Threat model coverage (plan 04-10 ``<threat_model>``):

* **T-04-AUTH (Information Disclosure)** — anonymous request must return
  404 to defeat existence enumeration. Read ``request.state.user``
  directly rather than using :func:`app.dependencies.auth.require_user`
  (which raises 401 — leaks "this is an auth-gated route").
* **Tampering / path traversal** — :func:`_is_safe_photo_filename` (from
  :mod:`app.services.photos`) restricts the filename to the UUID4-hex
  ``.jpg`` shape. Belt-and-braces ``Path.resolve().relative_to(...)``
  re-check defends against any future regex relaxation.
* **T-04-POLY (MIME-sniff spoofing)** — explicit ``Content-Type:
  image/jpeg`` + ``X-Content-Type-Options: nosniff`` + ``Content-
  Disposition: inline``. All saved files are JPEG (plan 04-01
  ``process_and_save`` always re-encodes to JPEG regardless of upload
  format), so the explicit media type is correct for every file the
  pipeline produces.
* **Cache-leak (Information Disclosure)** — ``private`` keeps photos
  out of shared caches (CDN, corporate proxy). ``max-age=31536000,
  immutable`` is safe because filenames are UUID4-hex (write-once) —
  the browser never needs to revalidate.

Phase 1 D-12 interaction: the route sets its own ``Cache-Control``, and
:class:`app.middleware.fragment_cache.FragmentCacheHeadersMiddleware`
"does not overwrite" routes that set one themselves. The contract is
verified end-to-end in
``tests/phase_04/test_routers_photos.py::test_cache_control_not_overwritten_by_middleware``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

# Import the module (not the symbols) so the ``PHOTOS_DIR`` attribute is
# looked up dynamically on every request. The Wave-0 ``photo_volume``
# fixture monkeypatches ``app.services.photos.PHOTOS_DIR`` for tests —
# binding the name directly into this module via
# ``from ... import PHOTOS_DIR`` would freeze the value at import time
# and the fixture would have no effect. ``_is_safe_photo_filename`` is
# a pure function so the binding form is irrelevant for it; aliased
# locally below for readability.
from app.services import photos as _photos_svc

_is_safe_photo_filename = _photos_svc._is_safe_photo_filename

router = APIRouter(prefix="/photos", tags=["photos"])


@router.get("/{filename}")
def serve_photo(filename: str, request: Request) -> FileResponse:
    """D-06: auth-gated photo serve. Anonymous → 404, NOT 403.

    Per CONTEXT D-06 the unauthenticated response is 404 to avoid
    leaking "this photo exists." :func:`app.dependencies.auth.require_user`
    raises 401 and is therefore NOT used here — the handler reads
    ``request.state.user`` directly so the unauth branch can return 404
    without the dependency framework injecting its own status.
    """
    # 1. Auth gate (404 on no session — D-06 existence-leak defense).
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # 2. Filename validation — primary path-traversal defense. The regex
    #    requires 32 lowercase hex chars + optional ``-thumb`` + ``.jpg``;
    #    anything else (``../etc/passwd``, ``foo.png``, ``short.jpg``,
    #    uppercase hex) fails immediately. Single source of truth: the
    #    same regex Plan 04-01 ``process_and_save`` uses when it generates
    #    filenames in the first place.
    if not _is_safe_photo_filename(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # 3. Belt-and-braces: resolve to an absolute path and re-check it
    #    stays inside ``PHOTOS_DIR``. The regex above already restricts
    #    to a flat filename (no separators) so this is defense-in-depth
    #    against a hypothetical future regex regression.
    #
    #    Module-attribute lookup (``_photos_svc.PHOTOS_DIR``) instead of
    #    a frozen import so the Wave-0 ``photo_volume`` test fixture's
    #    monkeypatch is honored — see import comment above.
    photos_dir = _photos_svc.PHOTOS_DIR
    photos_dir_resolved = photos_dir.resolve()
    photo_path = (photos_dir / filename).resolve()
    try:
        photo_path.relative_to(photos_dir_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc

    if not photo_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # 4. Serve with explicit headers per D-06. All saved files are JPEG
    #    (plan 04-01 always re-encodes via ``Image.save(..., "JPEG")``)
    #    so ``image/jpeg`` is correct for both the main and the thumb.
    return FileResponse(
        photo_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


__all__ = ["router", "serve_photo"]
