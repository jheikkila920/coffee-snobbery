"""Wave 0 stubs for SEC-04 + D-16 (/debug/proxy endpoint).

Covers per-task verification map rows for SEC-04 / D-16 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_default_returns_shape``    — JSON body has scheme, client_host,
                                       trusted_proxy_ips, headers_honored
- ``test_https_via_proxy_header``   — X-Forwarded-Proto: https → scheme=https
                                       AND client_host = X-Forwarded-For value

Plan 08 wires ``app.routers.debug.router``. Phase 1 ships the endpoint public;
Phase 2 wraps it in the ``is_admin`` gate (D-16). The endpoint is permanent
operational tooling — used after every NGINX config change to confirm
``X-Forwarded-*`` flow.
"""

from __future__ import annotations

import pytest


def _require_debug_proxy() -> None:
    try:
        from app.routers.debug import router  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.routers.debug (Plan 08)")


def test_default_returns_shape(client, seeded_admin_user) -> None:
    """SEC-04 / D-16: /debug/proxy returns JSON with the four documented keys.

    Phase 2 D-14 gated /debug/proxy behind admin — the test now seeds an
    admin user and presents the cookie.
    """
    _require_debug_proxy()
    response = client.get(
        "/debug/proxy",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("scheme", "client_host", "trusted_proxy_ips", "headers_honored"):
        assert key in body, f"missing key {key!r} in /debug/proxy body: {body}"


@pytest.mark.xfail(
    reason=(
        "Starlette TestClient does NOT invoke uvicorn's ProxyHeadersMiddleware, "
        "so X-Forwarded-Proto: https is never translated into request.url.scheme. "
        "The /debug/proxy endpoint reads request.url.scheme directly (correct against "
        "real uvicorn with --proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS). "
        "Persisted as item #1 in 01-HUMAN-UAT.md — verify post-deploy via "
        "curl -i https://snobbery.example.com/debug/proxy."
    ),
    strict=False,
)
def test_https_via_proxy_header(client, seeded_admin_user, forwarded_headers) -> None:
    """SEC-04: with X-Forwarded-Proto: https, scheme=https and client_host=forwarded IP.

    The ``forwarded_headers`` fixture (conftest.py) supplies the canonical
    {Proto: https, For: 203.0.113.7} pair.

    Phase 2 D-14 gated /debug/proxy behind admin — the test now seeds an
    admin user and presents the cookie. The xfail reason (TestClient does
    not invoke ProxyHeadersMiddleware) is independent of D-14 and still
    applies.
    """
    _require_debug_proxy()
    response = client.get(
        "/debug/proxy",
        headers=forwarded_headers,
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("scheme") == "https", (
        f"X-Forwarded-Proto: https not honored: scheme={body.get('scheme')!r}"
    )
    assert body.get("client_host") == "203.0.113.7", (
        f"X-Forwarded-For not honored: client_host={body.get('client_host')!r}"
    )


def test_debug_proxy_admin_only(
    client, seeded_admin_user, seeded_regular_user
) -> None:
    """D-14 / AUTH-09: /debug/proxy is admin-gated.

    Three states:
    * anonymous → 401 or 403
    * non-admin authenticated → 403
    * admin authenticated → 200 + the existing 4-key body shape
    """
    _require_debug_proxy()
    # Anon
    r_anon = client.get("/debug/proxy")
    assert r_anon.status_code in (401, 403), (
        f"anon must be 401/403, got {r_anon.status_code}"
    )
    # Non-admin
    r_user = client.get(
        "/debug/proxy",
        cookies={"session_id": seeded_regular_user["signed_cookie"]},
    )
    assert r_user.status_code == 403, (
        f"non-admin must be 403, got {r_user.status_code}"
    )
    # Admin
    r_admin = client.get(
        "/debug/proxy",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    assert r_admin.status_code == 200, (
        f"admin must be 200, got {r_admin.status_code}: {r_admin.text[:200]}"
    )
    body = r_admin.json()
    for key in ("scheme", "client_host", "trusted_proxy_ips", "headers_honored"):
        assert key in body, f"missing key {key!r} in /debug/proxy body: {body}"
