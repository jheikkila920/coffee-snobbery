"""AUTH-09 + D-13: ``GET /admin`` three-state gate + hub-body coverage.

Originally Plan 02-08 stub coverage; the admin-200 body assertions were
updated for Phase 9 (Plan 09-01) when the stub became the real admin hub.

Four tests cover the VALIDATION map rows:

* ``test_admin_gate_anon_returns_403`` — anonymous request → 401 or 403
  (the AUTH-09 VALIDATION row permits either; this implementation unifies
  on 403 via ``require_admin``).
* ``test_admin_gate_non_admin_returns_403`` — seeded non-admin session → 403.
* ``test_admin_gate_admin_returns_200`` — seeded admin session → 200 with the
  Phase 9 admin hub (section nav + hub links). Phase 2's stub body was
  retired when Plan 09-01 built the real admin sub-package.
* ``test_admin_hub_body`` — same 200-path but asserts the hub card grid links
  to all five admin sections (the durable replacement for the old
  "D-13 /admin stub literal body" VALIDATION row).

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
    """Admin seeded session → 200 with the Phase 9 admin hub.

    Phase 2 shipped a literal stub here; Plan 09-01 replaced it with the
    real admin hub that extends ``admin_base.html`` and renders the
    persistent section nav. Assert the stable hub markers rather than the
    retired stub string.
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
    """The Phase 9 admin hub body (replaced the Phase 2 D-13 stub).

    Plan 09-01 turned the single-file stub into the admin sub-package whose
    hub page renders a card grid linking to the five sections. Assert the
    hub links — the durable replacement for the old stub line.
    """
    _require_admin_router()
    r = client.get(
        "/admin",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    assert r.status_code == 200
    for path in (
        "/admin/users",
        "/admin/credentials",
        "/admin/settings",
        "/admin/backups",
        "/admin/system",
    ):
        assert f'href="{path}"' in r.text, f"hub missing link to {path}"
