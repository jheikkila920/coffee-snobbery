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
from urllib.parse import parse_qsl

from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Cookie that holds the CSRF token (matches starlette-csrf 3.0 default).
CSRF_COOKIE_NAME: str = "csrftoken"

#: Header the client (HTMX listener + form posts) echoes the cookie value into.
#: RESEARCH §3 explicitly overrides the library's lowercase ``x-csrftoken``
#: default for consistency with the project's conventional naming.
CSRF_HEADER_NAME: str = "X-CSRF-Token"

#: Cookies whose presence triggers CSRF enforcement. ``starlette-csrf`` checks
#: CSRF only when one of these cookies is present on the request, so enforcement
#: is scoped to requests carrying the ``session_id`` cookie — i.e. authenticated
#: sessions. Unauthenticated POSTs to ``/login`` and ``/setup`` carry no
#: ``session_id`` cookie and are therefore intentionally NOT CSRF-enforced. This
#: is a deliberate design choice: ``sensitive_cookies`` scopes enforcement to
#: authenticated sessions. The residual login-CSRF exposure is an accepted,
#: low-impact exception for this household-scale threat model (no public
#: registration; admin-provisioned users only).
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


class CSRFFormFieldShim:
    """Hoist the ``X-CSRF-Token`` form field into the request header.

    Required because ``starlette-csrf`` 3.0's ``_get_submitted_csrf_token``
    reads only headers (02-RESEARCH.md §"starlette-csrf 3.0 (CSRFMiddleware)
    — CRITICAL GOTCHA", confirmed against the library source). Without this
    shim, classic HTML form POSTs cannot deliver the CSRF token — the hidden
    ``<input>`` field ends up in the URL-encoded / multipart body, the header
    is empty, and the downstream middleware 403s.

    Behavior (D-15 spec, verbatim):

    1. Non-HTTP scopes (lifespan, websocket) — pass through untouched.
    2. Non-POST methods — pass through untouched.
    3. POST with the ``X-CSRF-Token`` header ALREADY present — pass through
       untouched. The HTMX listener wires this header from the ``csrftoken``
       cookie; the shim must be a no-op on that path.
    4. POST with content-type other than ``application/x-www-form-urlencoded``
       or ``multipart/form-data`` (e.g., ``application/json``) — pass
       through. A real API client is responsible for setting the header
       itself.
    5. Otherwise: buffer the entire body, parse it for the ``X-CSRF-Token``
       form field, inject ``(b"x-csrf-token", value.encode())`` into
       ``scope["headers"]``, and forward downstream with a replay-``receive``
       that re-emits the buffered chunks in original order with ``more_body``
       flags intact.

    Mount order (Plan 02-10 wires this — D-15 locked):

        app.add_middleware(SessionMiddleware, ...)
        app.add_middleware(CSRFMiddleware, ...)
        app.add_middleware(CSRFFormFieldShim)   # NEW
        app.add_middleware(FragmentCacheHeadersMiddleware)
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(RequestContextMiddleware)

    On a request: ``RequestContext → SecurityHeaders → FragmentCache →
    shim → CSRFMiddleware → SessionMiddleware → route``. So the shim
    executes BEFORE ``CSRFMiddleware`` on the inbound path — the headers it
    injects are visible by the time ``CSRFMiddleware`` does its check.

    Pure ASGI (no ``BaseHTTPMiddleware`` inheritance) per the project-wide
    invariant documented in the :mod:`app.middleware` package docstring —
    ``BaseHTTPMiddleware`` is on a soft-deprecation path in Starlette 1.0
    and breaks ``contextvars.ContextVar`` propagation.

    Body-preservation guarantee: chunks are buffered as
    ``(body_bytes, more_body)`` tuples and replayed in original order, so
    multipart bodies remain byte-for-byte identical to what the client
    sent. This is asserted by ``test_multipart_body_preserved`` (D-15
    regression gate).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Gate 1: non-HTTP scope (lifespan, websocket) — pass through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Gate 2: non-POST method — pass through. The CSRF check itself only
        # fires on state-changing requests; GET / HEAD / OPTIONS never need
        # body buffering.
        if scope.get("method", "GET").upper() != "POST":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        header_map = {name: value for name, value in headers}

        # Gate 3: header already present (HTMX path) — idempotent passthrough.
        # The HTMX listener wires X-CSRF-Token from the csrftoken cookie on
        # every request; the shim must not double-buffer those bodies.
        if b"x-csrf-token" in header_map:
            await self.app(scope, receive, send)
            return

        # Gate 4: content-type filter. Only form bodies can carry the token
        # as a field — JSON / other types delegate header-setting to the
        # client per D-15.
        content_type = header_map.get(b"content-type", b"")
        is_form = content_type.startswith(b"application/x-www-form-urlencoded")
        is_multipart = content_type.startswith(b"multipart/form-data")
        if not (is_form or is_multipart):
            await self.app(scope, receive, send)
            return

        # Step 5: buffer the body. Each chunk is preserved with its more_body
        # flag so the replay yields the same byte sequence + boundaries —
        # critical for multipart envelopes whose downstream parser is
        # boundary-sensitive.
        chunks: list[tuple[bytes, bool]] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # Disconnect (or unexpected message) — re-emit it so the
                # downstream app can handle the lifecycle. The buffered
                # body is discarded; nothing useful to replay.
                async def disconnect_receive(_msg: Message = message) -> Message:
                    return _msg

                await self.app(scope, disconnect_receive, send)
                return
            chunks.append((message.get("body", b""), message.get("more_body", False)))
            if not message.get("more_body", False):
                break

        full_body = b"".join(chunk for chunk, _ in chunks)

        # Parse for the X-CSRF-Token form field. The form-field name matches
        # CSRF_HEADER_NAME (exact case) — the template renders the hidden
        # <input> with name="X-CSRF-Token".
        token: str | None = None
        if is_form:
            try:
                # latin-1 keeps a 1:1 byte<->char map; the field name is
                # ASCII and the token value is ASCII per starlette-csrf.
                pairs = parse_qsl(full_body.decode("latin-1"), keep_blank_values=True)
                for k, v in pairs:
                    if k == CSRF_HEADER_NAME:
                        token = v
                        break
            except Exception:
                token = None
        else:
            # multipart — byte-scan for the specific named field. Using a
            # naive needle scan avoids instantiating Starlette's full
            # MultiPartParser (which would consume the body via async
            # iteration). The body is already buffered; scanning bytes is
            # O(n) and exact.
            try:
                boundary_marker = b"boundary="
                idx = content_type.find(boundary_marker)
                if idx != -1:
                    boundary = (
                        content_type[idx + len(boundary_marker) :].split(b";", 1)[0].strip(b'"')
                    )
                    needle = b'name="' + CSRF_HEADER_NAME.encode("ascii") + b'"\r\n\r\n'
                    pos = full_body.find(needle)
                    if pos != -1:
                        start = pos + len(needle)
                        end = full_body.find(b"\r\n--" + boundary, start)
                        if end != -1:
                            token = full_body[start:end].decode("latin-1")
            except Exception:
                token = None

        # Build the replay receive callable. ``chunks`` is captured by
        # reference; each call pops from the front so the chunked
        # ``more_body`` sequence is preserved exactly.
        chunks_to_replay = list(chunks)

        async def replay_receive() -> Message:
            if chunks_to_replay:
                body, more = chunks_to_replay.pop(0)
                return {"type": "http.request", "body": body, "more_body": more}
            # Defensive terminator: ASGI contract says the downstream app
            # should not call receive again after seeing more_body=False,
            # but if it does, return an empty no-more-body message rather
            # than hanging.
            return {"type": "http.request", "body": b"", "more_body": False}

        # If a token was found, mutate scope["headers"] in place so
        # downstream CSRFMiddleware sees it. When the token is absent the
        # shim is a no-op and CSRFMiddleware will 403 as expected — the
        # double-submit pattern still holds.
        if token is not None:
            new_headers = list(scope.get("headers", []))
            new_headers.append((b"x-csrf-token", token.encode("ascii", errors="replace")))
            scope["headers"] = new_headers

        await self.app(scope, replay_receive, send)


__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_EXEMPT_URL_PATTERNS",
    "CSRF_HEADER_NAME",
    "CSRF_SENSITIVE_COOKIES",
    "CSRFFormFieldShim",
    "csrf_middleware_kwargs",
]
