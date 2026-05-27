"""Photo pipeline: magic-byte verify → Pillow decode + re-encode → EXIF strip → resize → thumb.

Implements SEC-07 (image upload validation) and SEC-4 (polyglot defense)
per Phase 4 ``04-RESEARCH.md`` Pattern 5 + ``04-CONTEXT.md`` D-05..D-08.

CLAUDE.md "Architectural invariants": photo bytes from the browser are
untrusted. This module is the **only** place in the app that decodes
client-supplied image data. Routers (``app/routers/bags.py``,
``app/routers/photos.py`` — plans 04-09, 04-10) consume the primitives
defined here and never call ``PIL.Image`` directly.

Defense-in-depth ordering (matters):

1. **Size pre-check** (``len(raw_bytes) > MAX_BYTES``) — reject before
   doing any work. A 5 MiB cap is the ceiling FastAPI's spool-to-disk
   threshold is also tuned for.
2. **Magic-byte gate** (``_verify_magic_bytes``) — confirms the file
   starts with a JPEG/PNG/WebP signature before Pillow ever sees it.
   Defends against ``Content-Type: image/jpeg`` HTML/PHP polyglots that
   Pillow might otherwise treat as "unknown" (and the serving route
   would mis-sniff into).
3. **Pillow ``verify()`` pass** (T-04-POLY first-line check). ``verify``
   confirms structural validity without decoding pixels and consumes the
   stream — so the function reopens the buffer afterwards (RESEARCH.md
   Pitfall 2).
4. **Re-encode through ``Image.save(format="JPEG")``** (SEC-4) —
   re-encoding strips any trailing bytes the polyglot appended past the
   JPEG ``\\xff\\xd9`` EOI marker.
5. **EXIF strip** — ``Image.save`` with no ``exif=`` kwarg omits EXIF;
   ``image.getexif().clear()`` before save is belt-and-braces (T-04-EXIF).
6. **Pixel-count cap** (``Image.MAX_IMAGE_PIXELS``) — defends against
   decompression bombs (T-04-DOS). Pillow raises
   :class:`PIL.Image.DecompressionBombError` on any image whose product
   exceeds the cap.

Filenames are UUID4 hex (``_is_safe_photo_filename`` regex) so user
input never touches the path (T-04-PHOTO mitigation). The serving route
(plan 04-10) reuses ``_is_safe_photo_filename`` as a defense against
``../etc/passwd`` style path traversal.

``sweep_orphans`` queries BOTH ``bags.photo_filename`` AND
``cafe_logs.photo_filename`` to build the referenced set (Pitfall 8 /
CAFE-02 — sweeping only bags would silently delete every cafe photo).
Order is load-bearing per D-07: list filesystem FIRST, query DB SECOND,
unlink THIRD. Reversing the order would delete a file that a
freshly-inserted row references and produce silent data loss.
RESEARCH.md Pitfall 9 names the footgun.

This module is a primitives module (mirrors ``app/services/encryption.py``).
It does **not** open DB sessions on its own; callers pass a
:class:`sqlalchemy.orm.Session` in to ``sweep_orphans``.
"""

from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

import structlog
from PIL import Image, UnidentifiedImageError

from app.events import CATALOG_PHOTO_ORPHAN_SWEPT

log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Module constants                                                            #
# --------------------------------------------------------------------------- #

#: Filesystem root for processed photos. Mounted from the
#: ``coffee_snobbery_photos`` named volume per ``docker-compose.yml``. Tests
#: monkeypatch this via the ``photo_volume`` fixture.
PHOTOS_DIR = Path("/app/data/photos")

#: Hard cap on input bytes accepted by :func:`process_and_save`. Mirrors the
#: ``Content-Length`` pre-check the router enforces before reading the body.
MAX_BYTES = 5 * 1024 * 1024

#: Pillow decompression-bomb cap. 16 MPx (~2000x2000x4 channels). Pillow
#: raises :class:`PIL.Image.DecompressionBombError` on any image whose
#: pixel product exceeds this. Set process-globally below (Pillow assumption
#: A8 — see ``04-RESEARCH.md``).
MAX_DECODE_PIXELS = 2000 * 2000 * 4

