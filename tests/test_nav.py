"""Phase 11 Plan 03 nav + config hub smoke tests.

Asserts:
    1. GET /config returns 200 for an authenticated user (require_user works).
    2. GET /config returns 401 for an anonymous user.
    3. An authenticated non-admin user's home page response does NOT contain
       the /admin nav link (MOB-02 admin-tab hiding).
    4. An authenticated admin user's home page response DOES contain /admin.
    5. An authenticated user's home page contains the bottom-nav marker
       x-data="navBar" (persistent nav present).
"""

from __future__ import annotations


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
        f"GET /config must return 200 for authenticated user; got {r.status_code}: "
        f"{r.text[:300]}"
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
        "Non-admin user's home page must NOT contain href=\"/admin\" in the nav (MOB-02)"
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
        "Admin user's home page must contain href=\"/admin\" in the nav"
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
        "Authenticated home page must contain x-data=\"navBar\" (persistent nav frame present)"
    )
