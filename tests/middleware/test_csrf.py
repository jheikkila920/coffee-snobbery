"""Wave 0 stubs for SEC-01 (double-submit-cookie CSRF via starlette-csrf).

Covers per-task verification map rows for SEC-01 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_missing_token``    — POST without cookie + header returns 403
- ``test_valid_token``      — POST with valid cookie + matching header is not 403
- ``test_no_rotation``      — csrftoken cookie value is stable across HTMX fragment swaps
                              (PITFALL HX-1 mitigation)
- ``test_csp_report_exempt`` — POST /csp-report exempt from CSRF middleware

Each test imports a Wave 1 sentinel (the starlette-csrf middleware is wired by
Plan 03 or Plan 05 — see ``01-CONTEXT.md`` middleware stack order). If the
``app.main`` import fails because Wave 1 hasn't run, the tests skip cleanly.

The cookie name ``csrftoken`` is the convention starlette-csrf uses (and what
the templates' HTMX base-header config will read). Asserted by literal name
match here so a future cookie-name rename will break this test and surface
the convention change.
"""

from __future__ import annotations

import pytest


def test_missing_token(client) -> None:
    """SEC-01: POST without CSRF cookie + header → 403."""
    try:
        from app.middleware import session  # noqa: F401 — sentinel, app.main pulls it
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session (Plan 04)")
    response = client.post("/login", data={"username": "x", "password": "y"})
    assert response.status_code == 403, (
        f"expected 403 (CSRF missing), got {response.status_code}: {response.text}"
    )


def test_valid_token(client) -> None:
    """SEC-01: POST with cookie + matching header → not 403.

    The valid-token path may return 200 (stub /login allows) or 429 (rate limit
    in effect from a prior test). The assertion is the negation: "not 403"
    isolates the CSRF concern from the rate-limit / route-body concerns.
    """
    try:
        from app.middleware import session  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session (Plan 04)")
    primer = client.get("/")
    token = primer.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF cookie 'csrftoken' not yet set by Wave 1 middleware")
    response = client.post(
        "/login",
        data={"username": "x", "password": "y"},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": token},
    )
    assert response.status_code != 403, (
        f"valid CSRF rejected with 403: {response.text}"
    )


def test_no_rotation(client) -> None:
    """SEC-01 / PITFALL HX-1: csrftoken cookie must NOT rotate per response.

    HTMX fragment swaps fire multiple POSTs against the same authenticated
    page; if the cookie rotated, the second swap would see a stale token.
    """
    try:
        from app.middleware import session  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session (Plan 04)")
    r1 = client.get("/")
    token1 = r1.cookies.get("csrftoken")
    if not token1:
        pytest.skip("CSRF cookie 'csrftoken' not yet set by Wave 1 middleware")
    r2 = client.get("/", headers={"HX-Request": "true"})
    token2 = r2.cookies.get("csrftoken") or token1
    assert token1 == token2, (
        f"CSRF cookie rotated across requests: {token1!r} != {token2!r}"
    )


def test_csp_report_exempt(client) -> None:
    """D-06 / SEC-01: POST /csp-report bypasses CSRF (browsers cannot send a token)."""
    try:
        from app.routers import csp_report  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.routers.csp_report (Plan 03)")
    response = client.post(
        "/csp-report",
        json={"csp-report": {"blocked-uri": "x", "violated-directive": "y"}},
        headers={"Content-Type": "application/csp-report"},
    )
    assert response.status_code != 403, (
        f"/csp-report rejected with 403 (CSRF middleware should exempt it): "
        f"{response.text}"
    )
