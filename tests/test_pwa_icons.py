"""GAP 1 — C10 icon structural regression (Phase 13, Plan 13-02).

Two assertions:
  (a) Committed icon dimensions via Pillow — pure, no app deps, must NOT skip.
  (b) Manifest icon-reference integrity via TestClient: every icon src in
      GET /manifest.json (after stripping the ?v=... cache-bust query) resolves
      to an existing file under app/static/.

The Pillow test is dependency-free (Pillow is an app dep, always available in
the baked image) and has no reason to skip. The manifest test uses the
TestClient `client` fixture and may skip only when the source-tree is missing
Tailwind CSS (app.main import fails without it) — in the baked image it passes.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest

# ---------------------------------------------------------------------------
# (a) Pillow dimension assertions — pure, no app deps, must NOT skip
# ---------------------------------------------------------------------------

# Repo root is the pytest working directory (pyproject.toml is there).
_STATIC_IMG = Path("app/static/img")

_EXPECTED_DIMENSIONS: dict[str, tuple[int, int]] = {
    "icon-192.png": (192, 192),
    "icon-512.png": (512, 512),
    "icon-512-maskable.png": (512, 512),
    "apple-touch-icon.png": (180, 180),
    "logo-badge.png": (64, 64),
}


@pytest.mark.parametrize("filename,expected_size", list(_EXPECTED_DIMENSIONS.items()))
def test_icon_dimensions(filename: str, expected_size: tuple[int, int]) -> None:
    """Each committed PWA icon file has the correct pixel dimensions (C10).

    Uses Pillow (an app dependency, always installed in the baked image).
    Must NOT skip — Pillow has no external runtime dependency here and the
    icon files are checked in to the repo.
    """
    from PIL import Image

    icon_path = _STATIC_IMG / filename
    assert icon_path.exists(), (
        f"Icon file missing: {icon_path}. "
        "All 5 PWA icons must be committed to app/static/img/ (C10)."
    )
    with Image.open(icon_path) as img:
        actual_size = img.size  # (width, height)
    assert actual_size == expected_size, (
        f"{filename}: expected dimensions {expected_size[0]}x{expected_size[1]}, "
        f"got {actual_size[0]}x{actual_size[1]}. "
        "Icon must be regenerated at the correct size (C10 / Plan 13-02)."
    )


# ---------------------------------------------------------------------------
# (b) Manifest icon-reference integrity via TestClient
# ---------------------------------------------------------------------------


def test_manifest_icon_refs_resolve_to_existing_files(client: object) -> None:
    """Every icon src in GET /manifest.json resolves to an existing file (C10).

    Strips the ?v=... cache-bust query before resolving. The 4 manifest icons
    are icon-192, icon-512, icon-512-maskable, and apple-touch-icon.
    logo-badge.png is template-only and is NOT in the manifest.

    Uses the TestClient `client` fixture from conftest.py. In a source-tree
    run without Tailwind CSS the app fixture skips — that is acceptable. In
    the baked image this test must pass.
    """
    from fastapi.testclient import TestClient

    assert isinstance(client, TestClient), "client fixture did not yield a TestClient"

    r = client.get("/manifest.json")
    assert r.status_code == 200, f"GET /manifest.json returned {r.status_code}; expected 200."

    body = r.json()
    icons = body.get("icons", [])
    assert icons, "Manifest has no icons array — cannot verify icon references."

    # Collect all src values from the manifest icons list.
    missing: list[str] = []
    for icon in icons:
        src: str = icon.get("src", "")
        # Strip the query string (?v=...) to get the bare path.
        parsed = urlparse(src)
        bare_path = parsed.path  # e.g. /static/img/icon-192.png

        # Map /static/... → app/static/...
        if bare_path.startswith("/static/"):
            file_path = Path("app") / bare_path.lstrip("/")
        elif bare_path.startswith("/"):
            file_path = Path("app") / bare_path.lstrip("/")
        else:
            file_path = Path(bare_path)

        if not file_path.exists():
            missing.append(f"{src!r} → {file_path} (does not exist)")

    assert not missing, (
        "The following manifest icon src references point to missing files:\n"
        + "\n".join(f"  {m}" for m in missing)
        + "\nAll icon hrefs must resolve to committed files under app/static/ (C10)."
    )
