"""Phase 11 Plan 03 nav + config hub smoke tests.

Asserts:
    1. GET /config returns 200 for an authenticated user (require_user works).
    2. GET /config returns 401 for an anonymous user.
    3. An authenticated non-admin user's home page response does NOT contain
       the /admin nav link (MOB-02 admin-tab hiding).
    4. An authenticated admin user's home page response DOES contain /admin.
    5. An authenticated user's home page contains the bottom-nav marker
       x-data="navBar" (persistent nav present).

Phase 17 Plan 01 additions (IA-01 + IA-02):
    6. Admin's home page has NO ``href="/admin"`` inside the bottom-nav
       ``<nav x-data="navBar">`` region (D-01). Top-nav admin link still
       present (D-18) — see test 10 below.
    7. Admin's /config page has an ``Administration`` section containing
       ``href="/admin"`` (D-17 / IA-01).
    8. Non-admin's /config page has NO ``href="/admin"`` anywhere (no
       top-nav link, no Administration section).
    9. Any authed user's home page has ``href="/ai"`` and the ``AI`` label
       inside the bottom-nav region (D-02 / IA-02).
    10. Admin's home page still contains an ``href="/admin"`` somewhere
        (top-nav link survives the bottom-nav reshape — D-18 regression
        guard).
"""

from __future__ import annotations

import re


def _require_nav_wired() -> None:
    """Skip if any Phase 11 Plan 03 dependency is missing."""
    try:
        from app.routers.config_hub import router  # noqa: F401
    except ImportError as exc:
        import pytest

        pytest.skip(f"config_hub router not wired: {exc}")


