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
    assert body["name"] == "Snobbery — Coffee Log", (
        f"Manifest name mismatch: {body.get('name')!r}"
    )
    assert body["short_name"] == "Snobbery", (
        f"Manifest short_name mismatch: {body.get('short_name')!r}"
    )
    assert body["description"] == "Self-hosted coffee log for households who take pour-over seriously", (
        f"Manifest description mismatch: {body.get('description')!r}"
    )
    assert body["display"] == "standalone", (
        f"Manifest display mismatch: {body.get('display')!r}"
    )
    assert body["start_url"] == "/?source=pwa", (
        f"Manifest start_url mismatch: {body.get('start_url')!r}"
    )

    icons = body.get("icons", [])
    maskable = [i for i in icons if i.get("purpose") == "maskable"]
    assert maskable, "Manifest must have at least one icon with purpose == 'maskable'"
    assert any(i.get("sizes") == "512x512" for i in maskable), (
        "Maskable icon must be 512x512"
    )


def test_sw_headers(client) -> None:
    """GET /sw.js returns 200 with Service-Worker-Allowed: / and Cache-Control: no-cache."""
    r = client.get("/sw.js")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    swa = r.headers.get("service-worker-allowed", "")
    assert swa == "/", (
        f"Expected Service-Worker-Allowed: /, got: {swa!r}"
    )

    cc = r.headers.get("cache-control", "")
    assert cc == "no-cache", (
        f"Expected Cache-Control: no-cache, got: {cc!r}"
    )

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
