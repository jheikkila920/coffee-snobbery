"""Pure ASGI :class:`SessionMiddleware` — resolves ``request.state.user``.

Reads the signed ``session_id`` cookie, verifies the signature against
``app.config.settings.APP_SECRET_KEY``, looks up the matching row in the
``sessions`` table, and populates two scope-state attributes that every
downstream router can read:

* ``scope["state"]["session"]`` — the :class:`app.models.session.Session`
  row, or ``None`` when no live session exists.
* ``scope["state"]["user"]`` — the :class:`app.models.user.User` row
  when a live session resolves to an active user; ``None`` otherwise.
  Plan 02-06 D-09 swapped the Phase 1 ``{"user_id": int}`` stub for
  the full User row so downstream routes and templates can read
  ``.username`` / ``.is_admin`` / ``.email`` directly. D-10
  fail-closed: when the user row is missing OR ``is_active=false``,
  the session row is deleted, the cookie is cleared, and ``user`` is
  ``None``.

Pure ASGI (defines ``async def __call__(self, scope, receive, send)``).
**Do not** wrap this class in Starlette's deprecated request-response
base middleware — that path breaks ``contextvars.ContextVar`` propagation
which would silently destroy structlog's request_id correlation (see
PITFALL 13.1 / RESEARCH §1 + §5). The cookie parser is custom (~10 LOC,
strict split-on-``"; "``-then-``"="``) so a malformed ``Cookie:`` header
fails closed to "no signed_value extracted" rather than throwing — see
T-04-08 mitigation.

Write throttling (T-04-06 mitigation): ``last_seen`` is refreshed only
when ``(now - last_seen).total_seconds() > REFRESH_THRESHOLD_SECONDS``
(5 minutes). Without throttling a single HTMX-staggered home page would
emit ~6 writes; the throttle yields the ~98% reduction noted in
RESEARCH §5.

Phase 1 ships the middleware shape; Phase 1 Plan 09 wires it into
:mod:`app.main` with the real ``session_factory``. The constructor
accepts any callable returning an async-context-manager-compatible
:class:`sqlalchemy.ext.asyncio.AsyncSession`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.sessions import (
    build_session_clear_cookie,
    delete_session,
    get_session_by_id,
    refresh_last_seen,
)
from app.signing import load_session_id

# 5 minutes — the sliding-refresh granularity (RESEARCH §5). Lower values
# add write load; higher values widen the "session looks expired but
# really isn't" window the cleanup job sees. 300 seconds is the locked
# value the Wave 0 test asserts against.
REFRESH_THRESHOLD_SECONDS = 300

# 30 days — matches CONTEXT D-10 and
# :data:`app.services.sessions.SESSION_MAX_AGE_SECONDS`.
MAX_AGE_SECONDS = 2_592_000

# The cookie name is part of the public ASGI contract — Phase 2's /login
# response and Phase 1's /debug/whoami probe both reach for the same name.
COOKIE_NAME = "session_id"


def _parse_cookies(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Return a dict of cookie name → value parsed from the raw ASGI headers.

    Strict parser (T-04-08 mitigation): split on ``"; "``, then on the
    first ``"="``; empty segments and segments without ``"="`` are
    silently dropped. Never delegates to :class:`http.cookies.SimpleCookie`
    which has documented edge-case bugs on malformed input.

    Operating at the raw scope level (not via ``starlette.Request``)
    avoids constructing a :class:`starlette.requests.Request` per
    middleware — measurable overhead on a hot path.
    """
    out: dict[str, str] = {}
    for name, value in headers:
        if name != b"cookie":
            continue
        # Decode as latin-1 because the wire format is bytes; latin-1 is
        # the safest 1:1 round-trip for cookie values that may contain
        # non-UTF-8 bytes (URLSafeSerializer output is ASCII-only, but
        # other cookies sharing the header may not be).
        for segment in value.decode("latin-1").split("; "):
            if "=" not in segment:
                continue
            key, _, val = segment.partition("=")
            key = key.strip()
            if key:
                out[key] = val
        # First Cookie header wins. RFC 6265 says servers SHOULD only
        # send one; clients SHOULD only emit one. Be strict.
        break
    return out


# A session factory is any callable returning an async context manager
# that yields an AsyncSession. We type it loosely (``Any``) so a custom
# wrapper (e.g., a transactional-rollback test fixture) is accepted.
SessionFactory = Callable[[], Any]


