"""Cross-cutting middleware; owned by Phase 1.

All middleware classes here MUST be pure ASGI (``__init__(self, app)`` +
``async def __call__(self, scope, receive, send)``). NEVER inherit from
:class:`starlette.middleware.base.BaseHTTPMiddleware` — it runs requests
inside a task group that does not propagate
:mod:`structlog.contextvars` mutations back to the route handler, silently
breaking ``request_id`` correlation (AUTH-10) and any future
``contextvars``-bound user/session tracking. See ``01-RESEARCH.md`` §13.1
and the forthcoming ``docs/decisions/0002`` ADR (Plan 10) for the
load-bearing rationale.

Each Wave 1 plan lands a middleware module here and re-exports its class
from this package so ``app/main.py`` (Plan 09) can do a single
``from app.middleware import ...`` block instead of N module-level imports.
Subsequent Wave 1 plans (03 SecurityHeaders, 04 Session, 06 FragmentCache)
append their own re-exports below; the file is structured so additions are
purely additive — never a line replacement.
"""

from __future__ import annotations

from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
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
    "RequestContextMiddleware",
    "SecurityHeadersMiddleware",
    "SessionMiddleware",
]
