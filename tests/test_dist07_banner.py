"""Phase 17 Plan 03 DIST-07 banner tests.

Asserts the admin AI-key-setup banner (D-19):

    1. Admin with no resolvable AI key sees the banner on GET /
       (contains ``bannerDismiss`` Alpine binding, the ``/admin/credentials``
       button, and the ``Welcome — add your AI API key`` headline).
    2. Admin with at least one resolvable AI key does NOT see the banner.
    3. Non-admin never sees the banner — neither with nor without a key.
    4. ``base.html`` registers ``banner-dismiss.js`` as a defer script with
       a CSP nonce attribute (Alpine CSP-build constraint).
    5. The banner's "Go to Admin" button targets ``/admin/credentials`` —
       not ``/admin`` (research A3).

Seed strategy: monkeypatches ``credentials_service.get_provider_credential``
on the home router module to return ``None`` (no key) or a sentinel object
(has key). This sidesteps the Fernet round-trip — encryption coverage lives
in tests/services/test_credentials.py. Same pattern documented in 17-03 plan
``<interfaces>`` so plan 17-04's AIX-08 tests reuse it.
"""

from __future__ import annotations

from typing import Any

import pytest


def _require_nav_wired() -> None:
    """Skip if any Phase 11 Plan 03 dependency is missing."""
    try:
        from app.routers.config_hub import router  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"config_hub router not wired: {exc}")


def _patch_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the home router's credentials helper to return None for
    every provider — simulates the "no AI key configured" state."""
    from app.routers import home as home_router

    monkeypatch.setattr(
        home_router.credentials_service,
        "get_provider_credential",
        lambda _db, _provider: None,
    )


def _patch_with_key(monkeypatch: pytest.MonkeyPatch, *, provider: str = "anthropic") -> None:
    """Monkeypatch the home router's credentials helper to return a sentinel
    object for ``provider`` and None otherwise — simulates the "has key" state."""
    from app.routers import home as home_router

    sentinel = object()

    def fake(_db: Any, p: str) -> Any:
        return sentinel if p == provider else None

    monkeypatch.setattr(home_router.credentials_service, "get_provider_credential", fake)


def test_home_shows_dist07_banner_for_admin_with_no_key(
    client,
    seeded_admin_user,
    monkeypatch,
) -> None:
    """Admin with no AI key configured sees the DIST-07 banner on GET /."""
    _require_nav_wired()
    _patch_no_key(monkeypatch)
    signed_cookie = seeded_admin_user["signed_cookie"]

    r = client.get("/", cookies={"session_id": signed_cookie})

    assert r.status_code == 200, (
        f"GET / must return 200 for admin; got {r.status_code}: {r.text[:300]}"
    )
    assert "bannerDismiss" in r.text, (
        "Banner Alpine binding (x-data='bannerDismiss') missing from admin+no-key home page"
    )
    assert 'href="/admin/credentials"' in r.text, (
        "Banner 'Go to Admin' button should target /admin/credentials"
    )
    assert "Welcome — add your AI API key" in r.text, (
        "Banner headline 'Welcome — add your AI API key' missing"
    )


def test_home_hides_dist07_banner_when_admin_has_key(
    client,
    seeded_admin_user,
    monkeypatch,
) -> None:
    """Admin WITH at least one resolvable AI key does NOT see the DIST-07 banner.

    Seed strategy: monkeypatch ``credentials_service.get_provider_credential``
    to return a sentinel object for ``anthropic``. This avoids the Fernet
    encryption round-trip that ``tests/services/test_credentials.py`` already
    covers — the test here is about the template-level banner gate, not the
    encryption layer.
    """
    _require_nav_wired()
    _patch_with_key(monkeypatch, provider="anthropic")
    signed_cookie = seeded_admin_user["signed_cookie"]

    r = client.get("/", cookies={"session_id": signed_cookie})

    assert r.status_code == 200
    assert "bannerDismiss" not in r.text, (
        "Banner must NOT render when admin already has an AI key configured"
    )


@pytest.mark.parametrize("has_key", [False, True])
def test_home_hides_dist07_banner_for_non_admin(
    client,
    seeded_regular_user,
    monkeypatch,
    has_key,
) -> None:
    """Non-admin user never sees the banner — with or without an AI key."""
    _require_nav_wired()
    if has_key:
        _patch_with_key(monkeypatch, provider="anthropic")
    else:
        _patch_no_key(monkeypatch)
    signed_cookie = seeded_regular_user["signed_cookie"]

    r = client.get("/", cookies={"session_id": signed_cookie})

    assert r.status_code == 200
    assert "bannerDismiss" not in r.text, (
        f"Banner must NEVER render for non-admin (has_key={has_key})"
    )


def test_banner_dismiss_component_registered_in_base_html(
    client,
    seeded_regular_user,
) -> None:
    """base.html registers banner-dismiss.js with a CSP nonce."""
    _require_nav_wired()
    signed_cookie = seeded_regular_user["signed_cookie"]

    r = client.get("/", cookies={"session_id": signed_cookie})

    assert r.status_code == 200
    assert '<script defer src="/static/js/alpine-components/banner-dismiss.js"' in r.text, (
        "banner-dismiss.js registration missing from base.html"
    )
    import re

    script_match = re.search(
        r'<script defer src="/static/js/alpine-components/banner-dismiss\.js"[^>]*>',
        r.text,
    )
    assert script_match is not None, "banner-dismiss.js script tag not found"
    assert "nonce=" in script_match.group(0), (
        "banner-dismiss.js script tag must carry a CSP nonce attribute"
    )


def test_dist07_banner_uses_admin_credentials_route(
    client,
    seeded_admin_user,
    monkeypatch,
) -> None:
    """Admin+no-key banner button targets /admin/credentials — not /admin (A3)."""
    _require_nav_wired()
    _patch_no_key(monkeypatch)
    signed_cookie = seeded_admin_user["signed_cookie"]

    r = client.get("/", cookies={"session_id": signed_cookie})

    assert r.status_code == 200
    assert 'href="/admin/credentials"' in r.text, (
        "Banner href target must be exactly /admin/credentials"
    )