class SessionMiddleware:
    """Pure ASGI middleware that populates ``request.state.user`` / ``session``.

    The implementation deliberately works on raw ``scope`` — never via
    :class:`starlette.requests.Request` — so cookie parsing and header
    injection avoid building a Request object on every hit. The
    ``send_wrapper`` pattern (capturing ``http.response.start``,
    mutating its ``headers`` list, then delegating to ``send``) is the
    Starlette-recommended way to add a response header from middleware
    that lives inside the routing tree.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        session_factory: SessionFactory,
        cookie_name: str = COOKIE_NAME,
        refresh_threshold_seconds: int = REFRESH_THRESHOLD_SECONDS,
        max_age_seconds: int = MAX_AGE_SECONDS,
    ) -> None:
        self.app = app
        self.session_factory = session_factory
        self.cookie_name = cookie_name
        self.refresh_threshold_seconds = refresh_threshold_seconds
        self.max_age_seconds = max_age_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan / websocket / other non-HTTP scopes pass through.
        # request.state semantics are HTTP-only here.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        scope.setdefault("state", {})
        cookies = _parse_cookies(scope.get("headers", []))
        signed_value = cookies.get(self.cookie_name)

        clear_cookie = False

        if signed_value is None:
            # No cookie → unauthenticated. Nothing to do.
            scope["state"]["user"] = None
            scope["state"]["session"] = None
        else:
            session_id = load_session_id(signed_value)
            if session_id is None:
                # Tampered / wrong-secret / non-UUID payload → defend
                # against fixation by clearing the cookie (T-04-01 +
                # T-04-04 mitigation).
                clear_cookie = True
                scope["state"]["user"] = None
                scope["state"]["session"] = None
            else:
                # Live lookup. Open a session via the injected factory.
                async with self.session_factory() as db:
                    session_row = await get_session_by_id(db, session_id)

                    if session_row is None:
                        # Cookie carried a UUID we've never minted
                        # (revoked / DB wipe / forged-but-signed).
                        clear_cookie = True
                        scope["state"]["user"] = None
                        scope["state"]["session"] = None
                    elif session_row.expires_at < datetime.now(UTC):
                        # Row expired — delete it so cleanup is
                        # immediate, then clear the cookie.
                        await delete_session(db, session_id)
                        clear_cookie = True
                        scope["state"]["user"] = None
                        scope["state"]["session"] = None
                    else:
                        # D-09: load the FULL User row in the same async
                        # session scope already open for the session
                        # lookup. Local import keeps the model module
                        # out of the middleware module's import graph
                        # until needed (RESEARCH Open Q6 — defensive
                        # against cyclic-import risk at app startup).
                        from app.models.user import User

                        user_result = await db.execute(
                            select(User).where(User.id == session_row.user_id)
                        )
                        user_row = user_result.scalar_one_or_none()

                        if user_row is None or not user_row.is_active:
                            # D-10: deleted-or-deactivated user →
                            # fail-closed, mirroring the expired-session
                            # branch above. Deactivating via the future
                            # admin tool logs the user out on their
                            # next request — no waiting for the 30-day
                            # cookie. ASVS V3.3.2 (immediate revocation).
                            await delete_session(db, session_id)
                            clear_cookie = True
                            scope["state"]["user"] = None
                            scope["state"]["session"] = None
                        else:
                            scope["state"]["session"] = session_row
                            # Public contract change: dict → User.
                            # Downstream routes (/admin, /debug/proxy,
                            # Phase 4+ catalog) read .username /
                            # .is_admin / .email directly.
                            scope["state"]["user"] = user_row

                            # Write-throttled sliding refresh
                            # (T-04-06 mitigation) — unchanged from
                            # Phase 1.
                            elapsed = (
                                datetime.now(UTC) - session_row.last_seen
                            ).total_seconds()
                            if elapsed > self.refresh_threshold_seconds:
                                await refresh_last_seen(db, session_id)

        async def send_wrapper(message: Message) -> None:
            """Inject a clear-cookie Set-Cookie header on the response start."""
            if clear_cookie and message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (b"set-cookie", build_session_clear_cookie().encode("ascii"))
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


__all__ = [
    "COOKIE_NAME",
    "MAX_AGE_SECONDS",
    "REFRESH_THRESHOLD_SECONDS",
    "SessionFactory",
    "SessionMiddleware",
]
