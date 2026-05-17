"""Cross-cutting middleware; owned by Phase 1.

Every middleware in this package is **pure ASGI** —
``async def __call__(self, scope, receive, send)`` — never
:class:`starlette.middleware.base.BaseHTTPMiddleware`.

Why this matters: Starlette's deprecated request-response base
middleware runs the downstream app in a new task, breaking
:mod:`contextvars` propagation. That silently destroys structlog
``request_id`` correlation (AUTH-10) and any future
``contextvars``-bound user/session tracking. See RESEARCH §1 + §5 and
PITFALL 13.1. Future contributors: do **not** subclass that helper here.
"""

from app.middleware.session import (
    COOKIE_NAME,
    MAX_AGE_SECONDS,
    REFRESH_THRESHOLD_SECONDS,
    SessionMiddleware,
)

__all__ = [
    "COOKIE_NAME",
    "MAX_AGE_SECONDS",
    "REFRESH_THRESHOLD_SECONDS",
    "SessionMiddleware",
]
