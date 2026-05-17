"""Stub ``/login`` and ``/setup`` routes for Phase 1.

Real bodies land in Phase 2. The stubs MUST be decorated with the rate
limiter so slowapi can be exercised end-to-end. The stub ``/login`` emits
one ``auth.login_attempt`` log line per request (no ``user_id`` in Phase 1
because auth isn't implemented yet — Phase 2 adds it on real-user matches
per D-15).

AUTH-10 invariant: neither stub reads the request body. Phase 1's audit
trail is exactly ``event=auth.login_attempt, ip, request_id`` — nothing
that could leak credentials.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request

from app.events import AUTH_LOGIN_ATTEMPT
from app.rate_limit import LOGIN_LIMIT, SETUP_LIMIT, limiter

log = structlog.get_logger()
router = APIRouter()


@router.post("/login", status_code=200)
@limiter.limit(LOGIN_LIMIT)
async def login_stub(request: Request) -> dict:
    """Stub login. Phase 2 replaces the body with the real argon2 verify flow.

    The ``request: Request`` parameter is required for slowapi's decorator
    introspection — see RESEARCH §7. Body is intentionally not read
    (AUTH-10).
    """
    log.info(
        AUTH_LOGIN_ATTEMPT,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    return {"status": "stub", "phase": "1"}


@router.post("/setup", status_code=200)
@limiter.limit(SETUP_LIMIT)
async def setup_stub(request: Request) -> dict:
    """Stub first-admin setup. Phase 2 replaces with the real flow.

    No log line here — ``/setup`` doesn't have an analogue to
    ``auth.login_attempt`` in the D-14 taxonomy; Phase 2 emits
    ``admin.user_created`` on the real path.
    """
    return {"status": "stub", "phase": "1"}
