"""AUTH-09 + D-13: ``GET /admin`` three-state gate + stub-body coverage (Plan 02-08).

Four tests cover the VALIDATION map rows:

* ``test_admin_gate_anon_returns_403`` — anonymous request → 401 or 403
  (the AUTH-09 VALIDATION row permits either; this implementation unifies
  on 403 via ``require_admin``).
* ``test_admin_gate_non_admin_returns_403`` — seeded non-admin session → 403.
* ``test_admin_gate_admin_returns_200`` — seeded admin session → 200 with the
  literal D-13 body. Uses the runtime-xfail pattern (a 404 between Wave 4
  and Wave 5 means Plan 02-10 has not wired the router into ``app.main``
  yet — same convention as ``tests/routers/test_auth.py``'s CSRF-block
  tests).
* ``test_admin_stub_body`` — same 200-path assertion but isolated for the
  "D-13 /admin stub literal body" VALIDATION row.

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
    assert r.status_code in (401, 403), (
        f"expected 401 or 403 for anon, got {r.status_code}"
    )


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
    """Admin seeded session → 200 with literal D-13 body.

    Wave 4 / Wave 5 split: this plan creates the router but Plan 02-10
    wires it into ``app.main``. Between the two plans the route is
    registered in ``app.routers.admin.router`` but not included in the
    app, so the request hits a 404. ``pytest.xfail`` keeps the suite
    green during incremental execution.
    """
    _require_admin_router()
    r = client.get(
        "/admin",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    if r.status_code == 404:
        pytest.xfail(
            "admin router not yet included in app.main — Plan 02-10 wires it; "
            "this test turns green then."
        )
    assert r.status_code == 200, f"admin must get 200, got {r.status_code}: {r.text[:200]}"
    assert "Admin (stub) — wiring lands in Phase 9" in r.text


def test_admin_stub_body(client, seeded_admin_user) -> None:
    """D-13: the literal Phase-2 admin stub body.

    Note the Unicode em-dash (U+2014) — the assertion must match exactly;
    a hyphen-minus would silently fail.
    """
    _require_admin_router()
    r = client.get(
        "/admin",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    if r.status_code == 404:
        pytest.xfail(
            "admin router not yet included in app.main — Plan 02-10 wires it; "
            "this test turns green then."
        )
    assert r.status_code == 200
    assert "Admin (stub) — wiring lands in Phase 9" in r.text
