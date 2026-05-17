"""slowapi 0.1.9 wiring.

Final replacement for the Plan 01-03 stub. Uses ``get_remote_address``
(NOT ``get_ipaddr`` — slowapi issue #255 / RESEARCH §13.3) so that uvicorn's
``--proxy-headers`` rewriting of ``request.client.host`` from
``X-Forwarded-For`` feeds the keying function correctly.

In-memory storage is consistent under the single uvicorn worker rule
(FOUND-04). Restart clears all rate-limit buckets — documented limitation
in RESEARCH §7; household scale + single VPS makes this acceptable.

Limits per CONTEXT D-17:

- ``/login`` and ``/setup``: 5/15 minutes per IP
- ``/csp-report``: 30/minute per IP

The ``register_rate_limiter(app)`` helper is called once by Plan 09 during
``app/main.py`` assembly. It (a) sets ``app.state.limiter`` (slowapi looks
there at decoration time) and (b) registers a custom 429 handler that emits
the canonical ``rate_limit.exceeded`` structured log line BEFORE delegating
to slowapi's stock JSON response. Every 429 leaves an audit trail (T-07-07).
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import Response

from app.events import RATE_LIMIT_EXCEEDED

log = structlog.get_logger()

# Limit-string constants — per-route decorations import these rather than
# hard-coding strings, so D-17 changes touch exactly one file.
LOGIN_LIMIT: str = "5/15minutes"
SETUP_LIMIT: str = "5/15minutes"
CSP_REPORT_LIMIT: str = "30/minute"

# Module-level Limiter. Constructed at import so router modules can decorate
# at module-load time via ``@limiter.limit(...)``. ``default_limits=[]``
# means routes opt in explicitly — RESEARCH §7 calls out no global default.
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def _structured_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Emit a structured ``rate_limit.exceeded`` log line, then delegate.

    Logs ``path``, ``ip``, and ``detail`` — never the request body. Calls
    slowapi's stock ``_rate_limit_exceeded_handler`` to preserve the
    canonical 429 JSON response shape.
    """
    log.warning(
        RATE_LIMIT_EXCEEDED,
        path=request.url.path,
        ip=request.client.host if request.client else "unknown",
        detail=str(getattr(exc, "detail", "")),
    )
    return _rate_limit_exceeded_handler(request, exc)


def register_rate_limiter(app: FastAPI) -> None:
    """Attach the limiter + exception handler to a FastAPI app.

    Called once by Plan 09 during ``app/main.py`` assembly. slowapi looks
    up ``app.state.limiter`` at decoration time, so this MUST run before
    any router is included.
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _structured_rate_limit_handler)
