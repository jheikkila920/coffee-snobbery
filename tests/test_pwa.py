"""PWA installability smoke tests (Phase 11, Plan 01).

Tests three Wave 0 requirements:
  - MOB-09: GET /manifest.json returns 200 with locked UX-02 strings.
  - MOB-10: GET /sw.js returns 200 with Service-Worker-Allowed: / and Cache-Control: no-cache.
  - test_start_url_returns_200: authenticated GET /?source=pwa returns 200.

These tests are intentionally RED before Tasks 2-3 of Plan 11-01 land.
Do NOT use pytest.skip to mask missing routes — skip-as-green is a verification gap.
"""

from __future__ import annotations

import re


def test_manifest_200(client) -> None:
    """GET /manifest.json returns 200 with correct Content-Type and locked UX-02 strings."""
    r = client.get("/manifest.json")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    content_type = r.headers.get("content-type", "")
    assert "application/manifest+json" in content_type, (
        f"Expected Content-Type application/manifest+json, got: {content_type!r}"
    )

    body = r.json()
    assert body["name"] == "Snobbery — Coffee Log", f"Manifest name mismatch: {body.get('name')!r}"
    assert body["short_name"] == "Snobbery", (
        f"Manifest short_name mismatch: {body.get('short_name')!r}"
    )
    assert (
        body["description"] == "Self-hosted coffee log for households who take pour-over seriously"
    ), f"Manifest description mismatch: {body.get('description')!r}"
    assert body["display"] == "standalone", f"Manifest display mismatch: {body.get('display')!r}"
    assert body["start_url"] == "/?source=pwa", (
        f"Manifest start_url mismatch: {body.get('start_url')!r}"
    )

    icons = body.get("icons", [])
    maskable = [i for i in icons if i.get("purpose") == "maskable"]
    assert maskable, "Manifest must have at least one icon with purpose == 'maskable'"
    assert any(i.get("sizes") == "512x512" for i in maskable), "Maskable icon must be 512x512"


def test_sw_headers(client) -> None:
    """GET /sw.js returns 200 with Service-Worker-Allowed: / and Cache-Control: no-cache."""
    r = client.get("/sw.js")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    swa = r.headers.get("service-worker-allowed", "")
    assert swa == "/", f"Expected Service-Worker-Allowed: /, got: {swa!r}"

    cc = r.headers.get("cache-control", "")
    assert cc == "no-cache", f"Expected Cache-Control: no-cache, got: {cc!r}"

    content_type = r.headers.get("content-type", "")
    assert re.search(r"javascript|text/js", content_type), (
        f"Expected a JavaScript Content-Type, got: {content_type!r}"
    )


def test_start_url_returns_200(client, seeded_regular_user) -> None:
    """Authenticated GET /?source=pwa returns 200 (not a redirect)."""
    signed_cookie = seeded_regular_user["signed_cookie"]
    # Get a CSRF token first so the cookie jar is populated.
    r_login = client.get("/login")
    csrf_token = r_login.cookies.get("csrftoken", "")

    r = client.get(
        "/?source=pwa",
        cookies={"session_id": signed_cookie, "csrftoken": csrf_token},
        follow_redirects=False,
    )
    assert r.status_code == 200, (
        f"Authenticated GET /?source=pwa must return 200; got {r.status_code}. "
        "The home route must pass through query params without redirecting."
    )


def test_manifest_link_in_head(client) -> None:
    """GET /login renders <link rel="manifest"> in <head> unconditionally (MOB-12).

    This is a regression test for the Phase 11 verification gap: base.html was
    missing PWA discovery tags, breaking browser installability (MOB-12 / ROADMAP
    SC#1).  The fix (lines 16-20 of base.html) must be present on every page,
    including the anonymous /login page — so no auth fixture is needed.
    """
    r = client.get("/login")
    assert r.status_code == 200, f"Expected 200 from /login, got {r.status_code}"
    assert '<link rel="manifest" href="/manifest.json">' in r.text, (
        'base.html must include <link rel="manifest" href="/manifest.json"> '
        "unconditionally so browsers can discover the PWA manifest (MOB-12). "
        f"Tag not found in /login response. Head excerpt:\n{r.text[:500]}"
    )


