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


def test_default_returns_shape(client) -> None:
    """SEC-04 / D-16: /debug/proxy returns JSON with the four documented keys."""
    _require_debug_proxy()
    response = client.get("/debug/proxy")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("scheme", "client_host", "trusted_proxy_ips", "headers_honored"):
        assert key in body, f"missing key {key!r} in /debug/proxy body: {body}"


def test_https_via_proxy_header(client, forwarded_headers) -> None:
    """SEC-04: with X-Forwarded-Proto: https, scheme=https and client_host=forwarded IP.

    The ``forwarded_headers`` fixture (conftest.py) supplies the canonical
    {Proto: https, For: 203.0.113.7} pair.
    """
    _require_debug_proxy()
    response = client.get("/debug/proxy", headers=forwarded_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("scheme") == "https", (
        f"X-Forwarded-Proto: https not honored: scheme={body.get('scheme')!r}"
    )
    assert body.get("client_host") == "203.0.113.7", (
        f"X-Forwarded-For not honored: client_host={body.get('client_host')!r}"
    )
