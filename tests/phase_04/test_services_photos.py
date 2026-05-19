"""Real tests for ``app.services.photos`` (plan 04-01 Task 2).

Covers the per-task verification map rows 04-01-01 through 04-01-05 in
``.planning/phases/04-shared-catalog/04-VALIDATION.md`` and the threat
register entries T-04-PHOTO, T-04-EXIF, T-04-POLY, T-04-DOS in the
plan's ``<threat_model>``:

- ``test_magic_byte_reject``           — T-04-POLY (early gate)
- ``test_exif_strip``                  — T-04-EXIF
- ``test_polyglot_strip``              — T-04-POLY (re-encode defense)
- ``test_size_reject``                 — T-04-DOS (size cap)
- ``test_decompression_bomb_rejected`` — T-04-DOS (pixel cap)
- ``test_jpeg_round_trip``             — happy path
- ``test_replace_unlinks_old``         — D-07 write-new-then-delete-old
- ``test_sweep_orphans``               — D-07 FS-first / DB-second / unlink-third
- ``test_safe_filename_regex``         — T-04-PHOTO path-traversal defense

The ``sweep_orphans`` test uses a hand-rolled fake session because the
``bags.photo_filename`` column is not added until plan 04-03 (Wave 2).
The fake exercises the in-memory diff and unlink logic — the SQL query
itself is one-line and trivially correct against the real model once it
exists.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

import pytest
from PIL import Image


def _require_photos_service() -> None:
    """Skip cleanly if the photos module hasn't shipped (Task 1 ordering)."""
    try:
        from app.services import photos  # noqa: F401
    except ImportError:
        pytest.skip("plan 04-01 Task 2 dependency: app.services.photos")


# --------------------------------------------------------------------------- #
# Magic-byte gate (T-04-POLY first line)                                      #
# --------------------------------------------------------------------------- #


def test_magic_byte_reject(photo_volume: Path, bad_magic_jpeg: bytes) -> None:
    """HTML/PHP bytes with a ``.jpg`` extension are rejected before Pillow."""
    _require_photos_service()
    from app.services.photos import PhotoRejected, process_and_save

    with pytest.raises(PhotoRejected) as excinfo:
        process_and_save(bad_magic_jpeg)
    assert "Unsupported" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# EXIF strip (T-04-EXIF)                                                      #
# --------------------------------------------------------------------------- #


def test_exif_strip(photo_volume: Path, exif_jpeg: Callable[..., bytes]) -> None:
    """Saved file's EXIF dict is empty after the re-encode."""
    _require_photos_service()
    from app.services.photos import process_and_save

    filename = process_and_save(exif_jpeg())
    saved = photo_volume / filename
    assert saved.exists(), "main photo not written"

    with Image.open(saved) as img:
        # ``getexif()`` returns an empty Exif dict when no EXIF segment
        # is present. Different Pillow paths surface emptiness as either
        # ``len(...) == 0`` or a falsy Exif object — both are accepted.
        exif = img.getexif()
        assert not exif or len(exif) == 0, (
            f"EXIF leaked into saved photo: {dict(exif)!r}"
        )


# --------------------------------------------------------------------------- #
# Polyglot strip (T-04-POLY second line — re-encode)                          #
# --------------------------------------------------------------------------- #


def test_polyglot_strip(photo_volume: Path, polyglot_jpeg: bytes) -> None:
    """Trailing ``<?php ...`` past the EOI marker is stripped by re-encode."""
    _require_photos_service()
    from app.services.photos import process_and_save

    filename = process_and_save(polyglot_jpeg)
    saved = photo_volume / filename
    raw = saved.read_bytes()

    assert b"<?php" not in raw, "polyglot trailer survived re-encode"
    assert raw.endswith(b"\xff\xd9"), (
        "saved file does not end with JPEG EOI marker — re-encode may be incomplete"
    )


# --------------------------------------------------------------------------- #
# Size cap (T-04-DOS)                                                         #
# --------------------------------------------------------------------------- #


def test_size_reject(photo_volume: Path) -> None:
    """Payload larger than MAX_BYTES raises before any decode work."""
    _require_photos_service()
    from app.services.photos import MAX_BYTES, PhotoRejected, process_and_save

    oversized = b"\xff\xd8\xff\xe0" + b"\x00" * (MAX_BYTES + 1 - 4)
    with pytest.raises(PhotoRejected) as excinfo:
        process_and_save(oversized)
    assert "too large" in str(excinfo.value).lower()


# --------------------------------------------------------------------------- #
# Decompression-bomb cap (T-04-DOS pixel cap)                                 #
# --------------------------------------------------------------------------- #