def test_config_hub_returns_200_for_authenticated_user(
    client,
    seeded_regular_user,
) -> None:
    """GET /config returns 200 for an authenticated (non-admin) user."""
    _require_nav_wired()
    signed_cookie = seeded_regular_user["signed_cookie"]
    r = client.get(
        "/config",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200, (
        f"GET /config must return 200 for authenticated user; got {r.status_code}: {r.text[:300]}"
    )
    # Config hub page should contain catalog links
    assert "/coffees" in r.text
    assert "/equipment" in r.text
    assert "/recipes" in r.text
    assert "/roasters" in r.text
    assert "/flavor-notes" in r.text


def test_config_hub_returns_401_for_anonymous(client) -> None:
    """GET /config returns 401 for an unauthenticated (anonymous) user."""
    _require_nav_wired()
    r = client.get("/config")
    assert r.status_code == 401, (
        f"GET /config must return 401 for anonymous user; got {r.status_code}"
    )


def test_config_hub_has_mobile_signout_form(
    client,
    seeded_regular_user,
) -> None:
    """Config hub has the md:hidden sign-out CSRF POST form to /logout (D-03)."""
    _require_nav_wired()
    signed_cookie = seeded_regular_user["signed_cookie"]
    r = client.get(
        "/config",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    assert 'action="/logout"' in r.text, (
        "config_hub.html must contain a CSRF POST form to /logout for mobile sign-out (D-03)"
    )


def test_non_admin_home_has_no_admin_link(
    client,
    seeded_regular_user,
) -> None:
    """An authenticated NON-admin user's home page does NOT contain the /admin nav link (MOB-02)."""
    _require_nav_wired()
    signed_cookie = seeded_regular_user["signed_cookie"]
    r = client.get(
        "/",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    # The admin link should not appear in the nav for non-admin users.
    # We check specifically for the nav Admin link, not any other admin reference.
    # The link pattern in base.html is href="/admin" within the nav frame.
    assert 'href="/admin"' not in r.text, (
        'Non-admin user\'s home page must NOT contain href="/admin" in the nav (MOB-02)'
    )


def test_admin_home_has_admin_link(
    client,
    seeded_admin_user,
) -> None:
    """An authenticated ADMIN user's home page DOES contain the /admin nav link."""
    _require_nav_wired()
    signed_cookie = seeded_admin_user["signed_cookie"]
    r = client.get(
        "/",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    assert 'href="/admin"' in r.text, (
        'Admin user\'s home page must contain href="/admin" in the nav'
    )


def test_authenticated_home_has_nav_bar_component(
    client,
    seeded_regular_user,
) -> None:
    """An authenticated user's home page contains the navBar x-data attribute."""
    _require_nav_wired()
    signed_cookie = seeded_regular_user["signed_cookie"]
    r = client.get(
        "/",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    assert 'x-data="navBar"' in r.text, (
        'Authenticated home page must contain x-data="navBar" (persistent nav frame present)'
    )


# --------------------------------------------------------------------------- #
# Phase 17 Plan 01 — IA-01 + IA-02 nav reshape assertions
# --------------------------------------------------------------------------- #


_BOTTOM_NAV_RE = re.compile(r'<nav x-data="navBar".*?</nav>', re.DOTALL)


def _bottom_nav_block(html: str) -> str:
    """Extract the ``<nav x-data="navBar">...</nav>`` substring from an HTML page.

    Returns the matched block so tests can scope assertions to the bottom
    nav region only. The top-nav admin link survives Phase 17 per D-18,
    so a bare ``'href="/admin"' in r.text`` check is no longer sufficient
    to assert IA-01.
    """
    m = _BOTTOM_NAV_RE.search(html)
    assert m is not None, (
        'Could not locate <nav x-data="navBar">...</nav> in response HTML; '
        "base.html bottom nav block missing or shape changed."
    )
    return m.group(0)


def test_admin_home_has_no_admin_bottom_nav_tab(
    client,
    seeded_admin_user,
) -> None:
    """IA-01 / D-01: Admin's bottom nav must NOT contain href="/admin".

    The Admin slot is fully removed from the bottom tab bar in Phase 17.
    The top-nav admin link survives per D-18; this test scopes the
    assertion to the bottom-nav region only.
    """
    _require_nav_wired()
    signed_cookie = seeded_admin_user["signed_cookie"]
    r = client.get(
        "/",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    bottom = _bottom_nav_block(r.text)
    assert 'href="/admin"' not in bottom, (
        'Bottom-nav (<nav x-data="navBar">) must NOT contain href="/admin" '
        "for admin users (IA-01 / D-01)"
    )


def test_admin_config_page_has_admin_entry(
    client,
    seeded_admin_user,
) -> None:
    """IA-01 / D-17: Admin's /config page contains an Administration section
    with href="/admin"."""
    _require_nav_wired()
    signed_cookie = seeded_admin_user["signed_cookie"]
    r = client.get(
        "/config",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    assert "Administration" in r.text, (
        '/config (admin) must contain the literal text "Administration" '
        "(D-17 — Admin entry section heading)"
    )
    assert 'href="/admin"' in r.text, (
        '/config (admin) must contain href="/admin" (D-17 — Admin entry link)'
    )


def test_non_admin_config_page_has_no_admin_entry(
    client,
    seeded_regular_user,
) -> None:
    """IA-01: Non-admin's /config page contains no href="/admin" anywhere.

    Neither the top-nav admin link (is_admin-gated, D-18) nor the new
    Administration section (is_admin-gated, D-17) should render for
    non-admins.
    """
    _require_nav_wired()
    signed_cookie = seeded_regular_user["signed_cookie"]
    r = client.get(
        "/config",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    assert 'href="/admin"' not in r.text, (
        '/config (non-admin) must NOT contain href="/admin" anywhere '
        "(no top-nav link, no Administration section)"
    )


def test_home_has_ai_bottom_nav_tab(
    client,
    seeded_regular_user,
) -> None:
    """IA-02 / D-02: Bottom nav contains href="/ai" and an "AI" label.

    The AI tab is always visible (D-03) — exercise this with a regular
    user (not just admin) to confirm the slot is not is_admin-gated.
    """
    _require_nav_wired()
    signed_cookie = seeded_regular_user["signed_cookie"]
    r = client.get(
        "/",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    bottom = _bottom_nav_block(r.text)
    assert 'href="/ai"' in bottom, (
        'Bottom-nav must contain href="/ai" — the new AI tab (IA-02 / D-01)'
    )
    assert ">AI<" in bottom, (
        'Bottom-nav must contain the literal label ">AI<" '
        '(the <span class="text-xs">AI</span> tab label, D-02)'
    )


def test_top_nav_still_has_admin_link_for_admin(
    client,
    seeded_admin_user,
) -> None:
    """D-18 regression guard: admin's home page still has an href="/admin"
    somewhere (the top-nav link at >=768px stays).

    Pairs with test_admin_home_has_no_admin_bottom_nav_tab — together they
    pin "removed from bottom nav, kept in top nav" precisely.
    """
    _require_nav_wired()
    signed_cookie = seeded_admin_user["signed_cookie"]
    r = client.get(
        "/",
        cookies={"session_id": signed_cookie},
    )
    assert r.status_code == 200
    assert 'href="/admin"' in r.text, (
        'Admin\'s home page must still contain href="/admin" somewhere '
        "(top-nav link at >=768px stays per D-18)"
    )
