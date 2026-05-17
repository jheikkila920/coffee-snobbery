"""Configuration for starlette-csrf 3.0.

RESEARCH §3 locks every parameter; this module is the single source of truth so
Plan 09 (main.py wiring) and Plan 08 (base.html template) read from the same
constants.

This module is pure configuration — it does NOT import ``CSRFMiddleware`` from
``starlette_csrf`` directly. Plan 09 is responsible for the wiring call:

    from starlette_csrf import CSRFMiddleware
    from app.csrf import csrf_middleware_kwargs
    from app.config import settings

    app.add_middleware(
        CSRFMiddleware, **csrf_middleware_kwargs(settings.APP_SECRET_KEY)
    )

Stack-order note (RESEARCH §3 "Stack order interaction"): Plan 09 adds this
middleware AFTER ``SessionMiddleware`` so CSRF runs OUTSIDE (closer to the
wire) and fail-fasts with 403 before the session DB lookup runs.

Cookie lifecycle note (RESEARCH §3 + PROJECT.md row 15 + PITFALL HX-1):
``starlette-csrf`` sets the ``csrftoken`` cookie ONCE per session (no rotation
on every response). Multiple HTMX fragment swaps in the same browser session
share the same token — the second swap's POST is not rejected with a stale-
token 403. This is the locked-in reason for choosing the double-submit-cookie
pattern over rotated-per-request tokens.
"""

from __future__ import annotations

import re
from typing import Any

#: Cookie that holds the CSRF token (matches starlette-csrf 3.0 default).
CSRF_COOKIE_NAME: str = "csrftoken"

#: Header the client (HTMX listener + form posts) echoes the cookie value into.
#: RESEARCH §3 explicitly overrides the library's lowercase ``x-csrftoken``
#: default for consistency with the project's conventional naming.
CSRF_HEADER_NAME: str = "X-CSRF-Token"

#: Cookies whose presence triggers CSRF enforcement. The session cookie is the
#: only one listed: an unauthenticated POST that nevertheless carries the
#: ``csrftoken`` cookie (always present after the first safe GET) still gets
#: checked because the double-submit pattern remains intact.
CSRF_SENSITIVE_COOKIES: set[str] = {"session_id"}

#: URL patterns exempt from the CSRF check. CSP violation reports are POSTed by
#: browsers as ``application/csp-report`` without our cookies — checking CSRF
#: would always fail. Exempting ``/csp-report`` is an ASVS V4.2.1 sanctioned
#: known-safe-endpoint exception.
CSRF_EXEMPT_URL_PATTERNS: list[re.Pattern[str]] = [re.compile(r"^/csp-report")]


def csrf_middleware_kwargs(secret: str) -> dict[str, Any]:
    """Build the kwargs dict for ``app.add_middleware(CSRFMiddleware, ...)``.

    Pass ``settings.APP_SECRET_KEY`` as ``secret``. Plan 09 wires this via::

        app.add_middleware(
            CSRFMiddleware, **csrf_middleware_kwargs(settings.APP_SECRET_KEY)
        )

    The order matters — Plan 09 adds this middleware AFTER ``SessionMiddleware``
    so CSRF runs OUTSIDE (closer to wire, fail-fasts before session DB lookup)
    — see RESEARCH §3 "Stack order interaction" for the full rationale.

    Args:
        secret: HMAC signing key for the CSRF cookie. Re-uses
            ``APP_SECRET_KEY`` per RESEARCH §3 (cryptographically separate
            from the session signer via the library's distinct HMAC use).

    Returns:
        Keyword-argument dict matching ``starlette_csrf.CSRFMiddleware``'s
        constructor signature. Every value is locked by RESEARCH §3 and the
        STRIDE threat register (T-05-01..T-05-06).
    """
    return {
        "secret": secret,
        "cookie_name": CSRF_COOKIE_NAME,
        "cookie_secure": True,
        "cookie_samesite": "lax",
        "header_name": CSRF_HEADER_NAME,
        "sensitive_cookies": CSRF_SENSITIVE_COOKIES,
        "exempt_urls": CSRF_EXEMPT_URL_PATTERNS,
    }