#: Main-image max edge length (in-place ``Image.thumbnail`` is aspect-preserving).
MAIN_MAX_EDGE = 1600

#: Thumbnail max edge length (used for list-view and bag detail summaries).
THUMB_MAX_EDGE = 400

#: JPEG quality for both main + thumb. Quality 85 is the conventional
#: visually-lossless/storage trade-off for re-encoded photos.
JPEG_QUALITY = 85

# Magic-byte signatures. JPEG variants cover JFIF (E0), EXIF (E1),
# Adobe APP14 (EE), and bare quantization-table starts (DB — produced by
# some camera firmwares and by Pillow itself when re-saving stripped JPEGs).
JPEG_MAGICS = (
    b"\xff\xd8\xff\xe0",
    b"\xff\xd8\xff\xe1",
    b"\xff\xd8\xff\xee",
    b"\xff\xd8\xff\xdb",
)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_RIFF = b"RIFF"
WEBP_FOURCC = b"WEBP"

# Path-traversal defense for the serving route (D-06). UUID4 hex is 32
# lowercase chars; the optional ``-thumb`` suffix matches the thumbnail
# pair written by :func:`process_and_save`. No directory separators, no
# control chars, no extensions other than ``.jpg``.
_SAFE_FILENAME_RE = re.compile(r"^[0-9a-f]{32}(-thumb)?\.jpg$")

# Pillow assumption A8: ``Image.MAX_IMAGE_PIXELS`` is a module-level
# attribute on :mod:`PIL.Image`. Setting it once at import is sufficient.
Image.MAX_IMAGE_PIXELS = MAX_DECODE_PIXELS


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class PhotoRejected(Exception):
    """Raised by :func:`process_and_save` on any rejection.

    The router (plan 04-09) catches this and translates to a 200 + form
    fragment (D-04 inline-error pattern). The exception message is shown
    to the user verbatim — keep it short and user-friendly.
    """


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _verify_magic_bytes(head: bytes) -> str:
    """Return ``"jpeg" | "png" | "webp"`` or raise :class:`PhotoRejected`.

    Requires at least 12 bytes (the WebP signature is 12 bytes including
    the RIFF size field + WEBP fourcc). A shorter buffer cannot be a
    valid image and is rejected.
    """
    if len(head) < 12:
        raise PhotoRejected("Unsupported image format")
    if any(head.startswith(m) for m in JPEG_MAGICS):
        return "jpeg"
    if head.startswith(PNG_MAGIC):
        return "png"
    if head.startswith(WEBP_RIFF) and head[8:12] == WEBP_FOURCC:
        return "webp"
    raise PhotoRejected("Unsupported image format")