def test_apple_touch_icon_and_web_app_meta_in_head(client) -> None:
    """GET /login renders apple-touch-icon + apple-mobile-web-app-* meta tags (MOB-11).

    Regression test for Phase 11 verification gap: iOS Safari requires these tags
    for Add-to-Home-Screen standalone launch behaviour (MOB-11).  They live in
    base.html outside the auth gate and must be present on every page.
    """
    r = client.get("/login")
    assert r.status_code == 200, f"Expected 200 from /login, got {r.status_code}"
    assert 'rel="apple-touch-icon"' in r.text, (
        'base.html must include <link rel="apple-touch-icon"> for iOS Home Screen '
        "install (MOB-11). Tag not found in /login response."
    )
    assert "apple-mobile-web-app-capable" in r.text, (
        'base.html must include <meta name="apple-mobile-web-app-capable"> for iOS '
        "standalone mode (MOB-11). Meta tag not found in /login response."
    )
    assert "apple-mobile-web-app-title" in r.text, (
        'base.html must include <meta name="apple-mobile-web-app-title"> for the '
        "iOS Home Screen label (MOB-11). Meta tag not found in /login response."
    )
    assert "apple-mobile-web-app-status-bar-style" in r.text, (
        'base.html must include <meta name="apple-mobile-web-app-status-bar-style"> '
        "for iOS status bar appearance (MOB-11). Meta tag not found in /login response."
    )


# --- Phase 13, Plan 01: C9 cache-versioning regression tests -------------------


def test_sw_cache_name_is_versioned(client) -> None:
    """GET /sw.js body contains a snobbery-v<hash> CACHE_NAME token (C9).

    Asserts only the structural shape (snobbery-v followed by alphanumeric chars)
    so the test is green in both:
      - source-tree / CI runs where no compiled tailwind.*.css and no build_id.txt
        exist (hash falls back to "dev" → CACHE_NAME = "snobbery-vdev"), and
      - baked-image runs where a real timestamp or CSS hash is present.

    This is a regression guard: if the __BUILD_HASH__ token is ever left
    un-substituted or the CACHE_NAME prefix changes, this test catches it.
    Do NOT use pytest.skip here — skip-as-green is a verification gap
    (memory: tests-pass-by-skip-mask-green).
    """
    r = client.get("/sw.js")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
    match = re.search(r"snobbery-v([A-Za-z0-9]+)", r.text)
    assert match is not None, (
        "GET /sw.js body must contain a CACHE_NAME matching 'snobbery-v<alphanum>'. "
        f"Body excerpt: {r.text[:300]}"
    )
    assert match.group(1), (
        f"The hash segment after 'snobbery-v' must be non-empty. Got: {match.group(0)!r}"
    )


def test_build_hash_prefers_build_id_txt(tmp_path, monkeypatch) -> None:
    """_get_build_hash() returns build_id.txt content (truncated to 16 chars) when present (C9).

    This is the RED test for Task 1 — it fails until Task 2 rewrites
    _get_build_hash() to prefer build_id.txt over the CSS-filename hash.

    Uses a real temp file under app/static/build_id.txt (the production path)
    so the test exercises the exact Path the implementation will read.
    Cleans up in a finally block to leave no stray artifact in the source tree.
    """
    import importlib
    from pathlib import Path

    build_id_path = Path("app/static/build_id.txt")
    test_content = "20260524120000"
    created = False
    try:
        build_id_path.write_text(test_content, encoding="utf-8")
        created = True

        # Re-import to get a fresh call — the module-level _BUILD_HASH is
        # computed at import time, so we call the function directly.
        import app.routers.pwa as pwa_module

        importlib.reload(pwa_module)
        result = pwa_module._get_build_hash()

        assert result == test_content[:16], (
            f"_get_build_hash() must return build_id.txt content (truncated to 16 chars) "
            f"when the file is present. Expected {test_content[:16]!r}, got {result!r}. "
            "Task 2 (pwa.py rewrite) has not landed yet — this is expected RED."
        )
    finally:
        if created and build_id_path.exists():
            build_id_path.unlink()
