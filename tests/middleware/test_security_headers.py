"""Wave 0 stubs for SEC-02 + SEC-03 (CSP + full security header set).

Covers per-task verification map rows for SEC-02 / SEC-03 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_csp_present``         — CSP header carries ``script-src 'self' 'nonce-...'``
- ``test_nonce_uniqueness``    — two consecutive requests produce different nonces
- ``test_no_unsafe_eval`` — script-src contains neither ``'unsafe-eval'`` nor ``'unsafe-inline'``
- ``test_all_headers``         — X-Frame-Options DENY, X-Content-Type-Options nosniff,
                                  Referrer-Policy strict-origin-when-cross-origin,
                                  Permissions-Policy: camera=(self), microphone=(), geolocation=()

Each test attempts a sentinel import of the Wave 1 symbol
``app.middleware.security_headers:SecurityHeadersMiddleware`` (Plan 03 lands it).
If the import fails the test ``pytest.skip``s rather than failing collection —
the Wave 0 contract per ``01-01-PLAN.md`` is that every file is collectable
even when most tests are red.
"""

from __future__ import annotations

import re

import pytest


def _require_security_middleware() -> None:
    """Skip the calling test if Plan 03's symbol does not exist yet."""
    try:
        from app.middleware.security_headers import (  # noqa: F401
            SecurityHeadersMiddleware,
        )
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.security_headers.SecurityHeadersMiddleware")


def _extract_directive(csp_header: str, directive: str) -> str:
    """Return the token list for a CSP directive (e.g. ``script-src``)."""
    parts = [p.strip() for p in csp_header.split(";") if p.strip()]
    for part in parts:
        if part.startswith(f"{directive} "):
            return part[len(directive) + 1 :]
    return ""


def test_csp_present(client) -> None:
    """SEC-02: every response carries a CSP with ``script-src 'self' 'nonce-...'``."""
    _require_security_middleware()
    response = client.get("/")
    csp = response.headers.get("Content-Security-Policy", "")
    assert "'nonce-" in csp, f"CSP missing nonce token: {csp!r}"
    script_src = _extract_directive(csp, "script-src")
    assert "'self'" in script_src, f"script-src missing 'self': {script_src!r}"


def test_nonce_uniqueness(client) -> None:
    """SEC-02: two GET / requests must produce distinct CSP nonces."""
    _require_security_middleware()
    r1 = client.get("/")
    r2 = client.get("/")
    csp1 = r1.headers.get("Content-Security-Policy", "")
    csp2 = r2.headers.get("Content-Security-Policy", "")
    m1 = re.search(r"'nonce-([A-Za-z0-9+/=_-]+)'", csp1)
    m2 = re.search(r"'nonce-([A-Za-z0-9+/=_-]+)'", csp2)
    assert m1 and m2, f"nonce not found in CSP(s): {csp1!r}, {csp2!r}"
    assert m1.group(1) != m2.group(1), (
        f"nonce reused across requests: {m1.group(1)} == {m2.group(1)}"
    )


def test_no_unsafe_eval(client) -> None:
    """SEC-02: ``script-src`` must NOT permit ``'unsafe-eval'`` or ``'unsafe-inline'``.

    Alpine CSP build + nonce-only script execution forbids both per D-02 / D-04.
    """
    _require_security_middleware()
    response = client.get("/")
    csp = response.headers.get("Content-Security-Policy", "")
    script_src = _extract_directive(csp, "script-src")
    assert "'unsafe-eval'" not in script_src, f"script-src contains 'unsafe-eval': {script_src!r}"
    assert "'unsafe-inline'" not in script_src, (
        f"script-src contains 'unsafe-inline': {script_src!r}"
    )


def test_all_headers(client) -> None:
    """SEC-03: full hardening-header set lands on every response."""
    _require_security_middleware()
    response = client.get("/")
    assert response.headers.get("X-Frame-Options") == "DENY", response.headers
    assert response.headers.get("X-Content-Type-Options") == "nosniff", response.headers
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin", (
        response.headers
    )
    permissions = response.headers.get("Permissions-Policy", "")
    assert "camera=(self)" in permissions, f"missing camera=(self): {permissions!r}"
    assert "microphone=()" in permissions, f"missing microphone=(): {permissions!r}"
    assert "geolocation=()" in permissions, f"missing geolocation=(): {permissions!r}"
