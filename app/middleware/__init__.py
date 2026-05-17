"""Cross-cutting middleware; owned by Phase 1.

Every middleware in this package is **pure ASGI**
(``__call__(scope, receive, send)``) — never inherit from Starlette's
request/response-buffering middleware base class (``starlette.middleware.base``).
That base class breaks :class:`contextvars.ContextVar` propagation, which
silently destroys the structlog ``request_id`` correlation that AUTH-10
depends on, and is on a soft-deprecation path in Starlette 1.0.
"""

from app.middleware.fragment_cache import FragmentCacheHeadersMiddleware

__all__ = ["FragmentCacheHeadersMiddleware"]