def test_decompression_bomb_rejected(
    photo_volume: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_jpeg: Callable[..., bytes],
) -> None:
    """Pillow's pixel cap raises and the function translates to PhotoRejected."""
    _require_photos_service()
    from app.services import photos as photos_mod
    from app.services.photos import PhotoRejected, process_and_save

    # Drop the cap below the 200x200 = 40_000 pixel fixture so the next
    # decode attempt trips it. Cap is reset by monkeypatch teardown.
    monkeypatch.setattr(photos_mod.Image, "MAX_IMAGE_PIXELS", 100)

    payload = synthetic_jpeg(dimensions=(200, 200))
    with pytest.raises(PhotoRejected) as excinfo:
        process_and_save(payload)
    # User-facing message is "Photo dimensions too large." — accept any
    # variant that mentions either dimensions or that it's too large.
    msg = str(excinfo.value).lower()
    assert "too large" in msg or "dimensions" in msg


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #


def test_jpeg_round_trip(
    photo_volume: Path, synthetic_jpeg: Callable[..., bytes]
) -> None:
    """Valid JPEG produces a UUID-named main + thumb pair on disk."""
    _require_photos_service()
    from app.services.photos import process_and_save

    filename = process_and_save(synthetic_jpeg())
    assert filename.endswith(".jpg")
    stem = filename.removesuffix(".jpg")
    main = photo_volume / filename
    thumb = photo_volume / f"{stem}-thumb.jpg"

    assert main.exists(), "main file missing"
    assert thumb.exists(), "thumb file missing"

    # Both must decode as valid JPEGs.
    with Image.open(main) as img:
        img.verify()
        assert img.format == "JPEG"
    with Image.open(thumb) as t:
        t.verify()
        assert t.format == "JPEG"


# --------------------------------------------------------------------------- #
# replace_photo (D-07 write-new-then-delete-old)                              #
# --------------------------------------------------------------------------- #


def test_replace_unlinks_old(
    photo_volume: Path, synthetic_jpeg: Callable[..., bytes]
) -> None:
    """``replace_photo(old, new)`` unlinks both old files; new pair survives."""
    _require_photos_service()
    from app.services.photos import process_and_save, replace_photo

    old_filename = process_and_save(synthetic_jpeg(dimensions=(400, 300)))
    new_filename = process_and_save(synthetic_jpeg(dimensions=(500, 400)))
    assert old_filename != new_filename

    old_stem = old_filename.removesuffix(".jpg")
    new_stem = new_filename.removesuffix(".jpg")
    old_main = photo_volume / old_filename
    old_thumb = photo_volume / f"{old_stem}-thumb.jpg"
    new_main = photo_volume / new_filename
    new_thumb = photo_volume / f"{new_stem}-thumb.jpg"

    # Pre-condition: both pairs on disk.
    for p in (old_main, old_thumb, new_main, new_thumb):
        assert p.exists(), f"missing pre-condition: {p}"

    replace_photo(old_filename, new_filename)

    assert not old_main.exists(), "old main not unlinked"
    assert not old_thumb.exists(), "old thumb not unlinked"
    assert new_main.exists(), "new main was clobbered"
    assert new_thumb.exists(), "new thumb was clobbered"


def test_replace_photo_with_none_is_noop(
    photo_volume: Path, synthetic_jpeg: Callable[..., bytes]
) -> None:
    """``replace_photo(None, new)`` leaves the new pair intact (first upload path)."""
    _require_photos_service()
    from app.services.photos import process_and_save, replace_photo

    new_filename = process_and_save(synthetic_jpeg())
    new_stem = new_filename.removesuffix(".jpg")
    replace_photo(None, new_filename)
    assert (photo_volume / new_filename).exists()
    assert (photo_volume / f"{new_stem}-thumb.jpg").exists()


# --------------------------------------------------------------------------- #
# sweep_orphans (D-07 FS-first / DB-second / unlink-third)                    #
# --------------------------------------------------------------------------- #
#
# The DB-aware ``sweep_orphans`` function depends on ``Bag.photo_filename``
# (added in plan 04-03). Until then, the load-bearing diff/unlink logic
# is exercised via the internal ``_sweep_unreferenced`` helper. Plan
# 04-03 lands a ``sweep_orphans`` integration test in ``test_migration.py``
# once the column exists.


