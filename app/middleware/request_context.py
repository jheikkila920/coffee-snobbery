"""Pure ASGI ``RequestContextMiddleware`` — outermost layer of the Phase 1 stack.

Plan 01-02 wires the cross-cutting per-request identifiers that every other
middleware and route handler depends on:

- A correlation ``request_id`` bound to :mod:`structlog.contextvars` so every
  structured log call inside the request carries it (AUTH-10).
- A per-request ``csp_nonce`` minted with 128 bits of entropy
  (:func:`secrets.token_urlsafe(16)`) and stashed on the ASGI scope for
  ``SecurityHeadersMiddleware`` (Plan 03) to read inside its
  ``http.response.start`` send-wrapper.
- ``scope["state"]["request_id"]`` and ``scope["state"]["csp_nonce"]`` exposed
  to downstream middleware + handlers — Starlette/FastAPI's :class:`Request`
  surfaces these as ``request.state.request_id`` and
  ``request.state.csp_nonce`` once the route runs.

Why pure ASGI, not :class:`starlette.middleware.base.BaseHTTPMiddleware`?
------------------------------------------------------------------------
PITFALL 13.1 in ``01-RESEARCH.md`` documents the load-bearing reason:
:class:`BaseHTTPMiddleware` runs the request inside a Starlette-managed
:class:`anyio.create_task_group`, which copies the parent
:class:`contextlib.copy_context` but never propagates contextvars MUTATIONS
made inside the request back to the route handler's frame. Binding
``request_id`` in a ``BaseHTTPMiddleware`` would silently no-op for the
handler's log calls. The pure-ASGI form (this file) runs in the same
context as the inner ``await self.app(...)`` and contextvars work.

Why ``clear_contextvars()`` at entry AND in ``finally``?
---------------------------------------------------------
PITFALL 13.2: contextvars are tied to the Python thread / event-loop task,
not to the request. The same worker reuses the same task for many
requests, and a leftover binding from request N would silently appear in
the JSON log lines of request N+1. The defensive entry-clear catches
leakage from a prior middleware that forgot to clean up; the ``finally``
clear catches an inner exception that prevents the natural-flow cleanup.

Plan 09 wires this class LAST in ``app.add_middleware(...)`` calls — last
``add_middleware`` is outermost in the request path (Starlette's reverse
order). Plan 03's :class:`SecurityHeadersMiddleware`, Plan 04's
``SessionMiddleware``, and every other Wave 1+ middleware run INSIDE this
one and therefore see ``request_id`` bound on ``contextvars`` and
``scope["state"]["csp_nonce"]`` populated.
"""

from __future__ import annotations

import re
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

# Accepted shape for an upstream-supplied ``X-Request-Id``. Threat T-02-02
# (log injection via crafted header): rejecting newlines + non-ASCII control
# bytes is the load-bearing defense. The regex restricts the value to URL-safe
# base64 alphabet + dash/underscore, 1-128 chars — wide enough for UUID hex
# (32 chars), ``secrets.token_urlsafe(8)`` (~11 chars), and most upstream
# correlation tokens; tight enough to reject ``"\n{\"event\":...\"}"`` injection.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# Header name in ASGI scope (lower-case bytes — ASGI 3.0 normalizes incoming
# header names to lower-case ASCII bytes). Outgoing echo is Plan 09's job.
_X_REQUEST_ID_HEADER = b"x-request-id"


class RequestContextMiddleware:
    """Bind ``request_id`` + mint ``csp_nonce`` on every HTTP scope.

    Pure ASGI — defines ``__init__(self, app)`` and
    ``async def __call__(self, scope, receive, send)`` and nothing else.
    See module docstring for the rationale against the Starlette base-class
    form.

    Lifespan and WebSocket scopes pass straight through to ``self.app``
    with zero side effects (the contract for non-HTTP middleware is "be
    invisible").
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # PITFALL 13.2 defensive entry-clear — catches leakage from any
        # outer middleware (or a previous request handled by this same
        # worker task) that didn't clean up its own contextvars bindings.
        clear_contextvars()

        # Honor incoming X-Request-Id only if it matches the strict
        # validation pattern. Anything malformed (non-ASCII, control chars,
        # over-long, empty) is silently replaced with a fresh mint —
        # T-02-02 log-injection mitigation.
        request_id = _extract_request_id(scope) or secrets.token_urlsafe(8)

        # 128-bit nonce per RESEARCH §9 — CSP spec recommends >=128 bits.
        # ``token_urlsafe(16)`` produces a 22-char URL-safe base64 string
        # that fits inside a CSP ``'nonce-...'`` source expression without
        # escaping.
        csp_nonce = secrets.token_urlsafe(16)

        # ``scope["state"]`` is the ASGI 3.0 conventional dict for
        # cross-middleware state. Starlette's Request object surfaces it
        # as ``request.state``. Use ``setdefault`` so we never overwrite
        # whatever an outer middleware might have populated (defensive
        # composition).
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["csp_nonce"] = csp_nonce

        # Bind onto structlog contextvars so every structlog call inside
        # the request frame (including foreign-pre-chain log lines from
        # uvicorn.access / SQLAlchemy) picks ``request_id`` up via
        # :func:`structlog.contextvars.merge_contextvars`.
        bind_contextvars(request_id=request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            # PITFALL 13.2 cleanup-clear — fires even if the inner app
            # raises, so an exception path cannot leak request_id into a
            # later request handled by the same worker task.
            clear_contextvars()


def _extract_request_id(scope: Scope) -> str | None:
    """Return a validated upstream ``X-Request-Id`` value, or ``None``.

    Iterates ASGI raw headers (``list[tuple[bytes, bytes]]``). On the
    first match for ``b"x-request-id"`` the value is decoded as ASCII
    (``errors="strict"`` to reject malformed bytes) and validated against
    :data:`_REQUEST_ID_PATTERN`. Any failure path returns ``None`` so the
    caller mints a fresh ID.
    """
    for name, value in scope.get("headers", []):
        if name != _X_REQUEST_ID_HEADER:
            continue
        try:
            decoded = value.decode("ascii")
        except UnicodeDecodeError:
            return None
        if _REQUEST_ID_PATTERN.match(decoded):
            return decoded
        return None
    return None
