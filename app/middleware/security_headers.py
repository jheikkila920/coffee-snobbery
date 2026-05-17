"""Security response-header layer — owned by Phase 1 (Plan 01-03).

This module ships a *pure ASGI* :class:`SecurityHeadersMiddleware` that
appends — never replaces — the full security-header set on every HTTP
response. The set is locked in CONTEXT D-05 and satisfies SEC-02
(nonce-based CSP, no ``'unsafe-eval'``, no ``'unsafe-inline'`` for scripts)
and SEC-03 (X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
Permissions-Policy).

Why pure ASGI and not :class:`starlette.middleware.base.BaseHTTPMiddleware`?
``BaseHTTPMiddleware`` buffers the entire response body before forwarding it
downstream, which breaks streaming responses (Phase 1 also adds a fragment
cache, Phase 6's eventual AI streaming endpoint, ``StaticFiles`` ranged
GETs). The ``send_wrapper`` pattern below mutates only the
``http.response.start`` ASGI message — the body chunks pass through
untouched.

Headers appended on the response.start message:

- ``content-security-policy`` — full directive set with the per-request
  nonce substituted via :data:`CSP_TEMPLATE`. The nonce is minted upstream
  by Plan 02's ``RequestContextMiddleware`` and surfaced via
  ``scope["state"]["csp_nonce"]``. If the nonce is missing (pitfall §13.4
  in 01-RESEARCH.md), the middleware falls back to :data:`CSP_FALLBACK`
  (script-src 'self' with no nonce term) and emits a structured
  ``csp.nonce_missing`` WARNING — fails closed (blocks all inline scripts)
  rather than open.
- ``x-frame-options: DENY`` — clickjacking belt-and-braces alongside CSP
  ``frame-ancestors 'none'``.
- ``x-content-type-options: nosniff`` — disables MIME sniffing.
- ``referrer-policy: strict-origin-when-cross-origin`` — limits referrer
  leakage to external origins.
- ``permissions-policy: ...`` — allowlists browser feature APIs.
- ``reporting-endpoints: csp-report="/csp-report"`` — paired with CSP's
  ``report-to`` directive for the modern Reporting API path.

Wiring: Plan 09's ``app/main.py`` assembly adds this middleware to the
FastAPI app via ``app.add_middleware(SecurityHeadersMiddleware)``. Order
matters — RequestContextMiddleware (Plan 02) must run BEFORE this one so
``scope["state"]["csp_nonce"]`` is populated by the time the response
starts.
"""

from __future__ import annotations

from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Module constants — verifiable from tests without instantiating middleware.   #
# --------------------------------------------------------------------------- #

# CSP directive list locked in CONTEXT D-05.
# The single ``{nonce}`` placeholder appears in two positions (script-src AND
# style-src-elem) — both filled with the same per-request value via str.format.
#
# Order chosen for grep readability: defaults first, source-specific second,
# capability locks third, reporting last. The ``; `` separator is canonical
# (RFC 7240 §3 / WHATWG CSP); browsers tolerate the trailing absence of a
# semicolon and we omit it deliberately for cleaner ``split("; ")`` parsing in
# tests.
#
# IMPORTANT — ``'unsafe-eval'`` MUST NOT appear anywhere in this string
# (SEC-02). ``'unsafe-inline'`` is permitted ONLY in the ``style-src-attr``
# directive (Alpine.js needs inline style attributes for x-show/x-transition
# bindings; the alternative is style hashes per inline x-binding which is
# impractical at the rate Alpine mutates style). Tests assert this.
CSP_TEMPLATE: str = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}'; "
    "style-src-elem 'self' 'nonce-{nonce}'; "
    "style-src-attr 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "report-uri /csp-report; "
    "report-to csp-report"
)

# Defensive fallback used when ``scope["state"]["csp_nonce"]`` is absent.
# Drops the ``'nonce-...'`` term from both nonce-aware directives so the
# response is well-formed but maximally restrictive (fails closed). The
# fallback path also emits a ``csp.nonce_missing`` WARNING so an operator
# can correlate degraded-CSP responses to a middleware misconfiguration.
CSP_FALLBACK: str = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src-elem 'self'; "
    "style-src-attr 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "report-uri /csp-report; "
    "report-to csp-report"
)