def test_sweep_orphans(
    photo_volume: Path, synthetic_jpeg: Callable[..., bytes]
) -> None:
    """Files not referenced are unlinked; referenced files survive.

    Calls the internal ``_sweep_unreferenced`` helper because the
    DB-aware ``sweep_orphans`` wrapper depends on ``Bag.photo_filename``
    which plan 04-03 adds. The wrapper is a 3-line shim around the
    helper plus a one-line ``select(...)`` — both trivially correct
    once the column exists.
    """
    _require_photos_service()
    from app.services.photos import (
        _sweep_unreferenced,
        process_and_save,
    )

    # Create three full pairs on disk.
    kept_filename = process_and_save(synthetic_jpeg(dimensions=(300, 200)))
    orphan1 = process_and_save(synthetic_jpeg(dimensions=(310, 210)))
    orphan2 = process_and_save(synthetic_jpeg(dimensions=(320, 220)))

    # Sanity: 6 files on disk (3 main + 3 thumb).
    on_disk_before = {p.name for p in photo_volume.iterdir()}
    assert len(on_disk_before) == 6

    # Snapshot FS first (matches the strict ordering inside sweep_orphans).
    on_disk = {p.name for p in photo_volume.iterdir() if p.suffix == ".jpg"}

    # Referenced set: only the first photo (and its implicit thumb).
    count = _sweep_unreferenced(on_disk, referenced_main_filenames={kept_filename})

    assert count == 4, "expected 4 unlinks (2 orphan pairs = 2 main + 2 thumb)"

    # Kept pair survives; orphan pairs gone.
    kept_stem = kept_filename.removesuffix(".jpg")
    assert (photo_volume / kept_filename).exists()
    assert (photo_volume / f"{kept_stem}-thumb.jpg").exists()
    for orphan in (orphan1, orphan2):
        stem = orphan.removesuffix(".jpg")
        assert not (photo_volume / orphan).exists()
        assert not (photo_volume / f"{stem}-thumb.jpg").exists()


def test_sweep_orphans_empty_dir(photo_volume: Path) -> None:
    """Empty filesystem snapshot + empty referenced set returns 0 cleanly."""
    _require_photos_service()
    from app.services.photos import _sweep_unreferenced

    assert _sweep_unreferenced(on_disk=set(), referenced_main_filenames=set()) == 0


def test_sweep_orphans_top_level_skips_when_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``sweep_orphans()`` returns 0 cleanly when the photos dir doesn't exist.

    Exercises the DB-aware wrapper's early-return branch (the only path
    in the wrapper that doesn't depend on ``Bag.photo_filename``, which
    plan 04-03 adds). Full DB-coupled integration coverage lands in plan
    04-03 once the column exists.
    """
    _require_photos_service()
    from app.services import photos as photos_mod
    from app.services.photos import sweep_orphans

    nonexistent = tmp_path / "does-not-exist"
    monkeypatch.setattr(photos_mod, "PHOTOS_DIR", nonexistent)

    # ``db`` is never reached on the missing-dir branch — pass None.
    assert sweep_orphans(db=None) == 0


# --------------------------------------------------------------------------- #
# _is_safe_photo_filename (T-04-PHOTO path-traversal defense)                 #
# --------------------------------------------------------------------------- #


def test_safe_filename_regex() -> None:
    """Regex accepts UUID-hex .jpg names; rejects traversal / wrong-ext probes."""
    _require_photos_service()
    from app.services.photos import _is_safe_photo_filename

    # Accept: 32 lowercase hex chars + .jpg, with optional -thumb.
    assert _is_safe_photo_filename("a1b2c3d4e5f60718293a4b5c6d7e8f90.jpg")
    assert _is_safe_photo_filename("a1b2c3d4e5f60718293a4b5c6d7e8f90-thumb.jpg")

    # Reject: path traversal, wrong extension, too short, uppercase hex.
    assert not _is_safe_photo_filename("../etc/passwd")
    assert not _is_safe_photo_filename("deadbeef.png")
    assert not _is_safe_photo_filename("123.jpg")
    assert not _is_safe_photo_filename("A1B2C3D4E5F60718293A4B5C6D7E8F90.jpg")
    assert not _is_safe_photo_filename("a1b2c3d4e5f60718293a4b5c6d7e8f90.png")
    assert not _is_safe_photo_filename("")
    assert not _is_safe_photo_filename(
        "a1b2c3d4e5f60718293a4b5c6d7e8f90/../passwd.jpg"
    )


# --------------------------------------------------------------------------- #
# Unused-import guard — keep io + BytesIO imported so test isolation passes   #
# --------------------------------------------------------------------------- #
_ = io.BytesIO  # imported above for future tests; assigning silences unused-import
