"""AUTH-09 + D-13: ``GET /admin`` three-state gate + System-page body coverage.

Originally Plan 02-08 stub coverage; updated for the Phase 9 gap-closure pass
when /admin was redesigned to serve the System page directly (hub page removed).

Four tests cover the VALIDATION map rows:

* ``test_admin_gate_anon_returns_403`` — anonymous request → 401 or 403
  (the AUTH-09 VALIDATION row permits either; this implementation unifies
  on 403 via ``require_admin``).
* ``test_admin_gate_non_admin_returns_403`` — seeded non-admin session → 403.
* ``test_admin_gate_admin_returns_200`` — seeded admin session → 200 with the
  System page that extends ``admin_base.html`` (section nav present).
* ``test_admin_hub_body`` — same 200-path but asserts the System page content
  and the section nav links (hub card grid retired; /admin/system not in nav).

The ``_require_admin_router`` helper turns "Plan 02-08 not yet executed"
into a clean ``pytest.skip`` rather than an ``ImportError`` collection
failure (Wave 4 contract — every test file is collectable even if its
target plan has not landed).
"""

from __future__ import annotations

import pytest


def _require_admin_router() -> None:
    """Skip if Plan 02-08's ``app.routers.admin`` module has not landed."""
    try:
        from app.routers.admin import router  # noqa: F401
    except ImportError:
        pytest.skip("Wave 4 dep: app.routers.admin (Plan 02-08)")


def test_admin_gate_anon_returns_403(client) -> None:
    """Anonymous request to /admin returns 401 or 403.

    D-13 + AUTH-09: ``require_admin`` folds anon and non-admin into the
    same 403, but the VALIDATION row permits either 401 or 403 for the
    anon case. Accept both so the test stays green if a future revision
    splits the two.
    """
    _require_admin_router()
    r = client.get("/admin")
    if r.status_code == 404:
        pytest.xfail(
            "admin router not yet included in app.main — Plan 02-10 wires it; "
            "this test turns green then."
        )
    assert r.status_code in (401, 403), f"expected 401 or 403 for anon, got {r.status_code}"


def test_admin_gate_non_admin_returns_403(client, seeded_regular_user) -> None:
    """Non-admin seeded session → 403 (no body-content assertion needed)."""
    _require_admin_router()
    r = client.get(
        "/admin",
        cookies={"session_id": seeded_regular_user["signed_cookie"]},
    )
    if r.status_code == 404:
        pytest.xfail(
            "admin router not yet included in app.main — Plan 02-10 wires it; "
            "this test turns green then."
        )
    assert r.status_code == 403, f"non-admin must get 403, got {r.status_code}"


def test_admin_gate_admin_returns_200(client, seeded_admin_user) -> None:
    """Admin seeded session → 200 with the System page at /admin.

    /admin now serves the System page (hub page removed in Phase 9 gap closure).
    The System page extends admin_base.html, so the persistent section nav is
    present. Assert the stable markers: 200, section nav, and a System-page
    data label.
    """
    _require_admin_router()
    r = client.get(
        "/admin",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    assert r.status_code == 200, f"admin must get 200, got {r.status_code}: {r.text[:200]}"
    assert 'aria-label="Admin sections"' in r.text
    assert 'href="/admin/users"' in r.text


def test_admin_hub_body(client, seeded_admin_user) -> None:
    """GET /admin serves the System page; section nav has correct links.

    The hub card grid was removed in the Phase 9 gap-closure pass. /admin now
    renders the System page (System Info + API Health). Assert:
    - A stable System-page marker is present (App Version or System Info heading).
    - The section nav links to Users, Credentials, Settings, Backups.
    - System nav link points to /admin (not /admin/system).
    - /admin/system is NOT a nav link (it is a 301 redirect, not a nav item).
    """
    _require_admin_router()
    r = client.get(
        "/admin",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    assert r.status_code == 200

    # System page content — the System Info panel has an "App Version" label
    assert any(
        marker in r.text
        for marker in ("App Version", "System Info", "API Health", "Database Version")
    ), "System-page content not found at /admin"

    # Section nav links (hub cards replaced by section nav from admin_base.html)
    for path in ("/admin/users", "/admin/credentials", "/admin/settings", "/admin/backups"):
        assert f'href="{path}"' in r.text, f"section nav missing link to {path}"

    # System nav entry points to /admin, not /admin/system
    assert 'href="/admin"' in r.text, "System nav link href=/admin not found"
    # /admin/system must NOT appear as a nav href (it's a redirect, not a nav item)
    assert 'href="/admin/system"' not in r.text, (
        "href=/admin/system must not appear in nav (System links to /admin now)"
    )