# Non-CSP headers — static (no per-request substitution). Stored as
# ``tuple[tuple[bytes, bytes], ...]`` because ASGI requires bytes for the
# ``message["headers"]`` payload; precomputing avoids the per-response
# str.encode() cost.
#
# Header names are lowercase per HTTP/2 (and tolerated by HTTP/1.1).
STATIC_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (
        b"permissions-policy",
        b"camera=(self), microphone=(), geolocation=(), interest-cohort=(), "
        b"payment=(), usb=(), bluetooth=()",
    ),
    (b"reporting-endpoints", b'csp-report="/csp-report"'),
)


# Module-load invariants: cheap sanity checks that the locked-down policy
# does not regress under future refactors. The pytest CSP tests duplicate
# these so a regression also flags in the test suite — but module-load
# catches the moment the import happens, before any code runs.
#
# Implemented as ``raise RuntimeError`` rather than ``assert`` so the check
# survives ``python -O`` (which strips asserts). The constraint is a
# security invariant, not a developer-only sanity check.
if "'unsafe-eval'" in CSP_TEMPLATE:
    raise RuntimeError(
        "CSP_TEMPLATE must not permit 'unsafe-eval' (SEC-02 / D-02)"
    )
# 'unsafe-inline' is permitted ONLY in the style-src-attr directive segment.
# Tokenize on '; ' and check that the only segment containing it begins with
# 'style-src-attr'.
for _segment in CSP_TEMPLATE.split("; "):
    if "'unsafe-inline'" in _segment and not _segment.startswith(
        "style-src-attr "
    ):
        raise RuntimeError(
            f"'unsafe-inline' may only appear in style-src-attr; found in: "
            f"{_segment!r}"
        )
del _segment  # don't leak the loop variable into the module namespace


# --------------------------------------------------------------------------- #
# Middleware                                                                  #
# --------------------------------------------------------------------------- #


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware that appends the security header set on every response.

    Does NOT inherit from :class:`BaseHTTPMiddleware` (see module docstring
    for the rationale). Lifespan and websocket scopes are passed through
    unchanged — neither has a meaningful response.start message.

    The middleware is stateless: a single instance handles every concurrent
    request. The ``send_wrapper`` closure captures ``scope`` so it can read
    the per-request CSP nonce when the response starts.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Store the downstream ASGI app for later delegation."""
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """ASGI entry point.

        For non-HTTP scopes (lifespan, websocket) pass through unchanged.
        For HTTP scopes, wrap ``send`` so the ``http.response.start`` message
        carries the security headers — the response body stream is untouched.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Read the per-request nonce minted upstream by Plan 02's
                # RequestContextMiddleware. ``scope.get("state", {})`` is
                # the defensive shape: even if no upstream middleware
                # initialised ``scope["state"]`` (e.g. under a raw ASGI
                # TestClient that bypasses Plan 02), we get an empty dict
                # rather than KeyError.
                state: dict[str, Any] = scope.get("state", {}) or {}
                nonce = state.get("csp_nonce", "")

                if nonce:
                    csp_value = CSP_TEMPLATE.format(nonce=nonce).encode("ascii")
                else:
                    # Defensive fallback per pitfall §13.4. We do NOT raise —
                    # a missing nonce is an upstream wiring bug, not a
                    # response-killing condition. Logging + a closed-fail
                    # policy is the right balance.
                    csp_value = CSP_FALLBACK.encode("ascii")
                    log.warning(
                        "csp.nonce_missing",
                        path=scope.get("path"),
                        method=scope.get("method"),
                    )

                # Append rather than replace: a downstream handler may have
                # set its own headers (e.g. cache-control, content-type,
                # location). The ASGI spec permits multiple entries per
                # header name; for the security headers we only ever append
                # once per response and downstream handlers don't set them,
                # so duplicate-key concerns don't apply.
                existing = list(message.get("headers", []))
                existing.append((b"content-security-policy", csp_value))
                existing.extend(STATIC_HEADERS)
                message["headers"] = existing

            await send(message)

        await self.app(scope, receive, send_wrapper)