def _is_safe_photo_filename(name: str) -> bool:
    """Return True iff ``name`` matches the UUID4-hex ``.jpg`` shape.

    Exposed for ``app/routers/photos.py`` (plan 04-10) to reuse as the
    path-traversal defense on the ``/photos/{filename}`` route.
    """
    return bool(_SAFE_FILENAME_RE.match(name))


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def process_and_save(raw_bytes: bytes) -> str:
    """Validate, re-encode, strip EXIF, resize, save main + thumb. Return filename.

    Order matters — see module docstring. Raises :class:`PhotoRejected`
    on any failure (oversize, bad magic, undecodable, decompression
    bomb). Returns the ``{uuid4_hex}.jpg`` filename (without directory)
    so callers store the bare filename in ``bags.photo_filename`` and
    the serving route reconstructs the full path.

    Note on atomicity: D-07 prescribes "write-new-then-delete-old" for
    the replace path. This function does NOT delete an existing file —
    that lives in :func:`replace_photo` below. Direct ``Image.save`` to
    the final filename is acceptable here because the filename is a
    fresh UUID; no collision is possible and a mid-write crash leaves a
    partially-written file unreferenced by any DB row (which the orphan
    sweep then collects).
    """
    # Step 1: size pre-check
    if len(raw_bytes) > MAX_BYTES:
        raise PhotoRejected("Photo too large (max 5MB).")

    # Step 2: magic-byte gate (catches HTML/PHP-as-image polyglots
    # before Pillow allocates any memory for them).
    _verify_magic_bytes(raw_bytes[:12])

    # Ensure storage directory exists (cheap; idempotent).
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 3: structural verify pass. ``verify()`` consumes the stream,
    # so a separate ``Image.open`` below is required (Pillow Pitfall 2).
    # Wrap ``DecompressionBombError`` explicitly so the user-facing
    # message stays friendly; the bare ``Exception`` branch catches
    # ``UnidentifiedImageError`` and any odd codec-internal failure.
    try:
        with Image.open(io.BytesIO(raw_bytes)) as probe:
            probe.verify()
    except Image.DecompressionBombError as exc:
        log.warning("photo.decode_failed", error_class=type(exc).__name__)
        raise PhotoRejected("Photo dimensions too large.") from exc
    except (UnidentifiedImageError, Exception) as exc:
        log.warning("photo.decode_failed", error_class=type(exc).__name__)
        raise PhotoRejected("We couldn't read this image. Try a JPEG, PNG, or WebP.") from exc

    # Step 4: re-open + load (verify() invalidated the previous handle).
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except Image.DecompressionBombError as exc:
        log.warning("photo.decode_failed", error_class=type(exc).__name__)
        raise PhotoRejected("Photo dimensions too large.") from exc
    except (UnidentifiedImageError, Exception) as exc:
        log.warning("photo.decode_failed", error_class=type(exc).__name__)
        raise PhotoRejected("We couldn't read this image. Try a JPEG, PNG, or WebP.") from exc

    # Step 5: belt-and-braces EXIF strip. The primary defense is the
    # ``Image.save`` call below WITHOUT the ``exif=`` kwarg (Pillow
    # writes no EXIF segment in that mode). Clearing the in-memory
    # ``getexif()`` dict here is the second layer.
    try:
        image.getexif().clear()
    except Exception:  # noqa: BLE001, S110 — not all formats expose getexif()
        pass

    # Step 6: normalize mode. PNG with alpha + WebP often come in as
    # ``RGBA`` / ``P``; converting to RGB lets JPEG encode them safely
    # (JPEG cannot store an alpha channel).
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Step 7: main in-place resize. LANCZOS is the canonical
    # high-quality downscale resampler.
    image.thumbnail((MAIN_MAX_EDGE, MAIN_MAX_EDGE), Image.Resampling.LANCZOS)

    # Step 8: save main. NO ``exif=`` kwarg → no EXIF segment written.
    filename_uuid = uuid.uuid4().hex
    main_path = PHOTOS_DIR / f"{filename_uuid}.jpg"
    image.save(main_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    # Step 9: thumbnail derived from the (already downsized) main image.
    thumb = image.copy()
    thumb.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE), Image.Resampling.LANCZOS)
    thumb_path = PHOTOS_DIR / f"{filename_uuid}-thumb.jpg"
    thumb.save(thumb_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    # Step 10: return the canonical filename. Callers persist it on
    # ``bags.photo_filename``; the serving route reconstructs the path.
    return f"{filename_uuid}.jpg"


def replace_photo(old_filename: str | None, new_filename: str) -> None:
    """Write-new-then-delete-old: unlink the OLD file pair.

    The NEW file is already on disk (returned by :func:`process_and_save`);
    this helper exists so the router can update the DB row first and THEN
    unlink the old file, guaranteeing the DB never points at a missing
    file even if the unlink fails (D-07 ordering).

    No-op when ``old_filename`` is ``None`` (first photo for this bag).
    Logs warnings on :class:`OSError` but never raises — a failed unlink
    leaves an orphan that the nightly sweep collects.
    """
    if old_filename is None:
        return
    stem = old_filename.removesuffix(".jpg")
    for path in (
        PHOTOS_DIR / f"{stem}.jpg",
        PHOTOS_DIR / f"{stem}-thumb.jpg",
    ):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning(
                "photos.unlink_failed",
                path=str(path),
                error_class=type(exc).__name__,
            )
    _ = new_filename  # accepted for API symmetry; nothing to do with it


def unlink_safe(filename: str | None) -> None:
    """Idempotent removal of ``{stem}.jpg`` + ``{stem}-thumb.jpg``.

    Used by bag hard-delete (plan 04-09) and as the inner loop of
    :func:`sweep_orphans`. ``filename=None`` is a no-op (bag never had
    a photo). Missing files are tolerated via ``missing_ok=True``.
    """
    if filename is None:
        return
    stem = filename.removesuffix(".jpg")
    for path in (
        PHOTOS_DIR / f"{stem}.jpg",
        PHOTOS_DIR / f"{stem}-thumb.jpg",
    ):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning(
                "photos.unlink_failed",
                path=str(path),
                error_class=type(exc).__name__,
            )


def _sweep_unreferenced(on_disk: set[str], referenced_main_filenames: set[str]) -> int:
    """Pure diff + unlink helper used by :func:`sweep_orphans`.

    Split out so plan 04-01 tests can exercise the FS-first / unlink
    logic without depending on ``bags.photo_filename`` (added in plan
    04-03). Expands each referenced ``{uuid}.jpg`` filename to also keep
    the paired ``{uuid}-thumb.jpg``.

    Returns the count of unlinked files (main + thumb counted
    separately). Logs but never raises on a failed unlink — a permission
    or transient FS error leaves the orphan in place for the next sweep.
    """
    referenced: set[str] = set()
    for fn in referenced_main_filenames:
        if fn is None:
            continue
        referenced.add(fn)
        stem = fn.removesuffix(".jpg")
        referenced.add(f"{stem}-thumb.jpg")

    orphans = on_disk - referenced
    count = 0
    for name in orphans:
        try:
            (PHOTOS_DIR / name).unlink()
            count += 1
        except OSError as exc:
            log.warning(
                "photos.sweep_unlink_failed",
                name=name,
                error_class=type(exc).__name__,
            )
    return count


def sweep_orphans(db) -> int:  # type: ignore[no-untyped-def]
    """Diff filesystem against referenced photo filenames; unlink unreferenced files.

    Queries BOTH ``bags.photo_filename`` AND ``cafe_logs.photo_filename``
    (Pitfall 8 / CAFE-02: union bags and cafe refs — silent data loss otherwise).

    STRICT ordering per D-07 / RESEARCH.md Pitfall 9:

    1. Snapshot the filesystem FIRST (``on_disk``).
    2. Query ``bags.photo_filename`` + ``cafe_logs.photo_filename`` SECOND.
    3. Unlink the DIFF THIRD (delegated to :func:`_sweep_unreferenced`).

    Doing it in reverse (unlinking files referenced by a freshly-inserted
    row) is the load-bearing footgun. The order is not negotiable.

    Returns the count of files unlinked (main + thumb counted
    separately). Returns 0 when the photos directory does not yet exist
    (first run before any upload). Emits ``CATALOG_PHOTO_ORPHAN_SWEPT``
    at INFO with the count for operator-facing visibility.

    The ``db`` parameter is a :class:`sqlalchemy.orm.Session`; typed as
    ``Any`` in the signature to avoid an import-time dependency on
    SQLAlchemy (this module is otherwise pure Pillow + stdlib + structlog).
    """
    if not PHOTOS_DIR.exists():
        log.info(CATALOG_PHOTO_ORPHAN_SWEPT, count=0, total_on_disk=0)
        return 0

    # Step 1: snapshot filesystem first.
    on_disk: set[str] = {p.name for p in PHOTOS_DIR.iterdir() if p.is_file() and p.suffix == ".jpg"}

    # Step 2: query DB second. Lazy-import to keep the module's import
    # graph minimal (mirrors ``app/dependencies/db.py`` pattern) and to
    # defer attribute lookups until call time.
    from sqlalchemy import select

    from app.models.bag import Bag
    from app.models.cafe_log import CafeLog  # Pitfall 8 / CAFE-02: cafe photos must survive sweep

    bag_rows = db.execute(select(Bag.photo_filename).where(Bag.photo_filename.isnot(None))).all()
    cafe_rows = db.execute(
        select(CafeLog.photo_filename).where(CafeLog.photo_filename.isnot(None))
    ).all()
    referenced_main: set[str] = {fn for (fn,) in bag_rows if fn is not None}
    referenced_main |= {fn for (fn,) in cafe_rows if fn is not None}

    # Step 3: unlink the diff.
    count = _sweep_unreferenced(on_disk, referenced_main)

    log.info(
        CATALOG_PHOTO_ORPHAN_SWEPT,
        count=count,
        total_on_disk=len(on_disk),
    )
    return count
