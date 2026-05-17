"""Pure ASGI middleware setting Cache-Control / Vary per D-11..D-13.

Sets ``Cache-Control`` / ``Vary`` based on the ``HX-Request`` request header per
D-11..D-13. Routes that set their OWN ``Cache-Control`` are respected (D-12
escape hatch). ``/static/`` paths bypass entirely so :class:`StaticFiles` can
set its own headers (longer cache for assets with content-hashed filenames per
FOUND-12).

Rules:

- Request carries ``HX-Request: true`` → response gets
  ``Cache-Control: no-store`` AND ``Vary: HX-Request``. Defends against
  PITFALL HX-2 (fragment-cache footgun) by default — `Vary` ensures
  intermediate proxies do not serve the fragment to a non-HTMX request.
- Request does NOT carry ``HX-Request`` → response gets
  ``Cache-Control: private, no-cache, must-revalidate``. Allows bfcache (fast
  back-button), forces revalidation so a logged-out user clicking "back"
  doesn't see a cached authenticated page. ``no-store`` is intentionally
  NOT used here — it would break the bfcache UX.
- Route already set ``Cache-Control`` (case-insensitive byte match against
  existing response headers) → middleware does NOT overwrite (D-12).
- ``scope["path"]`` matches any configured ``static_prefixes`` (default
  ``("/static/",)``) → middleware passes through untouched. StaticFiles owns
  its cache headers; content-hashed filenames per FOUND-12 want long
  immutable caching, not ``no-cache``.
- Non-HTTP scopes (lifespan, websocket) pass through untouched.

This is a **pure ASGI** middleware (``__call__(scope, receive, send)``) — never
inherit from Starlette's request/response-buffering middleware base class
(``starlette.middleware.base``), which is documented to break
:class:`contextvars.ContextVar` propagation and is on a soft-deprecation path
in Starlette 1.0. See ``01-RESEARCH.md`` §"Architectural Responsibility Map" +
§8 for the rationale.

The middleware is silent — no per-request logging of cache decisions (would be
pure noise at every-request frequency).

No ``Expires`` or ``Pragma`` header — modern browsers honor ``Cache-Control``
and the legacy headers add noise.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

# Module constants — exported for test introspection and to make the policy
# values discoverable from one place rather than buried in branch bodies.
HX_REQUEST_CACHE: bytes = b"no-store"
FULL_PAGE_CACHE: bytes = b"private, no-cache, must-revalidate"
HX_VARY: bytes = b"HX-Request"


class FragmentCacheHeadersMiddleware:
    """Apply D-11..D-13 cache-header policy to every HTTP response.

    Args:
        app: The inner ASGI application.
        static_prefixes: Tuple of path prefixes that bypass this middleware.
            Defaults to ``("/static/",)``. Pass a wider tuple to also bypass
            e.g. ``"/sw.js"`` or ``"/manifest.json"`` when those land in
            Phase 11 (PWA).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        static_prefixes: tuple[str, ...] = ("/static/",),
    ) -> None:
        self.app = app
        self.static_prefixes = static_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Non-HTTP scopes (lifespan, websocket) — pass through untouched.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Static-asset bypass — StaticFiles owns its cache headers.
        path = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in self.static_prefixes):
            await self.app(scope, receive, send)
            return

        # Detect HX-Request by inspecting raw scope headers (list of
        # (bytes, bytes); ASGI guarantees keys are lowercased). We must NOT
        # build a Starlette ``Request`` here — that would force buffering of
        # the body and break streaming responses downstream.
        hx_request = False
        for name, value in scope.get("headers", []):
            if name == b"hx-request" and value.lower() == b"true":
                hx_request = True
                break

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                # D-12 escape hatch: do not overwrite a route-set
                # Cache-Control. Case-insensitive byte match against header
                # names (ASGI spec says they're lowercased, but `name.lower()`
                # is cheap insurance and matches what other middleware do).
                has_cache_control = any(name.lower() == b"cache-control" for name, _ in headers)
                if not has_cache_control:
                    if hx_request:
                        headers.append((b"cache-control", HX_REQUEST_CACHE))
                        headers.append((b"vary", HX_VARY))
                    else:
                        headers.append((b"cache-control", FULL_PAGE_CACHE))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
